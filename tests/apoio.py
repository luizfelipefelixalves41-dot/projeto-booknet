"""Estrutura compartilhada dos testes: API ASGI e SQLite exclusivamente em memória.

O carregamento do .env é substituído antes de importar o backend, e qualquer
tentativa de conexão psycopg é bloqueada. Nenhuma migration é aplicada; cada
teste recebe um banco novo e descartável.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

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
    from backend import database
    from backend.dependencies.database import get_db
    from backend.main import app
    from backend.models.base import Base


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


async def _requisicao_asgi(method, target, payload=None, headers=None):
    """Executa uma requisição HTTP no próprio processo, sem sockets."""
    endereco = urlsplit(target)
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
            (nome.lower().encode("ascii"), valor.encode("ascii"))
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
        self._contador_livros = 0
        self._contador_exemplares = 0
        self._contador_usuarios = 0

    def requisicao(self, method, target, payload=None, headers=None):
        return asyncio.run(_requisicao_asgi(method, target, payload, headers))

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
