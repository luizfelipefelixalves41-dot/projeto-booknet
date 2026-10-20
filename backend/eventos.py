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

import asyncio
import json
import logging
import socket
from contextlib import suppress
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder

from backend.autenticacao import Sessao, TokenInvalido, ler_token
from backend.origens import origem_permitida


logger = logging.getLogger("booknet.eventos")
# V6: nome da réplica que atende a conexão (aparece na mensagem de boas-vindas).
INSTANCIA = socket.gethostname()
router = APIRouter(tags=["Eventos"])


class CentralDeEventos:
    """Mantém as conexões abertas e envia cada mensagem a todas elas (broadcast).

    V6: com um intermediário (Redis), ``publicar`` manda o evento para o canal do
    serviço e cada réplica, ao recebê-lo, entrega às suas próprias conexões.
    """

    # Tudo roda na mesma thread do event loop: alterações no conjunto entre dois
    # "await" não se intercalam, então não é preciso trava.
    def __init__(self, servico: str = "booknet", broker=None) -> None:
        self._conexoes: dict[WebSocket, Sessao] = {}
        self.canal = f"booknet:{servico}"
        self.broker = broker
        self._escuta: asyncio.Task | None = None

    @property
    def total(self) -> int:
        return len(self._conexoes)

    async def iniciar(self) -> None:
        if self.broker is not None and self._escuta is None:
            self._escuta = asyncio.create_task(self._escutar_broker())

    async def encerrar(self) -> None:
        if self._escuta is not None:
            self._escuta.cancel()
            with suppress(asyncio.CancelledError):
                await self._escuta
            self._escuta = None
        if self.broker is not None:
            await self.broker.fechar()

    async def _escutar_broker(self) -> None:
        espera = 1
        while True:
            try:
                async for bruta in self.broker.escutar(self.canal):
                    espera = 1
                    envelope = json.loads(bruta)
                    await self._entregar(
                        envelope["mensagem"], envelope["dono_id"], envelope["somente_bibliotecarios"]
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                # V5 aplicado ao V6: Redis fora do ar não derruba o serviço; tenta de novo.
                logger.warning("Intermediário de mensagens indisponível; nova tentativa em %ss.", espera)
                await asyncio.sleep(espera)
                espera = min(espera * 2, 30)

    async def conectar(self, websocket: WebSocket, sessao: Sessao) -> None:
        await websocket.accept()
        self._conexoes[websocket] = sessao
        await websocket.send_json(
            self.montar_mensagem("conectado", {"conexoes": self.total, "instancia": INSTANCIA})
        )
        await self._entregar(self.montar_mensagem("conexoes.alteradas", {"conexoes": self.total}))

    async def desconectar(self, websocket: WebSocket) -> None:
        self._conexoes.pop(websocket, None)
        await self._entregar(self.montar_mensagem("conexoes.alteradas", {"conexoes": self.total}))

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
        if self.broker is not None:
            envelope = {"mensagem": mensagem, "dono_id": dono_id, "somente_bibliotecarios": somente_bibliotecarios}
            try:
                await self.broker.publicar(self.canal, json.dumps(envelope))
                return
            except Exception:
                logger.warning("Intermediário de mensagens indisponível; entregando só nesta réplica.")
        await self._entregar(mensagem, dono_id, somente_bibliotecarios)

    async def _entregar(
        self, mensagem: dict[str, Any], dono_id: int | None = None, somente_bibliotecarios: bool = False
    ) -> None:
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
