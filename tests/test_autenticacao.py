"""Login, perfis (aluno e bibliotecário) e proteção das rotas nos três serviços.

Execução: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import base64
import json
import unittest
from unittest.mock import patch

from tests.apoio import BancoIsoladoTestCase, config
from tests.test_eventos import ConexaoWS
from backend import autenticacao
from backend.autenticacao import TokenInvalido, criar_token, gerar_hash_senha, ler_token, verificar_senha
from backend.routers import usuarios as rotas_usuarios


class SenhaETokenTestes(unittest.TestCase):
    def test_hash_de_senha_tem_sal_e_confere(self):
        primeiro, segundo = gerar_hash_senha("segredo123"), gerar_hash_senha("segredo123")
        self.assertNotEqual(primeiro, segundo)  # sal aleatório: hashes diferentes
        self.assertNotIn("segredo123", primeiro)
        self.assertTrue(primeiro.startswith("pbkdf2_sha256$600000$"))
        self.assertTrue(verificar_senha("segredo123", primeiro))
        self.assertFalse(verificar_senha("segredo124", primeiro))
        for armazenado in (None, "", "lixo", "md5$1$a$b"):
            self.assertFalse(verificar_senha("segredo123", armazenado))

    def test_token_valido_e_lido(self):
        sessao = ler_token(criar_token(7, "Luiz", "ALUNO"))
        self.assertEqual((sessao.usuario_id, sessao.nome, sessao.papel), (7, "Luiz", "ALUNO"))
        self.assertFalse(sessao.bibliotecario)

    def test_token_adulterado_expirado_ou_sem_assinatura_e_recusado(self):
        token = criar_token(7, "Luiz", "ALUNO")
        cabecalho, dados, assinatura = token.split(".")
        promovido = json.loads(base64.urlsafe_b64decode(dados + "=="))
        promovido["papel"] = "BIBLIOTECARIO"
        dados_falsos = base64.urlsafe_b64encode(json.dumps(promovido).encode()).rstrip(b"=").decode()
        alg_none = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        with patch.object(config, "SEGREDO_SESSAO", "outro-segredo"):
            assinado_com_outro_segredo = criar_token(7, "Luiz", "ALUNO")
        casos = {
            "papel trocado": f"{cabecalho}.{dados_falsos}.{assinatura}",
            "alg none": f"{alg_none}.{dados}.",
            "outro segredo": assinado_com_outro_segredo,
            "expirado": criar_token(7, "Luiz", "ALUNO", validade_segundos=-1),
            "malformado": "abc",
            "vazio": "",
        }
        for nome, invalido in casos.items():
            with self.subTest(caso=nome), self.assertRaises(TokenInvalido):
                ler_token(invalido)


class LoginTestes(BancoIsoladoTestCase):
    def setUp(self):
        super().setUp()
        rotas_usuarios._tentativas_falhas.clear()
        self.aluno = self.criar_usuario(nome="Luiz Felipe", matricula="2026003", senha="aluno-123")
        self.bibliotecaria = self.criar_usuario(
            nome="Bibliotecária", matricula="BIB-001", tipo="BIBLIOTECARIO", senha="biblio-123"
        )

    def entrar(self, matricula, senha, perfil=None):
        dados = {"matricula": matricula, "senha": senha}
        if perfil:
            dados["perfil"] = perfil
        return self.requisicao("POST", "/auth/login", dados, servico="usuarios", token=None)

    def test_login_devolve_token_e_dados_sem_a_senha(self):
        resposta = self.entrar("2026003", "aluno-123", "ALUNO")
        self.assertEqual(resposta.status_code, 200, resposta.text)
        corpo = resposta.json()
        self.assertEqual(corpo["usuario"]["nome"], "Luiz Felipe")
        self.assertIs(corpo["usuario"]["tem_senha"], True)
        self.assertNotIn("senha_hash", resposta.text)
        self.assertNotIn("aluno-123", resposta.text)
        self.assertEqual(ler_token(corpo["token"]).papel, "ALUNO")
        eu = self.requisicao("GET", "/auth/eu", servico="usuarios", token=corpo["token"])
        self.assertEqual(eu.json()["matricula"], "2026003")

    def test_login_recusado_com_mensagem_generica(self):
        sem_senha = self.criar_usuario(matricula="SEM-SENHA")
        for matricula, senha in (("2026003", "errada"), ("NAO-EXISTE", "aluno-123"), (sem_senha["matricula"], "x")):
            with self.subTest(matricula=matricula):
                resposta = self.entrar(matricula, senha)
                self.assertEqual(resposta.status_code, 401)
                self.assertEqual(resposta.json()["detail"], "Matrícula ou senha incorretos.")

    def test_aba_errada_e_conta_desativada(self):
        resposta = self.entrar("2026003", "aluno-123", "BIBLIOTECARIO")
        self.assertEqual(resposta.status_code, 403)
        self.assertIn("aba Aluno", resposta.json()["detail"])
        self.requisicao("PUT", f"/usuarios/{self.aluno['id']}", {
            "nome": "Luiz Felipe", "email": self.aluno["email"], "matricula": "2026003", "ativo": False,
        })
        self.assertEqual(self.entrar("2026003", "aluno-123").status_code, 403)

    def test_bloqueio_apos_cinco_erros(self):
        for _ in range(5):
            self.assertEqual(self.entrar("2026003", "errada").status_code, 401)
        bloqueado = self.entrar("2026003", "aluno-123")  # até a senha certa espera
        self.assertEqual(bloqueado.status_code, 429)
        self.assertEqual(self.entrar("BIB-001", "biblio-123").status_code, 200)  # outra conta segue livre

    def test_bibliotecario_define_e_troca_senha(self):
        novo = self.criar_usuario(matricula="2026099", senha="primeira")
        self.assertEqual(self.entrar("2026099", "primeira").status_code, 200)
        self.requisicao("PUT", f"/usuarios/{novo['id']}", {
            "nome": novo["nome"], "email": novo["email"], "matricula": "2026099", "senha": "segunda",
        })
        self.assertEqual(self.entrar("2026099", "primeira").status_code, 401)
        self.assertEqual(self.entrar("2026099", "segunda").status_code, 200)
        # PUT sem senha mantém a atual
        self.requisicao("PUT", f"/usuarios/{novo['id']}", {
            "nome": "Outro Nome", "email": novo["email"], "matricula": "2026099",
        })
        self.assertEqual(self.entrar("2026099", "segunda").status_code, 200)

    def test_senha_curta_e_recusada(self):
        resposta = self.requisicao("POST", "/usuarios", {
            "nome": "X", "email": "x@booknet.test", "matricula": "X-1", "senha": "123",
        })
        self.assertEqual(resposta.status_code, 422)


class PermissoesTestes(BancoIsoladoTestCase):
    def setUp(self):
        super().setUp()
        livro = self.criar_livro(titulo="Redes")
        self.livro = livro
        self.exemplares = [self.criar_exemplar(livro["id"]) for _ in range(3)]
        self.aluno = self.criar_usuario(nome="Aluno Um")
        self.outro = self.criar_usuario(nome="Aluno Dois")
        self.token_aluno = self.token_de(self.aluno)

    def test_sem_login_tudo_e_recusado_menos_saude_e_login(self):
        for servico, metodo, rota in (
            ("catalogo", "GET", "/livros"),
            ("catalogo", "GET", f"/exemplares/{self.exemplares[0]['id']}"),
            ("usuarios", "GET", "/usuarios"),
            ("usuarios", "GET", "/auth/eu"),
            ("emprestimos", "GET", "/emprestimos"),
        ):
            with self.subTest(rota=rota):
                resposta = self.requisicao(metodo, rota, servico=servico, token=None)
                self.assertEqual(resposta.status_code, 401)
                self.assertEqual(resposta.headers.get("www-authenticate"), "Bearer")
        for servico in ("catalogo", "usuarios", "emprestimos"):
            self.assertEqual(self.requisicao("GET", "/health", servico=servico, token=None).status_code, 200)
        self.assertEqual(
            self.requisicao("GET", "/livros", token="token.falso.aqui").status_code, 401
        )

    def test_aluno_consulta_acervo_mas_nao_administra(self):
        self.assertEqual(self.requisicao("GET", "/livros", token=self.token_aluno).status_code, 200)
        proibidas = (
            ("POST", "/livros", {"titulo": "X", "autor": "Y", "isbn": "999"}),
            ("PUT", f"/livros/{self.livro['id']}", {"titulo": "X", "autor": "Y", "isbn": "999"}),
            ("POST", f"/livros/{self.livro['id']}/exemplares", {"codigo_tombo": "HACK-1"}),
            ("GET", "/usuarios", None),
            ("POST", "/usuarios", {"nome": "X", "email": "h@x.co", "matricula": "H1", "tipo": "BIBLIOTECARIO"}),
            ("GET", f"/usuarios/{self.outro['id']}", None),
            ("POST", "/emprestimos/reconciliacao", None),
        )
        for metodo, rota, dados in proibidas:
            with self.subTest(rota=rota, metodo=metodo):
                resposta = self.requisicao(metodo, rota, dados, token=self.token_aluno)
                self.assertEqual(resposta.status_code, 403, resposta.text)
        proprio = self.requisicao("GET", f"/usuarios/{self.aluno['id']}", token=self.token_aluno)
        self.assertEqual(proprio.status_code, 200)

    def test_aluno_empresta_e_devolve_so_para_si(self):
        emprestar = lambda usuario, exemplar: self.requisicao(  # noqa: E731
            "POST", "/emprestimos", {"usuario_id": usuario["id"], "exemplar_id": exemplar["id"]},
            token=self.token_aluno,
        )
        self.assertEqual(emprestar(self.outro, self.exemplares[0]).status_code, 403)
        meu = emprestar(self.aluno, self.exemplares[0])
        self.assertEqual(meu.status_code, 201, meu.text)
        do_outro = self.requisicao("POST", "/emprestimos", {
            "usuario_id": self.outro["id"], "exemplar_id": self.exemplares[1]["id"],
        }).json()  # feito pela bibliotecária

        lista = self.requisicao("GET", "/emprestimos", token=self.token_aluno).json()
        self.assertEqual([e["id"] for e in lista], [meu.json()["id"]])
        lista_forcada = self.requisicao(
            "GET", f"/emprestimos?usuario_id={self.outro['id']}", token=self.token_aluno
        ).json()
        self.assertEqual([e["id"] for e in lista_forcada], [meu.json()["id"]])
        self.assertEqual(len(self.requisicao("GET", "/emprestimos").json()), 2)  # bibliotecária vê tudo

        for metodo, rota in (("GET", f"/emprestimos/{do_outro['id']}"),
                             ("POST", f"/emprestimos/{do_outro['id']}/devolucao")):
            with self.subTest(rota=rota):
                self.assertEqual(self.requisicao(metodo, rota, token=self.token_aluno).status_code, 403)
        devolucao = self.requisicao("POST", f"/emprestimos/{meu.json()['id']}/devolucao", token=self.token_aluno)
        self.assertEqual(devolucao.status_code, 200)

    def test_servicos_continuam_se_comunicando_com_token_interno(self):
        resposta = self.requisicao("POST", "/emprestimos", {
            "usuario_id": self.aluno["id"], "exemplar_id": self.exemplares[2]["id"],
        }, token=self.token_aluno)
        self.assertEqual(resposta.status_code, 201)
        self.assertIn(f"GET /usuarios/{self.aluno['id']}", self.chamadas_remotas)


class EventosComLoginTestes(BancoIsoladoTestCase):
    def setUp(self):
        super().setUp()
        livro = self.criar_livro()
        self.exemplares = [self.criar_exemplar(livro["id"]) for _ in range(2)]
        self.aluno = self.criar_usuario(nome="Aluno Um")
        self.outro = self.criar_usuario(nome="Aluno Dois")

    def test_canal_exige_token_valido(self):
        async def cenario():
            for token in (None, "invalido", criar_token(1, "X", "ALUNO", validade_segundos=-1)):
                with self.subTest(token=token):
                    resposta = await ConexaoWS(token=token).abrir()
                    self.assertEqual(resposta["type"], "websocket.close")
                    self.assertEqual(resposta["code"], 1008)

        asyncio.run(cenario())

    def test_aluno_so_recebe_os_proprios_emprestimos_e_bibliotecario_recebe_todos(self):
        async def cenario():
            telas = {
                "aluno": ConexaoWS(token=self.token_de(self.aluno)),
                "outro": ConexaoWS(token=self.token_de(self.outro)),
                "biblio": ConexaoWS(token=self.token_bibliotecario),
            }
            for tela in telas.values():
                await tela.abrir()
            await asyncio.sleep(0)
            for tela in telas.values():
                tela.pendentes()
            resposta = await self.http(
                "POST", "/emprestimos",
                {"usuario_id": self.aluno["id"], "exemplar_id": self.exemplares[0]["id"]},
                token=self.token_de(self.aluno),
            )
            self.assertEqual(resposta.status_code, 201)
            self.assertEqual((await telas["aluno"].receber("emprestimo.criado"))["dados"]["usuario_nome"], "Aluno Um")
            await telas["biblio"].receber("emprestimo.criado")
            await asyncio.sleep(0)
            self.assertNotIn("emprestimo.criado", telas["outro"].pendentes())
            for tela in telas.values():
                await tela.fechar()

        asyncio.run(cenario())


if __name__ == "__main__":
    unittest.main()
