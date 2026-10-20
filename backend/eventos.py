"""V2: mensagens em tempo real por WebSocket.

Cada cliente abre uma conexão persistente (socket) com ``/ws/eventos``. Quando
algo muda no acervo, a API publica uma mensagem JSON para todas as conexões:

    {"tipo": "emprestimo.criado", "dados": {...}, "momento": "2026-10-19T18:45:51Z"}

Diferente do HTTP (o cliente pergunta, o servidor responde), aqui o servidor
toma a iniciativa de avisar os clientes, sem que eles precisem perguntar.

V3: cada serviço é um processo próprio e tem a sua central (``app.state.central``),
com as mensagens do seu domínio: Catálogo avisa sobre livros e exemplares,
Usuários sobre usuários e Empréstimos sobre empréstimos e devoluções.

Login: a conexão exige o token de sessão (``/ws/eventos?token=...``) e cada
mensagem só vai para quem pode vê-la. Um aluno recebe os avisos do acervo e dos
próprios empréstimos; o bibliotecário recebe tudo.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder

from backend.autenticacao import Sessao, TokenInvalido, ler_token
from backend.origens import origem_permitida


logger = logging.getLogger("booknet.eventos")
router = APIRouter(tags=["Eventos"])


class CentralDeEventos:
    """Mantém as conexões abertas e envia cada mensagem a todas elas (broadcast)."""

    # Tudo roda na mesma thread do event loop: alterações no conjunto entre dois
    # "await" não se intercalam, então não é preciso trava.
    def __init__(self) -> None:
        self._conexoes: dict[WebSocket, Sessao] = {}

    @property
    def total(self) -> int:
        return len(self._conexoes)

    async def conectar(self, websocket: WebSocket, sessao: Sessao) -> None:
        await websocket.accept()
        self._conexoes[websocket] = sessao
        await websocket.send_json(self.montar_mensagem("conectado", {"conexoes": self.total}))
        await self.publicar("conexoes.alteradas", {"conexoes": self.total})

    async def desconectar(self, websocket: WebSocket) -> None:
        self._conexoes.pop(websocket, None)
        await self.publicar("conexoes.alteradas", {"conexoes": self.total})

    async def publicar(
        self,
        tipo: str,
        dados: dict[str, Any],
        dono_id: int | None = None,
        somente_bibliotecarios: bool = False,
    ) -> None:
        """``dono_id``: só o bibliotecário e o próprio usuário recebem (ex.: empréstimos).
        ``somente_bibliotecarios``: só bibliotecários recebem (ex.: cadastro de usuários)."""
        mensagem = self.montar_mensagem(tipo, dados)
        for websocket, sessao in list(self._conexoes.items()):
            if not sessao.bibliotecario and (
                somente_bibliotecarios or (dono_id is not None and dono_id != sessao.usuario_id)
            ):
                continue
            try:
                await websocket.send_json(mensagem)
            except Exception:
                # Conexão que caiu sem avisar: removida para não travar os demais envios.
                self._conexoes.pop(websocket, None)
                logger.info("Conexão de eventos encerrada durante o envio.")

    @staticmethod
    def montar_mensagem(tipo: str, dados: dict[str, Any]) -> dict[str, Any]:
        return {
            "tipo": tipo,
            "dados": jsonable_encoder(dados),
            "momento": datetime.now(timezone.utc).isoformat(),
        }


def obter_central(request: Request) -> CentralDeEventos:
    return request.app.state.central


Central = Annotated[CentralDeEventos, Depends(obter_central)]


@router.websocket("/ws/eventos")
async def canal_de_eventos(websocket: WebSocket) -> None:
    if not origem_permitida(websocket.headers.get("origin")):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        sessao = ler_token(websocket.query_params.get("token", ""))
    except TokenInvalido:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    central: CentralDeEventos = websocket.app.state.central
    await central.conectar(websocket, sessao)
    try:
        while True:
            # O cliente pode mandar "ping" para checar se o canal continua vivo.
            if await websocket.receive_text() == "ping":
                await websocket.send_json(central.montar_mensagem("pong", {}))
    except WebSocketDisconnect:
        pass
    finally:
        await central.desconectar(websocket)
