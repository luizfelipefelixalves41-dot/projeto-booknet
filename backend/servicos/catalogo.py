"""Serviço de Catálogo · porta 8001.

    uvicorn backend.servicos.catalogo:app --port 8001
"""

from backend.routers.catalogo import router, router_exemplares, router_interno
from backend.servicos.base import criar_servico

app = criar_servico(
    nome="catalogo",
    titulo="Serviço de Catálogo",
    descricao="Livros, exemplares e disponibilidade. Dono das tabelas livros e exemplares.",
    routers=[router, router_exemplares, router_interno],
    tags=[
        {"name": "Catálogo", "description": "Livros, exemplares e disponibilidade."},
        {
            "name": "Catálogo (interno)",
            "description": "Retirada e liberação de exemplares, chamadas pelo Serviço de "
            "Empréstimos com o cabeçalho X-Servico-Token.",
        },
    ],
)
