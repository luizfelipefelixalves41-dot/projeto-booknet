"""Usuários, empréstimos e devoluções em SQLite exclusivamente em memória.

Execução: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

from datetime import date, timedelta
import unittest
from urllib.parse import urlencode

from sqlalchemy import insert, text, update
from sqlalchemy.exc import IntegrityError

from tests.apoio import BancoIsoladoTestCase
from backend.models.emprestimo import Emprestimo
from backend.models.usuario import Usuario


class UsuariosTestes(BancoIsoladoTestCase):
    def test_criacao_normaliza_dados_e_aplica_padroes(self):
        usuario = self.criar_usuario(
            nome="  João Henrique  ", email="  Joao@Booknet.TEST ", matricula=" 2026001 "
        )
        self.assertEqual(usuario["nome"], "João Henrique")
        self.assertEqual(usuario["email"], "joao@booknet.test")
        self.assertEqual(usuario["matricula"], "2026001")
        self.assertEqual(usuario["tipo"], "ALUNO")
        self.assertIs(usuario["ativo"], True)
        self.assertTrue(usuario["criado_em"])

    def test_criacao_aceita_bibliotecario(self):
        self.assertEqual(self.criar_usuario(tipo="BIBLIOTECARIO")["tipo"], "BIBLIOTECARIO")

    def test_criacao_rejeita_campos_invalidos(self):
        base = {"nome": "Nome", "email": "a@b.co", "matricula": "M1"}
        casos = [
            ("nome", ""), ("nome", "   "), ("nome", "x" * 256), ("nome", None), ("nome", 1),
            ("email", ""), ("email", "sem-arroba"), ("email", "a@b"), ("email", "a b@c.d"),
            ("matricula", ""), ("matricula", "x" * 31), ("matricula", 123),
            ("tipo", "PROFESSOR"), ("id", 99),
        ]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                dados = {**base, campo: valor}
                self.assertEqual(self.requisicao("POST", "/usuarios", dados).status_code, 422)
        self.assertEqual(self.requisicao("GET", "/usuarios").json(), [])

    def test_email_e_matricula_duplicados_retornam_409(self):
        self.criar_usuario(email="unico@booknet.test", matricula="M-1")
        for dados, mensagem in (
            ({"email": "UNICO@booknet.test", "matricula": "M-2"}, "E-mail já cadastrado."),
            ({"email": "outro@booknet.test", "matricula": "M-1"}, "Matrícula já cadastrada."),
        ):
            with self.subTest(dados=dados):
                resposta = self.requisicao("POST", "/usuarios", {"nome": "Outro", **dados})
                self.assertEqual(resposta.status_code, 409)
                self.assertEqual(resposta.json()["detail"], mensagem)
        self.assertEqual(len(self.requisicao("GET", "/usuarios").json()), 1)

    def test_listagem_busca_filtro_e_inativos(self):
        ana = self.criar_usuario(nome="Ana Souza", matricula="2026-A")
        bibliotecario = self.criar_usuario(nome="Carlos", tipo="BIBLIOTECARIO")
        inativo = self.criar_usuario(nome="Ana Inativa", ativo=False)
        self.assertEqual(self.requisicao("GET", "/usuarios").json(), [ana, bibliotecario])
        self.assertEqual(self.requisicao("GET", "/usuarios?q=ana").json(), [ana])
        self.assertEqual(self.requisicao("GET", "/usuarios?q=2026-a").json(), [ana])
        self.assertEqual(
            self.requisicao("GET", "/usuarios?tipo=BIBLIOTECARIO").json(), [bibliotecario]
        )
        self.assertEqual(self.requisicao("GET", f"/usuarios/{inativo['id']}").json(), inativo)
        self.assertEqual(self.requisicao("GET", "/usuarios/99999").status_code, 404)

    def test_atualizacao_substitui_dados_e_valida_unicidade(self):
        primeiro = self.criar_usuario()
        segundo = self.criar_usuario()
        dados = {"nome": "Novo Nome", "email": primeiro["email"], "matricula": "NOVA"}
        resposta = self.requisicao("PUT", f"/usuarios/{primeiro['id']}", dados)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.json()["nome"], "Novo Nome")
        self.assertEqual(resposta.json()["matricula"], "NOVA")
        conflito = self.requisicao(
            "PUT", f"/usuarios/{segundo['id']}", {**dados, "matricula": "OUTRA"}
        )
        self.assertEqual(conflito.status_code, 409)
        self.assertEqual(self.requisicao("GET", f"/usuarios/{segundo['id']}").json(), segundo)
        self.assertEqual(self.requisicao("PUT", "/usuarios/99999", dados).status_code, 404)

    def test_banco_protege_unicidade_e_tipo_sem_pydantic(self):
        self.criar_usuario(email="a@booknet.test", matricula="M-1")
        casos = [
            {"email": "a@booknet.test"}, {"matricula": "M-1"},
            {"tipo": "PROFESSOR"}, {"nome": "   "}, {"matricula": None},
        ]
        for alteracoes in casos:
            with self.subTest(alteracoes=alteracoes), self.engine.connect() as conexao:
                dados = {"nome": "N", "email": "b@booknet.test", "matricula": "M-2", "tipo": "ALUNO"}
                dados.update(alteracoes)
                with self.assertRaises(IntegrityError):
                    conexao.execute(
                        text(
                            "INSERT INTO usuarios (nome, email, matricula, tipo) "
                            "VALUES (:nome, :email, :matricula, :tipo)"
                        ),
                        dados,
                    )
                conexao.rollback()


class EmprestimosTestes(BancoIsoladoTestCase):
    def preparar(self, exemplares=1):
        livro = self.criar_livro(titulo="Redes de Computadores")
        itens = [self.criar_exemplar(livro["id"]) for _ in range(exemplares)]
        return self.criar_usuario(nome="Luiz Felipe"), livro, itens

    def emprestar(self, usuario_id, exemplar_id, **extras):
        return self.requisicao(
            "POST", "/emprestimos", {"usuario_id": usuario_id, "exemplar_id": exemplar_id, **extras}
        )

    def status_exemplar(self, exemplar_id):
        return self.requisicao("GET", f"/exemplares/{exemplar_id}").json()["status"]

    def test_fluxo_completo_de_emprestimo_e_devolucao(self):
        usuario, livro, (exemplar,) = self.preparar()
        resposta = self.emprestar(usuario["id"], exemplar["id"])
        self.assertEqual(resposta.status_code, 201, resposta.text)
        emprestimo = resposta.json()
        self.assertEqual(emprestimo["status"], "ATIVO")
        self.assertIsNone(emprestimo["data_devolucao"])
        self.assertIs(emprestimo["atrasado"], False)
        self.assertEqual(
            emprestimo["data_prevista_devolucao"], (date.today() + timedelta(days=14)).isoformat()
        )
        self.assertEqual(emprestimo["usuario_nome"], "Luiz Felipe")
        self.assertEqual(emprestimo["livro_titulo"], "Redes de Computadores")
        self.assertEqual(emprestimo["livro_id"], livro["id"])
        self.assertEqual(emprestimo["codigo_tombo"], exemplar["codigo_tombo"])
        self.assertEqual(self.status_exemplar(exemplar["id"]), "EMPRESTADO")

        devolucao = self.requisicao("POST", f"/emprestimos/{emprestimo['id']}/devolucao")
        self.assertEqual(devolucao.status_code, 200, devolucao.text)
        self.assertEqual(devolucao.json()["status"], "DEVOLVIDO")
        self.assertTrue(devolucao.json()["data_devolucao"])
        self.assertEqual(self.status_exemplar(exemplar["id"]), "DISPONIVEL")
        self.assertEqual(
            self.requisicao("GET", f"/emprestimos/{emprestimo['id']}").json(), devolucao.json()
        )

        repetida = self.requisicao("POST", f"/emprestimos/{emprestimo['id']}/devolucao")
        self.assertEqual(repetida.status_code, 409)
        self.assertEqual(self.emprestar(usuario["id"], exemplar["id"]).status_code, 201)

    def test_exemplar_emprestado_nao_pode_ser_emprestado_novamente(self):
        usuario, _, (exemplar,) = self.preparar()
        outro = self.criar_usuario()
        self.assertEqual(self.emprestar(usuario["id"], exemplar["id"]).status_code, 201)
        resposta = self.emprestar(outro["id"], exemplar["id"])
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(resposta.json()["detail"], "Exemplar não está disponível.")
        self.assertEqual(len(self.requisicao("GET", "/emprestimos").json()), 1)

    def test_disponibilidade_e_verificada_no_banco_no_momento_da_retirada(self):
        # Simula outra requisição que alterou o exemplar depois da leitura inicial.
        usuario, _, (exemplar,) = self.preparar()
        with self.engine.begin() as conexao:
            conexao.execute(
                text("UPDATE exemplares SET status = 'EMPRESTADO' WHERE id = :id"),
                {"id": exemplar["id"]},
            )
        self.assertEqual(self.emprestar(usuario["id"], exemplar["id"]).status_code, 409)
        self.assertEqual(self.requisicao("GET", "/emprestimos").json(), [])

    def test_indice_unico_parcial_impede_dois_emprestimos_ativos_e_faz_rollback(self):
        usuario, _, (exemplar,) = self.preparar()
        outro = self.criar_usuario()
        # Dado inconsistente de propósito: empréstimo ativo com exemplar marcado disponível.
        with self.sessoes() as sessao:
            sessao.execute(insert(Emprestimo).values(
                usuario_id=outro["id"], exemplar_id=exemplar["id"],
                data_prevista_devolucao=date.today() + timedelta(days=7), status="ATIVO",
                usuario_nome=outro["nome"], codigo_tombo=exemplar["codigo_tombo"],
                livro_id=exemplar["livro_id"], livro_titulo="Redes de Computadores",
            ))
            sessao.commit()
        with self.assertLogs(level="WARNING"):
            resposta = self.emprestar(usuario["id"], exemplar["id"])
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(self.status_exemplar(exemplar["id"]), "DISPONIVEL")
        self.assertEqual(len(self.requisicao("GET", "/emprestimos").json()), 1)

    def test_recursos_inexistentes_retornam_404(self):
        usuario, _, (exemplar,) = self.preparar()
        self.assertEqual(self.emprestar(99999, exemplar["id"]).status_code, 404)
        self.assertEqual(self.emprestar(usuario["id"], 99999).status_code, 404)
        self.assertEqual(self.requisicao("GET", "/emprestimos/99999").status_code, 404)
        self.assertEqual(self.requisicao("POST", "/emprestimos/99999/devolucao").status_code, 404)
        self.assertEqual(self.status_exemplar(exemplar["id"]), "DISPONIVEL")

    def test_usuario_inativo_e_livro_inativo_nao_emprestam(self):
        usuario, livro, (exemplar,) = self.preparar()
        inativo = self.criar_usuario(ativo=False)
        self.assertEqual(self.emprestar(inativo["id"], exemplar["id"]).status_code, 409)
        self.requisicao("PUT", f"/livros/{livro['id']}", {
            "titulo": livro["titulo"], "autor": livro["autor"], "isbn": livro["isbn"], "ativo": False,
        })
        resposta = self.emprestar(usuario["id"], exemplar["id"])
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(self.status_exemplar(exemplar["id"]), "DISPONIVEL")

    def test_limite_de_tres_emprestimos_ativos(self):
        usuario, _, exemplares = self.preparar(exemplares=4)
        for exemplar in exemplares[:3]:
            self.assertEqual(self.emprestar(usuario["id"], exemplar["id"]).status_code, 201)
        resposta = self.emprestar(usuario["id"], exemplares[3]["id"])
        self.assertEqual(resposta.status_code, 409)
        self.assertIn("3 empréstimos ativos", resposta.json()["detail"])
        self.assertEqual(self.status_exemplar(exemplares[3]["id"]), "DISPONIVEL")

    def test_atraso_e_identificado_e_bloqueia_novo_emprestimo(self):
        usuario, _, (primeiro, segundo) = self.preparar(exemplares=2)
        emprestimo = self.emprestar(usuario["id"], primeiro["id"]).json()
        with self.sessoes() as sessao:
            sessao.execute(
                update(Emprestimo)
                .where(Emprestimo.id == emprestimo["id"])
                .values(data_prevista_devolucao=date.today() - timedelta(days=1))
            )
            sessao.commit()
        self.assertIs(self.requisicao("GET", f"/emprestimos/{emprestimo['id']}").json()["atrasado"], True)
        self.assertEqual(len(self.requisicao("GET", "/emprestimos?atrasados=true").json()), 1)
        resposta = self.emprestar(usuario["id"], segundo["id"])
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(resposta.json()["detail"], "Usuário possui empréstimo em atraso.")

    def test_prazo_personalizado_e_validacao_de_entrada(self):
        usuario, _, (exemplar,) = self.preparar()
        for extras in ({"prazo_dias": 0}, {"prazo_dias": 61}, {"prazo_dias": "7"}, {"extra": 1}):
            with self.subTest(extras=extras):
                self.assertEqual(self.emprestar(usuario["id"], exemplar["id"], **extras).status_code, 422)
        self.assertEqual(self.requisicao("POST", "/emprestimos", {"usuario_id": "1"}).status_code, 422)
        resposta = self.emprestar(usuario["id"], exemplar["id"], prazo_dias=7)
        self.assertEqual(
            resposta.json()["data_prevista_devolucao"], (date.today() + timedelta(days=7)).isoformat()
        )

    def test_listagem_filtra_por_usuario_e_status(self):
        usuario, _, (primeiro, segundo) = self.preparar(exemplares=2)
        outro = self.criar_usuario()
        devolvido = self.emprestar(usuario["id"], primeiro["id"]).json()
        self.requisicao("POST", f"/emprestimos/{devolvido['id']}/devolucao")
        ativo = self.emprestar(outro["id"], segundo["id"]).json()

        def ids(consulta):
            return [item["id"] for item in self.requisicao("GET", "/emprestimos?" + urlencode(consulta)).json()]

        self.assertEqual(ids({}), [ativo["id"], devolvido["id"]])
        self.assertEqual(ids({"usuario_id": usuario["id"]}), [devolvido["id"]])
        self.assertEqual(ids({"status": "ATIVO"}), [ativo["id"]])
        self.assertEqual(ids({"status": "DEVOLVIDO"}), [devolvido["id"]])
        self.assertEqual(self.requisicao("GET", "/emprestimos?status=PERDIDO").status_code, 422)

    def test_banco_protege_coerencia_do_emprestimo_sem_pydantic(self):
        usuario, _, (exemplar,) = self.preparar()
        comando = text(
            "INSERT INTO emprestimos (usuario_id, exemplar_id, data_prevista_devolucao, status, "
            "data_devolucao, usuario_nome, codigo_tombo, livro_id, livro_titulo) "
            "VALUES (:usuario_id, :exemplar_id, :prevista, :status, :devolucao, 'U', 'T', 1, 'L')"
        )
        casos = [
            {"status": "PERDIDO"}, {"status": "ATIVO", "devolucao": "2026-01-01"},
            {"status": "DEVOLVIDO", "devolucao": None}, {"usuario_id": 99999},
            {"exemplar_id": 99999}, {"prevista": None},
        ]
        for alteracoes in casos:
            with self.subTest(alteracoes=alteracoes), self.engine.connect() as conexao:
                dados = {
                    "usuario_id": usuario["id"], "exemplar_id": exemplar["id"],
                    "prevista": "2026-12-01", "status": "ATIVO", "devolucao": None,
                }
                dados.update(alteracoes)
                with self.assertRaises(IntegrityError):
                    conexao.execute(comando, dados)
                conexao.rollback()

    def test_banco_aceita_varios_devolvidos_mas_um_unico_ativo_por_exemplar(self):
        usuario, _, (exemplar,) = self.preparar()
        comando = text(
            "INSERT INTO emprestimos (usuario_id, exemplar_id, data_prevista_devolucao, status, "
            "data_devolucao, usuario_nome, codigo_tombo, livro_id, livro_titulo) "
            "VALUES (:u, :e, '2026-12-01', :s, :d, 'U', 'T', 1, 'L')"
        )
        base = {"u": usuario["id"], "e": exemplar["id"]}
        with self.engine.begin() as conexao:
            for _ in range(2):
                conexao.execute(comando, {**base, "s": "DEVOLVIDO", "d": "2026-11-01"})
            conexao.execute(comando, {**base, "s": "ATIVO", "d": None})
        with self.engine.connect() as conexao:
            with self.assertRaises(IntegrityError):
                conexao.execute(comando, {**base, "s": "ATIVO", "d": None})
            conexao.rollback()

    def test_swagger_inclui_usuarios_e_emprestimos(self):
        for servico, rota, metodos, tag in (
            ("usuarios", "/usuarios", {"get", "post"}, "Usuários"),
            ("usuarios", "/usuarios/{usuario_id}", {"get", "put"}, "Usuários"),
            ("emprestimos", "/emprestimos", {"get", "post"}, "Empréstimos"),
            ("emprestimos", "/emprestimos/{emprestimo_id}", {"get"}, "Empréstimos"),
            ("emprestimos", "/emprestimos/{emprestimo_id}/devolucao", {"post"}, "Empréstimos"),
            ("catalogo", "/exemplares/{exemplar_id}", {"get"}, "Catálogo"),
        ):
            with self.subTest(rota=rota):
                caminhos = self.requisicao("GET", "/openapi.json", servico=servico).json()["paths"]
                self.assertEqual(set(caminhos[rota]), metodos)
                for metodo in metodos:
                    self.assertIn(tag, caminhos[rota][metodo]["tags"])


if __name__ == "__main__":
    unittest.main()
