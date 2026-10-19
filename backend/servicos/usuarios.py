"""Serviço de Usuários · porta 8002.

    uvicorn backend.servicos.usuarios:app --port 8002
"""

from backend.routers.usuarios import router
from backend.servicos.base import criar_servico

app = criar_servico(
    nome="usuarios",
    titulo="Serviço de Usuários",
    descricao="Alunos e bibliotecários. Dono da tabela usuarios.",
    routers=[router],
    tags=[{"name": "Usuários", "description": "Alunos e bibliotecários."}],
)
