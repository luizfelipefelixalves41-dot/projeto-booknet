"""Serviço de Empréstimos · porta 8003.

    uvicorn backend.servicos.emprestimos:app --port 8003

Consulta o Serviço de Usuários (8002) e o Serviço de Catálogo (8001) por HTTP.
"""

from backend.routers.emprestimos import router
from backend.servicos.base import criar_servico

app = criar_servico(
    nome="emprestimos",
    titulo="Serviço de Empréstimos",
    descricao="Empréstimos e devoluções. Dono da tabela emprestimos; consulta Usuários "
    "e Catálogo por HTTP.",
    routers=[router],
    tags=[{"name": "Empréstimos", "description": "Empréstimos e devoluções de exemplares."}],
)
