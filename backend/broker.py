"""V6: intermediário de mensagens (Redis Pub/Sub) entre réplicas de um serviço.

O problema
----------
Com o orquestrador mantendo 2 réplicas do Catálogo, o navegador de uma pessoa
pode estar conectado ao WebSocket da réplica A enquanto o cadastro de um livro
é atendido pela réplica B. A central de eventos da réplica B não conhece as
conexões da réplica A, e o aviso "ao vivo" se perderia.

A solução
---------
Cada réplica publica seus eventos em um canal do Redis e todas as réplicas
assinam esse canal. Quem recebe repassa às conexões que tem:

    réplica B ── publica ──▶ Redis (canal booknet:catalogo) ──▶ réplica A ──▶ navegador
                                                             └─▶ réplica B ──▶ outros navegadores

Sem ``BOOKNET_REDIS_URL`` (testes, Render com uma instância por serviço), cada
serviço entrega os eventos diretamente, como na V2.
"""

from typing import AsyncIterator, Protocol

from backend import config


class Broker(Protocol):
    async def publicar(self, canal: str, mensagem: str) -> None: ...

    def escutar(self, canal: str) -> AsyncIterator[str]: ...

    async def fechar(self) -> None: ...


class BrokerRedis:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # só é necessário quando há Redis configurado

        self._cliente = redis.from_url(url, decode_responses=True)

    async def publicar(self, canal: str, mensagem: str) -> None:
        await self._cliente.publish(canal, mensagem)

    async def escutar(self, canal: str) -> AsyncIterator[str]:
        assinatura = self._cliente.pubsub()
        await assinatura.subscribe(canal)
        try:
            async for item in assinatura.listen():
                if item.get("type") == "message":
                    yield item["data"]
        finally:
            await assinatura.aclose()

    async def fechar(self) -> None:
        await self._cliente.aclose()


def criar_broker() -> Broker | None:
    return BrokerRedis(config.REDIS_URL) if config.REDIS_URL else None
