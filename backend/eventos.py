"""V2: mensagens em tempo real por WebSocket.

Cada cliente abre uma conexão persistente (socket) com ``/ws/eventos``. Quando
algo muda no acervo, a API publica uma mensagem JSON para todas as conexões:

    {"tipo": "emprestimo.criado", "dados": {...}, "momento": "2026-10-19T18:45:51Z"}

Diferente do HTTP (o cliente pergunta, o servidor responde), aqui o servidor
toma a iniciativa de avisar os clientes, sem que eles precisem perguntar.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder

from backend.origens import origem_permitida


logger = logging.getLogger("booknet.eventos")
router = APIRouter(tags=["Eventos"])


class CentralDeEventos:
    """Mantém as conexões abertas e envia cada mensagem a todas elas (broadcast)."""

    # Tudo roda na mesma thread do event loop: alterações no conjunto entre dois
    # "await" não se intercalam, então não é preciso trava.
    def __init__(self) -> None:
        self._conexoes: set[WebSocket] = set()

    @property
    def total(self) -> int:
        return len(self._conexoes)

    async def conectar(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._conexoes.add(websocket)
        await websocket.send_json(self.montar_mensagem("conectado", {"conexoes": self.total}))
        await self.publicar("conexoes.alteradas", {"conexoes": self.total})

    async def desconectar(self, websocket: WebSocket) -> None:
        self._conexoes.discard(websocket)
        await self.publicar("conexoes.alteradas", {"conexoes": self.total})

    async def publicar(self, tipo: str, dados: dict[str, Any]) -> None:
        mensagem = self.montar_mensagem(tipo, dados)
        for websocket in list(self._conexoes):
            try:
                await websocket.send_json(mensagem)
            except Exception:
                # Conexão que caiu sem avisar: removida para não travar os demais envios.
                self._conexoes.discard(websocket)
                logger.info("Conexão de eventos encerrada durante o envio.")

    @staticmethod
    def montar_mensagem(tipo: str, dados: dict[str, Any]) -> dict[str, Any]:
        return {
            "tipo": tipo,
            "dados": jsonable_encoder(dados),
            "momento": datetime.now(timezone.utc).isoformat(),
        }


central = CentralDeEventos()


@router.websocket("/ws/eventos")
async def canal_de_eventos(websocket: WebSocket) -> None:
    if not origem_permitida(websocket.headers.get("origin")):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await central.conectar(websocket)
    try:
        while True:
            # O cliente pode mandar "ping" para checar se o canal continua vivo.
            if await websocket.receive_text() == "ping":
                await websocket.send_json(central.montar_mensagem("pong", {}))
    except WebSocketDisconnect:
        pass
    finally:
        await central.desconectar(websocket)
