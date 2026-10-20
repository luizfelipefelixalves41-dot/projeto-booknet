"""Serviço de Empréstimos · porta 8003.

    uvicorn backend.servicos.emprestimos:app --port 8003

Consulta o Serviço de Usuários (8002) e o Serviço de Catálogo (8001) por HTTP.
"""

import asyncio
from contextlib import asynccontextmanager, suppress

from backend import config
from backend.reconciliacao import reconciliar_periodicamente
from backend.routers.emprestimos import router, router_sistema
from backend.servicos.base import criar_servico


@asynccontextmanager
async def ciclo_de_vida(_app):
    """V5: a reconciliação roda em segundo plano enquanto o serviço estiver no ar."""
    tarefa = None
    if config.RECONCILIACAO_INTERVALO_SEGUNDOS > 0:
        tarefa = asyncio.create_task(reconciliar_periodicamente())
    yield
    if tarefa:
        tarefa.cancel()
        with suppress(asyncio.CancelledError):
            await tarefa


app = criar_servico(
    nome="emprestimos",
    titulo="Serviço de Empréstimos",
    descricao="Empréstimos e devoluções. Dono da tabela emprestimos; consulta Usuários "
    "e Catálogo por HTTP.",
    routers=[router, router_sistema],
    tags=[{"name": "Empréstimos", "description": "Empréstimos e devoluções de exemplares."}],
    lifespan=ciclo_de_vida,
)
