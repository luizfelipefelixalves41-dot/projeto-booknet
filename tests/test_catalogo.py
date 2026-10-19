"""Catálogo: API ASGI e integridade em SQLite exclusivamente em memória.

Execução: .venv\\Scripts\\python.exe -m unittest discover -s tests -v

Não requer pytest ou httpx. A estrutura isolada fica em tests/apoio.py: o .env
não é carregado e qualquer tentativa de conexão psycopg é bloqueada.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from tests.apoio import BancoIsoladoTestCase, database, get_db
from backend.models.exemplar import Exemplar
from backend.models.livro import Livro


class CatalogoTestes(BancoIsoladoTestCase):
    def test_api_inicia_e_preserva_identificacao(self):
        resposta = self.requisicao("GET", "/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json(), {"projeto": "BookNet", "status": "online", "versao": "V2"}
        )

    def test_health_preservado(self):
        resposta = self.requisicao("GET", "/health")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})

    def test_health_database_online_somente_no_sqlite_isolado(self):
        resposta = self.requisicao("GET", "/health/database")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"database": "online"})

    def test_health_database_offline_tem_resposta_segura(self):
        with patch.object(self.engine, "connect", side_effect=RuntimeError("DADO_INTERNO")):
            resposta = self.requisicao("GET", "/health/database")
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json(), {"database": "offline"})
        self.assertNotIn("DADO_INTERNO", resposta.text)

    def test_swagger_e_openapi_incluem_catalogo_sem_delete(self):
        self.assertEqual(self.requisicao("GET", "/docs").status_code, 200)
        resposta = self.requisicao("GET", "/openapi.json")
        self.assertEqual(resposta.status_code, 200)
        caminhos = resposta.json()["paths"]
        for rota in ("/", "/health", "/health/database"):
            self.assertIn("get", caminhos[rota])
        for rota, metodos in {
            "/livros": {"get", "post"},
            "/livros/{livro_id}": {"get", "put"},
            "/livros/{livro_id}/exemplares": {"get", "post"},
        }.items():
            self.assertEqual(set(caminhos[rota]), metodos)
            for metodo in metodos:
                self.assertIn("Catálogo", caminhos[rota][metodo]["tags"])

    def test_criacao_valida_normaliza_texto_e_preserva_isbn_string(self):
        livro = self.criar_livro(
            titulo="  Redes de Computadores  ", autor="  André  ", isbn="  0000123456789  "
        )
        self.assertEqual(livro["titulo"], "Redes de Computadores")
        self.assertEqual(livro["autor"], "André")
        self.assertEqual(livro["isbn"], "0000123456789")
        self.assertIs(livro["ativo"], True)
        self.assertIsInstance(livro["id"], int)
        self.assertTrue(livro["criado_em"])
        self.assertTrue(livro["atualizado_em"])

    def test_criacao_rejeita_campos_invalidos(self):
        casos = [
            ("titulo", ""), ("titulo", "   "), ("titulo", "x" * 256),
            ("titulo", None), ("titulo", 42),
            ("autor", ""), ("autor", "   "), ("autor", "x" * 256),
            ("autor", None), ("autor", 42),
            ("isbn", ""), ("isbn", "   "), ("isbn", "1" * 21),
            ("isbn", None), ("isbn", 123),
        ]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                dados = {"titulo": "Livro", "autor": "Autor", "isbn": "001234"}
                dados[campo] = valor
                self.assertEqual(self.requisicao("POST", "/livros", dados).status_code, 422)
        self.assertEqual(self.requisicao("GET", "/livros").json(), [])

    def test_criacao_rejeita_campos_ausentes_e_extras(self):
        base = {"titulo": "Livro", "autor": "Autor", "isbn": "001234"}
        for campo in base:
            with self.subTest(campo=campo):
                dados = {chave: valor for chave, valor in base.items() if chave != campo}
                self.assertEqual(self.requisicao("POST", "/livros", dados).status_code, 422)
        self.assertEqual(
            self.requisicao("POST", "/livros", {**base, "id": 999}).status_code, 422
        )

    def test_limites_maximos_validos(self):
        livro = self.criar_livro(titulo="t" * 255, autor="a" * 255, isbn="0" * 20)
        exemplar = self.criar_exemplar(livro["id"], codigo_tombo="T" * 50)
        self.assertEqual(len(exemplar["codigo_tombo"]), 50)

    def test_isbn_duplicado_retorna_conflito_e_preserva_livro(self):
        livro = self.criar_livro(isbn="000123")
        resposta = self.requisicao(
            "POST", "/livros", {"titulo": "Outro", "autor": "Outra", "isbn": "000123"}
        )
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(self.requisicao("GET", "/livros").json(), [livro])
        self.assertNotIn("INSERT", resposta.text)
        self.assertNotIn("UNIQUE constraint", resposta.text)

    def test_listagem_vazia_e_ordenada(self):
        self.assertEqual(self.requisicao("GET", "/livros").json(), [])
        livros = [self.criar_livro(titulo=titulo) for titulo in ("Z", "A", "M")]
        resposta = self.requisicao("GET", "/livros")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual([item["id"] for item in resposta.json()], [item["id"] for item in livros])

    def test_listagem_exibe_apenas_ativos_e_consulta_direta_inclui_inativo(self):
        ativo = self.criar_livro()
        inativo = self.criar_livro(ativo=False)
        self.assertEqual(self.requisicao("GET", "/livros").json(), [ativo])
        self.assertEqual(self.requisicao("GET", f"/livros/{inativo['id']}").json(), inativo)

    def test_consulta_por_id_e_recurso_ausente(self):
        livro = self.criar_livro()
        resposta = self.requisicao("GET", f"/livros/{livro['id']}")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), livro)
        inexistente = self.requisicao("GET", "/livros/99999")
        self.assertEqual(inexistente.status_code, 404)
        self.assertIsInstance(inexistente.json()["detail"], str)

    def test_atualizacao_persiste_dados_e_inativacao(self):
        livro = self.criar_livro()
        dados = {"titulo": " Novo título ", "autor": " Nova autora ", "isbn": "000222", "ativo": False}
        resposta = self.requisicao("PUT", f"/livros/{livro['id']}", dados)
        self.assertEqual(resposta.status_code, 200)
        atualizado = resposta.json()
        self.assertEqual(atualizado["id"], livro["id"])
        self.assertEqual(atualizado["titulo"], "Novo título")
        self.assertEqual(atualizado["autor"], "Nova autora")
        self.assertEqual(atualizado["isbn"], "000222")
        self.assertIs(atualizado["ativo"], False)
        self.assertEqual(atualizado["criado_em"], livro["criado_em"])
        self.assertTrue(atualizado["atualizado_em"])
        self.assertEqual(self.requisicao("GET", f"/livros/{livro['id']}").json(), atualizado)
        self.assertEqual(self.requisicao("GET", "/livros").json(), [])

    def test_atualizacao_inexistente_retorna_404(self):
        resposta = self.requisicao(
            "PUT", "/livros/99999", {"titulo": "Novo", "autor": "Autor", "isbn": "000111"}
        )
        self.assertEqual(resposta.status_code, 404)

    def test_atualizacao_rejeita_isbn_conflitante_e_faz_rollback(self):
        primeiro = self.criar_livro(isbn="000111")
        segundo = self.criar_livro(isbn="000222")
        resposta = self.requisicao(
            "PUT", f"/livros/{segundo['id']}",
            {"titulo": "Alterado", "autor": "Outro", "isbn": primeiro["isbn"]},
        )
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(self.requisicao("GET", f"/livros/{segundo['id']}").json(), segundo)

    def test_atualizacao_exige_campos_completos_e_validos(self):
        livro = self.criar_livro()
        for dados in (
            {"titulo": "Parcial"},
            {"titulo": " ", "autor": "Autor", "isbn": "000111"},
            {"titulo": "Título", "autor": "Autor", "isbn": 123},
        ):
            with self.subTest(dados=dados):
                self.assertEqual(
                    self.requisicao("PUT", f"/livros/{livro['id']}", dados).status_code, 422
                )

    def test_criacao_de_exemplar_e_relacionamento(self):
        livro = self.criar_livro()
        exemplar = self.criar_exemplar(livro["id"], codigo_tombo="  ACERVO-001  ")
        self.assertEqual(exemplar["livro_id"], livro["id"])
        self.assertEqual(exemplar["codigo_tombo"], "ACERVO-001")
        self.assertEqual(exemplar["status"], "DISPONIVEL")
        self.assertTrue(exemplar["criado_em"])
        with self.sessoes() as sessao:
            registro = sessao.scalar(
                select(Exemplar)
                .where(Exemplar.id == exemplar["id"])
                .options(selectinload(Exemplar.livro).selectinload(Livro.exemplares))
            )
            self.assertEqual(registro.livro.id, livro["id"])
            self.assertEqual([item.id for item in registro.livro.exemplares], [exemplar["id"]])

    def test_exemplares_listados_apenas_no_livro_correto(self):
        primeiro = self.criar_livro()
        segundo = self.criar_livro()
        self.assertEqual(self.requisicao("GET", f"/livros/{primeiro['id']}/exemplares").json(), [])
        esperado = self.criar_exemplar(primeiro["id"])
        self.criar_exemplar(segundo["id"])
        resposta = self.requisicao("GET", f"/livros/{primeiro['id']}/exemplares")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), [esperado])

    def test_tombo_duplicado_entre_livros_retorna_409(self):
        primeiro = self.criar_livro()
        segundo = self.criar_livro()
        self.criar_exemplar(primeiro["id"], codigo_tombo="UNICO-001")
        resposta = self.requisicao(
            "POST", f"/livros/{segundo['id']}/exemplares", {"codigo_tombo": "UNICO-001"}
        )
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(self.requisicao("GET", f"/livros/{segundo['id']}/exemplares").json(), [])

    def test_exemplares_de_livro_inexistente_retornam_404(self):
        self.assertEqual(self.requisicao("GET", "/livros/99999/exemplares").status_code, 404)
        self.assertEqual(
            self.requisicao("POST", "/livros/99999/exemplares", {"codigo_tombo": "T-001"}).status_code,
            404,
        )

    def test_exemplar_rejeita_dados_invalidos(self):
        livro = self.criar_livro()
        for dados in (
            {}, {"codigo_tombo": ""}, {"codigo_tombo": "   "},
            {"codigo_tombo": "T" * 51}, {"codigo_tombo": 123},
            {"codigo_tombo": None}, {"codigo_tombo": "T-001", "status": "PERDIDO"},
            {"codigo_tombo": "T-001", "livro_id": 99999},
        ):
            with self.subTest(dados=dados):
                resposta = self.requisicao("POST", f"/livros/{livro['id']}/exemplares", dados)
                self.assertEqual(resposta.status_code, 422)

    def test_exemplar_nasce_disponivel_e_status_emprestado_e_rejeitado(self):
        livro = self.criar_livro()
        self.assertEqual(self.criar_exemplar(livro["id"], status="DISPONIVEL")["status"], "DISPONIVEL")
        resposta = self.requisicao(
            "POST", f"/livros/{livro['id']}/exemplares",
            {"codigo_tombo": "T-EMP", "status": "EMPRESTADO"},
        )
        self.assertEqual(resposta.status_code, 422)

    def test_consulta_de_exemplar_por_id(self):
        livro = self.criar_livro()
        exemplar = self.criar_exemplar(livro["id"])
        resposta = self.requisicao("GET", f"/exemplares/{exemplar['id']}")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), exemplar)
        self.assertEqual(self.requisicao("GET", "/exemplares/99999").status_code, 404)

    def test_paginacao_aplica_skip_limit_e_limite_padrao(self):
        livros = [self.criar_livro() for _ in range(22)]
        self.assertEqual(len(self.requisicao("GET", "/livros").json()), 20)
        resposta = self.requisicao("GET", "/livros?skip=2&limit=3")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual([item["id"] for item in resposta.json()], [item["id"] for item in livros[2:5]])
        self.assertEqual(self.requisicao("GET", "/livros?skip=99&limit=1").json(), [])

    def test_paginacao_rejeita_valores_fora_dos_limites(self):
        for consulta in ("skip=-1", "limit=0", "limit=101", "skip=texto", "limit=texto"):
            with self.subTest(consulta=consulta):
                self.assertEqual(self.requisicao("GET", f"/livros?{consulta}").status_code, 422)

    def test_busca_titulo_autor_isbn_sem_distinguir_maiusculas(self):
        livro = self.criar_livro(titulo="Redes de Computadores", autor="Autora Especial", isbn="0009876543210")
        self.criar_livro(titulo="Outro assunto", autor="Pessoa", isbn="111111")
        for termo in ("rEdEs", "eSpEcIaL", "987654"):
            with self.subTest(termo=termo):
                resposta = self.requisicao("GET", "/livros?" + urlencode({"q": termo}))
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.json(), [livro])

    def test_busca_nao_inclui_inativos(self):
        self.criar_livro(titulo="Oculto", ativo=False)
        self.assertEqual(self.requisicao("GET", "/livros?q=Oculto").json(), [])

    def test_busca_trata_curingas_e_sql_como_texto_literal(self):
        especial = self.criar_livro(titulo="100% Livro_especial")
        self.criar_livro(titulo="Livro comum")
        for termo in ("%", "_"):
            with self.subTest(termo=termo):
                self.assertEqual(
                    self.requisicao("GET", "/livros?" + urlencode({"q": termo})).json(), [especial]
                )
        resposta = self.requisicao("GET", "/livros?" + urlencode({"q": "' OR 1=1 --"}))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), [])
        self.assertEqual(len(self.requisicao("GET", "/livros").json()), 2)

    def test_cors_preserva_origens_locais_e_bloqueia_origem_nao_permitida(self):
        for origem in (
            "http://localhost:8080", "http://127.0.0.1:8080",
            "http://localhost:5500", "http://127.0.0.1:5500",
            # Rede local do laboratório: cliente em outra máquina.
            "http://192.168.0.15:8080", "http://10.0.5.20:8080", "http://172.20.1.3:5500",
        ):
            with self.subTest(origem=origem):
                resposta = self.requisicao("GET", "/health", headers={"origin": origem})
                self.assertEqual(resposta.headers.get("access-control-allow-origin"), origem)
        for origem in (
            "https://nao-permitido.invalid", "http://8.8.8.8:8080",
            "http://192.168.0.10:3000", "http://192.168.0.10.evil.com:8080",
        ):
            with self.subTest(origem=origem):
                resposta = self.requisicao("GET", "/health", headers={"origin": origem})
                self.assertNotIn("access-control-allow-origin", resposta.headers)
        preflight = self.requisicao(
            "OPTIONS", "/livros", headers={
                "origin": "http://localhost:8080", "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            },
        )
        self.assertEqual(preflight.status_code, 200)

    def test_falha_operacional_retorna_503_sem_detalhes_em_resposta_ou_logs(self):
        interno = "DADO_INTERNO_NAO_PUBLICAR"
        erro = OperationalError("SQL_INTERNO", {"dado": interno}, RuntimeError(interno))
        with patch.object(Session, "scalars", side_effect=erro), self.assertLogs(level="WARNING") as logs:
            resposta = self.requisicao("GET", "/livros")
        self.assertEqual(resposta.status_code, 503)
        for conteudo in (resposta.text, "\n".join(logs.output)):
            self.assertNotIn(interno, conteudo)
            self.assertNotIn("SQL_INTERNO", conteudo)
            self.assertNotIn("Traceback", conteudo)

    def test_erro_sql_inesperado_retorna_500_seguro(self):
        interno = "DADO_INTERNO_NAO_PUBLICAR"
        with (
            patch.object(Session, "get", side_effect=SQLAlchemyError(interno)),
            self.assertLogs(level="ERROR") as logs,
        ):
            resposta = self.requisicao("GET", "/livros/1")
        self.assertEqual(resposta.status_code, 500)
        self.assertNotIn(interno, resposta.text)
        self.assertNotIn(interno, "\n".join(logs.output))

    def test_fallback_inesperado_omite_detalhes_e_preserva_cors(self):
        interno = "DADO_INTERNO_NAO_PUBLICAR"
        origem = "http://localhost:8080"
        with (
            patch.object(Session, "get", side_effect=RuntimeError(interno)),
            self.assertLogs(level="ERROR") as logs,
        ):
            resposta = self.requisicao("GET", "/livros/1", headers={"origin": origem})
        self.assertEqual(resposta.status_code, 500)
        self.assertEqual(resposta.headers.get("access-control-allow-origin"), origem)
        self.assertIsInstance(resposta.json()["detail"], str)
        for conteudo in (resposta.text, "\n".join(logs.output)):
            self.assertNotIn(interno, conteudo)
            self.assertNotIn("Traceback", conteudo)

    def test_falha_no_commit_nao_persiste_e_proxima_requisicao_funciona(self):
        erro = OperationalError("SQL_INTERNO", {}, RuntimeError("DADO_INTERNO"))
        with patch.object(Session, "commit", side_effect=erro), self.assertLogs(level="WARNING"):
            resposta = self.requisicao(
                "POST", "/livros", {"titulo": "Livro", "autor": "Autor", "isbn": "000111"}
            )
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(self.requisicao("GET", "/livros").json(), [])
        self.criar_livro(isbn="000111")

    def test_dependency_cria_e_fecha_sessao_por_requisicao(self):
        primeira = Mock(spec=Session)
        segunda = Mock(spec=Session)
        with patch.object(database, "SessionLocal", side_effect=[primeira, segunda]) as fabrica:
            for esperada in (primeira, segunda):
                gerador = get_db()
                self.assertIs(next(gerador), esperada)
                with self.assertRaises(StopIteration):
                    next(gerador)
                esperada.close.assert_called_once()
            self.assertEqual(fabrica.call_count, 2)

    def test_dependency_faz_rollback_e_fecha_apos_excecao(self):
        sessao = Mock(spec=Session)
        with patch.object(database, "SessionLocal", return_value=sessao):
            gerador = get_db()
            self.assertIs(next(gerador), sessao)
            with self.assertRaises(SQLAlchemyError):
                gerador.throw(SQLAlchemyError("Falha simulada"))
        sessao.rollback.assert_called_once()
        sessao.close.assert_called_once()

    def test_banco_protege_campos_de_livro_sem_pydantic(self):
        casos = [
            {"titulo": ""}, {"titulo": "   "}, {"titulo": None}, {"titulo": "t" * 256},
            {"autor": ""}, {"autor": "   "}, {"autor": None}, {"autor": "a" * 256},
            {"isbn": ""}, {"isbn": "   "}, {"isbn": None}, {"isbn": "0" * 21},
            {"ativo": None},
        ]
        for alteracoes in casos:
            with self.subTest(alteracoes=alteracoes), self.engine.connect() as conexao:
                dados = {"titulo": "Livro", "autor": "Autor", "isbn": "000111", "ativo": True}
                dados.update(alteracoes)
                with self.assertRaises(IntegrityError):
                    conexao.execute(insert(Livro.__table__).values(**dados))
                conexao.rollback()

    def test_banco_protege_isbn_unico_sem_pydantic(self):
        self.criar_livro(isbn="000111")
        with self.engine.connect() as conexao:
            with self.assertRaises(IntegrityError):
                conexao.execute(insert(Livro.__table__).values(titulo="Outro", autor="Autor", isbn="000111"))
            conexao.rollback()

    def test_banco_protege_exemplar_tombo_status_e_fk_sem_pydantic(self):
        livro = self.criar_livro()
        casos = [
            {"codigo_tombo": ""}, {"codigo_tombo": "   "},
            {"codigo_tombo": None}, {"codigo_tombo": "T" * 51},
            {"status": "PERDIDO"}, {"status": None},
            {"livro_id": None}, {"livro_id": 99999},
        ]
        comando = text(
            "INSERT INTO exemplares (livro_id, codigo_tombo, status) "
            "VALUES (:livro_id, :codigo_tombo, :status)"
        )
        for alteracoes in casos:
            with self.subTest(alteracoes=alteracoes), self.engine.connect() as conexao:
                dados = {"livro_id": livro["id"], "codigo_tombo": "T-001", "status": "DISPONIVEL"}
                dados.update(alteracoes)
                with self.assertRaises(IntegrityError):
                    conexao.execute(comando, dados)
                conexao.rollback()

    def test_banco_protege_tombo_unico_sem_pydantic(self):
        livro = self.criar_livro()
        self.criar_exemplar(livro["id"], codigo_tombo="T-001")
        with self.engine.connect() as conexao:
            with self.assertRaises(IntegrityError):
                conexao.execute(
                    text("INSERT INTO exemplares (livro_id, codigo_tombo, status) VALUES (:id, :tombo, :status)"),
                    {"id": livro["id"], "tombo": "T-001", "status": "DISPONIVEL"},
                )
            conexao.rollback()

    def test_relacionamento_impede_cascata_de_exclusao(self):
        with self.engine.connect() as conexao:
            chaves = conexao.execute(text("PRAGMA foreign_key_list(exemplares)")).mappings().all()
            self.assertEqual(conexao.execute(text("PRAGMA foreign_keys")).scalar_one(), 1)
        fk_livro = next(item for item in chaves if item["from"] == "livro_id")
        self.assertEqual(fk_livro["table"], "livros")
        self.assertIn(fk_livro["on_delete"], {"RESTRICT", "NO ACTION"})
        self.assertNotIn("delete", Livro.exemplares.property.cascade)
        self.assertNotIn("delete-orphan", Livro.exemplares.property.cascade)


if __name__ == "__main__":
    unittest.main()
