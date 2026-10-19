"""Estrutura compartilhada dos testes: três serviços ASGI e SQLite exclusivamente em memória.

O carregamento do .env é substituído antes de importar o backend, e qualquer
tentativa de conexão psycopg é bloqueada. Nenhuma migration é aplicada; cada
teste recebe um banco novo e descartável.

V3: os serviços de Catálogo, Usuários e Empréstimos rodam no mesmo processo de
teste. As chamadas HTTP do Serviço de Empréstimos usam o cliente httpx real, com
um transporte simulado que entrega cada pedido ao serviço de destino. A lista
``self.falhas`` permite simular serviço fora do ar ou lento.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import anyio.from_thread
import httpx
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# URL fictícia, sem usuário ou senha; nunca usada para abrir uma conexão.
_URL_TESTE = URL.create(
    "postgresql+psycopg", host="127.0.0.1", database="booknet_test"
).render_as_string(hide_password=True)

with (
    patch("dotenv.load_dotenv", return_value=False),
    patch.dict(os.environ, {"DATABASE_URL": _URL_TESTE}),
    patch(
        "psycopg.connect",
        side_effect=AssertionError("Os testes não podem conectar ao PostgreSQL."),
    ),
):
    from backend import config, database
    from backend.dependencies.database import get_db
    from backend.eventos import CentralDeEventos
    from backend.models.base import Base
    from backend.servicos.catalogo import app as app_catalogo
    from backend.servicos.emprestimos import app as app_emprestimos
    from backend.servicos.usuarios import app as app_usuarios
    from backend.servicos_remotos import ServicosRemotos, obter_servicos_remotos

APPS = {"catalogo": app_catalogo, "usuarios": app_usuarios, "emprestimos": app_emprestimos}
PORTAS = {8001: app_catalogo, 8002: app_usuarios, 8003: app_emprestimos}


def app_da_rota(caminho: str):
    """Escolhe o serviço dono da rota, como o Cliente Web faz pelo prefixo."""
    if caminho.startswith("/usuarios"):
        return app_usuarios
    if caminho.startswith(("/emprestimos", "/ws/")):
        return app_emprestimos
    return app_catalogo


@dataclass(frozen=True)
class Resposta:
    status_code: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self):
        return json.loads(self.body)


async def _requisicao_asgi(method, target, payload=None, headers=None, app=None, corpo=None):
    """Executa uma requisição HTTP no próprio processo, sem sockets."""
    endereco = urlsplit(target)
    app = app or app_da_rota(endereco.path)
    if corpo is None:
        corpo = json.dumps(payload).encode("utf-8") if payload is not None else b""
    cabecalhos = {"host": "testserver"}
    if payload is not None:
        cabecalhos["content-type"] = "application/json"
    cabecalhos.update(headers or {})
    escopo = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": endereco.path,
        "raw_path": endereco.path.encode("ascii"),
        "query_string": endereco.query.encode("ascii"),
        "root_path": "",
        "headers": [
            (nome.lower().encode("ascii"), valor.encode("latin-1"))
            for nome, valor in cabecalhos.items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    mensagens = []
    recebido = False

    async def receive():
        nonlocal recebido
        if not recebido:
            recebido = True
            return {"type": "http.request", "body": corpo, "more_body": False}
        await asyncio.sleep(0)
        return {"type": "http.disconnect"}

    async def send(message):
        mensagens.append(message)

    await app(escopo, receive, send)
    inicio = next(item for item in mensagens if item["type"] == "http.response.start")
    return Resposta(
        status_code=inicio["status"],
        headers={
            chave.decode("ascii"): valor.decode("latin-1")
            for chave, valor in inicio.get("headers", [])
        },
        body=b"".join(
            item.get("body", b"")
            for item in mensagens
            if item["type"] == "http.response.body"
        ),
    )


class BancoIsoladoTestCase(unittest.TestCase):
    def setUp(self):
        self.bloqueio_postgres = patch(
            "psycopg.connect",
            side_effect=AssertionError("Os testes não podem conectar ao PostgreSQL."),
        )
        self.conectar_postgres = self.bloqueio_postgres.start()
        self.addCleanup(self.bloqueio_postgres.stop)
        self.addCleanup(self.conectar_postgres.assert_not_called)
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def habilitar_chaves_estrangeiras(conexao, _registro):
            cursor = conexao.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.sessoes = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patch_engine = patch.object(database, "engine", self.engine)
        self.patch_sessoes = patch.object(database, "SessionLocal", self.sessoes)
        self.patch_engine.start()
        self.patch_sessoes.start()
        self.addCleanup(self.patch_engine.stop)
        self.addCleanup(self.patch_sessoes.stop)

        # Cada teste começa com centrais de eventos vazias, uma por serviço.
        for app in APPS.values():
            app.state.central = CentralDeEventos()

        # Comunicação entre serviços: httpx real com transporte simulado.
        self.falhas: list[tuple[str, Exception]] = []
        self.chamadas_remotas: list[str] = []
        cliente = httpx.Client(
            transport=httpx.MockTransport(self._entregar), timeout=config.TIMEOUT_SERVICOS
        )
        self.addCleanup(cliente.close)
        self.servicos = ServicosRemotos(cliente)
        app_emprestimos.dependency_overrides[obter_servicos_remotos] = lambda: self.servicos
        self.addCleanup(app_emprestimos.dependency_overrides.clear)

        self._contador_livros = 0
        self._contador_exemplares = 0
        self._contador_usuarios = 0

    def _entregar(self, pedido: httpx.Request) -> httpx.Response:
        """Transporte simulado: roda dentro da thread da rota de Empréstimos."""
        url = str(pedido.url)
        self.chamadas_remotas.append(f"{pedido.method} {pedido.url.path}")
        for trecho, erro in self.falhas:
            if trecho in url:
                raise erro
        destino = PORTAS[pedido.url.port]
        alvo = pedido.url.raw_path.decode("ascii")
        cabecalhos = {
            nome: valor for nome, valor in pedido.headers.items() if nome.lower() != "host"
        }
        resposta = anyio.from_thread.run(
            lambda: _requisicao_asgi(
                pedido.method, alvo, headers=cabecalhos, app=destino, corpo=pedido.content
            )
        )
        return httpx.Response(resposta.status_code, headers=resposta.headers, content=resposta.body)

    def simular_falha(self, trecho: str, erro: Exception) -> None:
        self.falhas.append((trecho, erro))

    def requisicao(self, method, target, payload=None, headers=None, servico=None):
        app = APPS[servico] if servico else None
        return asyncio.run(_requisicao_asgi(method, target, payload, headers, app=app))

    def criar_livro(self, **alteracoes):
        self._contador_livros += 1
        dados = {
            "titulo": "Sistemas Distribuídos",
            "autor": "Autora de Teste",
            "isbn": f"000{self._contador_livros:010d}",
        }
        dados.update(alteracoes)
        resposta = self.requisicao("POST", "/livros", dados)
        self.assertEqual(resposta.status_code, 201, resposta.text)
        return resposta.json()

    def criar_exemplar(self, livro_id, **alteracoes):
        self._contador_exemplares += 1
        dados = {"codigo_tombo": f"TOMBO-{self._contador_exemplares:04d}"}
        dados.update(alteracoes)
        resposta = self.requisicao("POST", f"/livros/{livro_id}/exemplares", dados)
        self.assertEqual(resposta.status_code, 201, resposta.text)
        return resposta.json()

    def criar_usuario(self, **alteracoes):
        self._contador_usuarios += 1
        dados = {
            "nome": "Aluna de Teste",
            "email": f"aluna{self._contador_usuarios}@booknet.test",
            "matricula": f"MAT-{self._contador_usuarios:04d}",
        }
        dados.update(alteracoes)
        resposta = self.requisicao("POST", "/usuarios", dados)
        self.assertEqual(resposta.status_code, 201, resposta.text)
        return resposta.json()
