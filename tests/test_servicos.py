"""V3: serviços separados, rotas internas e falhas de comunicação entre serviços.

Execução: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest

import httpx

from tests.apoio import BancoIsoladoTestCase, config


class SeparacaoTestes(BancoIsoladoTestCase):
    def test_cada_servico_expoe_somente_as_proprias_rotas(self):
        esperado = {
            "catalogo": {"/livros", "/exemplares/{exemplar_id}", "/interno/exemplares/{exemplar_id}/retirada"},
            "usuarios": {"/usuarios", "/usuarios/{usuario_id}"},
            "emprestimos": {"/emprestimos", "/emprestimos/{emprestimo_id}/devolucao"},
        }
        todas = set().union(*esperado.values())
        for servico, proprias in esperado.items():
            with self.subTest(servico=servico):
                identificacao = self.requisicao("GET", "/", servico=servico).json()
                self.assertEqual(identificacao["servico"], servico)
                caminhos = set(self.requisicao("GET", "/openapi.json", servico=servico).json()["paths"])
                self.assertTrue(proprias <= caminhos)
                self.assertFalse((todas - proprias) & caminhos)

    def test_rotas_internas_exigem_token(self):
        livro = self.criar_livro()
        exemplar = self.criar_exemplar(livro["id"])
        rota = f"/interno/exemplares/{exemplar['id']}/retirada"
        for cabecalhos in ({}, {"X-Servico-Token": "token-errado"}):
            with self.subTest(cabecalhos=cabecalhos):
                self.assertEqual(self.requisicao("POST", rota, headers=cabecalhos).status_code, 403)
        self.assertEqual(self.requisicao("GET", f"/exemplares/{exemplar['id']}").json()["status"], "DISPONIVEL")

    def test_retirada_e_liberacao_internas(self):
        livro = self.criar_livro(titulo="Redes")
        exemplar = self.criar_exemplar(livro["id"])
        token = {"X-Servico-Token": config.TOKEN_INTERNO}
        base = f"/interno/exemplares/{exemplar['id']}"
        retirada = self.requisicao("POST", f"{base}/retirada", headers=token)
        self.assertEqual(retirada.status_code, 200)
        self.assertEqual(retirada.json()["status"], "EMPRESTADO")
        self.assertEqual(retirada.json()["livro_titulo"], "Redes")
        self.assertEqual(self.requisicao("POST", f"{base}/retirada", headers=token).status_code, 409)
        for _ in range(2):  # idempotente: repetir a liberação não é erro
            liberacao = self.requisicao("POST", f"{base}/liberacao", headers=token)
            self.assertEqual(liberacao.status_code, 200)
            self.assertEqual(liberacao.json()["status"], "DISPONIVEL")
        self.assertEqual(
            self.requisicao("POST", "/interno/exemplares/99999/liberacao", headers=token).status_code, 404
        )


class ComunicacaoEntreServicosTestes(BancoIsoladoTestCase):
    def preparar(self):
        livro = self.criar_livro(titulo="Sistemas Distribuídos")
        exemplar = self.criar_exemplar(livro["id"])
        usuario = self.criar_usuario(nome="João Henrique")
        return usuario, exemplar

    def emprestar(self, usuario, exemplar):
        return self.requisicao(
            "POST", "/emprestimos", {"usuario_id": usuario["id"], "exemplar_id": exemplar["id"]}
        )

    def status_exemplar(self, exemplar):
        return self.requisicao("GET", f"/exemplares/{exemplar['id']}").json()["status"]

    def test_emprestimo_consulta_usuarios_e_catalogo_pela_rede(self):
        usuario, exemplar = self.preparar()
        self.assertEqual(self.emprestar(usuario, exemplar).status_code, 201)
        self.assertEqual(
            self.chamadas_remotas,
            [f"GET /usuarios/{usuario['id']}", f"POST /interno/exemplares/{exemplar['id']}/retirada"],
        )

    def test_servico_de_usuarios_fora_do_ar_retorna_503_sem_mexer_no_exemplar(self):
        usuario, exemplar = self.preparar()
        self.simular_falha(":8002", httpx.ConnectError("conexão recusada"))
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            resposta = self.emprestar(usuario, exemplar)
        self.assertEqual(resposta.status_code, 503)
        self.assertIn("Usuários", resposta.json()["detail"])
        self.assertEqual(self.status_exemplar(exemplar), "DISPONIVEL")
        self.assertEqual(self.requisicao("GET", "/emprestimos").json(), [])

    def test_catalogo_lento_retorna_504_timeout(self):
        usuario, exemplar = self.preparar()
        self.simular_falha(":8001", httpx.ReadTimeout("sem resposta"))
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            resposta = self.emprestar(usuario, exemplar)
        self.assertEqual(resposta.status_code, 504)
        self.assertIn("Catálogo", resposta.json()["detail"])
        self.assertEqual(self.requisicao("GET", "/emprestimos").json(), [])

    def test_devolucao_com_catalogo_fora_do_ar_e_desfeita_e_pode_ser_repetida(self):
        usuario, exemplar = self.preparar()
        emprestimo = self.emprestar(usuario, exemplar).json()
        self.simular_falha("/liberacao", httpx.ConnectError("conexão recusada"))
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            falha = self.requisicao("POST", f"/emprestimos/{emprestimo['id']}/devolucao")
        self.assertEqual(falha.status_code, 503)
        self.assertEqual(self.requisicao("GET", f"/emprestimos/{emprestimo['id']}").json()["status"], "ATIVO")
        self.assertEqual(self.status_exemplar(exemplar), "EMPRESTADO")

        self.falhas.clear()  # o Catálogo voltou
        devolucao = self.requisicao("POST", f"/emprestimos/{emprestimo['id']}/devolucao")
        self.assertEqual(devolucao.status_code, 200)
        self.assertEqual(self.status_exemplar(exemplar), "DISPONIVEL")

    def test_compensacao_que_falha_fica_registrada_no_log(self):
        usuario, exemplar = self.preparar()
        outro = self.criar_usuario()
        # Força o passo 4 a falhar: já existe um empréstimo ativo para o exemplar.
        self.assertEqual(self.emprestar(outro, exemplar).status_code, 201)
        self.requisicao("POST", f"/interno/exemplares/{exemplar['id']}/liberacao",
                        headers={"X-Servico-Token": config.TOKEN_INTERNO})
        self.simular_falha("/liberacao", httpx.ConnectError("conexão recusada"))
        with self.assertLogs("booknet.emprestimos", level="ERROR") as logs:
            resposta = self.emprestar(usuario, exemplar)
        self.assertEqual(resposta.status_code, 409)
        self.assertIn("Compensação falhou", "\n".join(logs.output))

    def test_listagem_de_emprestimos_funciona_com_os_outros_servicos_fora_do_ar(self):
        usuario, exemplar = self.preparar()
        self.emprestar(usuario, exemplar)
        self.simular_falha(":8001", httpx.ConnectError("fora do ar"))
        self.simular_falha(":8002", httpx.ConnectError("fora do ar"))
        lista = self.requisicao("GET", "/emprestimos")
        self.assertEqual(lista.status_code, 200)
        self.assertEqual(lista.json()[0]["usuario_nome"], "João Henrique")
        self.assertEqual(lista.json()[0]["livro_titulo"], "Sistemas Distribuídos")

    def test_emprestimo_guarda_copia_dos_dados_do_momento(self):
        usuario, exemplar = self.preparar()
        emprestimo = self.emprestar(usuario, exemplar).json()
        self.requisicao("PUT", f"/usuarios/{usuario['id']}", {
            "nome": "Nome Novo", "email": usuario["email"], "matricula": usuario["matricula"],
        })
        registro = self.requisicao("GET", f"/emprestimos/{emprestimo['id']}").json()
        self.assertEqual(registro["usuario_nome"], "João Henrique")

    def test_servico_respondendo_erro_500_vira_503(self):
        usuario, exemplar = self.preparar()
        original = self.servicos.cliente._transport.handler

        def com_erro(pedido):
            if pedido.url.port == 8002:
                return httpx.Response(500, json={"detail": "erro interno"})
            return original(pedido)

        self.servicos.cliente._transport.handler = com_erro
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            resposta = self.emprestar(usuario, exemplar)
        self.assertEqual(resposta.status_code, 503)


if __name__ == "__main__":
    unittest.main()
