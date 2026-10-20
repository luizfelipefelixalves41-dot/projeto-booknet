"""Serviço de Usuários · porta 8002.

    uvicorn backend.servicos.usuarios:app --port 8002
"""

from backend.routers.usuarios import router, router_auth
from backend.servicos.base import criar_servico

app = criar_servico(
    nome="usuarios",
    titulo="Serviço de Usuários",
    descricao="Alunos e bibliotecários. Dono da tabela usuarios.",
    routers=[router_auth, router],
    tags=[
        {"name": "Login", "description": "Entrar com matrícula e senha; recebe o token de sessão."},
        {"name": "Usuários", "description": "Alunos e bibliotecários."},
    ],
)
