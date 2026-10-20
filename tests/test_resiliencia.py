"""V5: falhas e recuperação (novas tentativas, disjuntor e reconciliação).

Execução: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import update

from tests.apoio import BancoIsoladoTestCase, config
from backend import reconciliacao
from backend.models.exemplar import Exemplar
from backend.resiliencia import Disjuntor, EstadoDisjuntor


class DisjuntorTestes(unittest.TestCase):
    def setUp(self):
        self.agora = 0.0
        self.disjuntor = Disjuntor("Teste", limite_falhas=3, segundos_aberto=30, relogio=lambda: self.agora)

    def test_abre_depois_de_falhas_seguidas(self):
        for _ in range(2):
            self.disjuntor.registrar_falha()
        self.assertEqual(self.disjuntor.estado, EstadoDisjuntor.FECHADO)
        self.disjuntor.registrar_falha()
        self.assertEqual(self.disjuntor.estado, EstadoDisjuntor.ABERTO)
        self.assertFalse(self.disjuntor.permitir())
        self.assertEqual(self.disjuntor.segundos_para_nova_tentativa(), 30)

    def test_sucesso_zera_a_contagem(self):
        self.disjuntor.registrar_falha()
        self.disjuntor.registrar_falha()
        self.disjuntor.registrar_sucesso()
        self.disjuntor.registrar_falha()
        self.assertEqual(self.disjuntor.estado, EstadoDisjuntor.FECHADO)

    def test_meio_aberto_fecha_com_sucesso_e_reabre_com_falha(self):
        for _ in range(3):
            self.disjuntor.registrar_falha()
        self.agora = 30
        self.assertEqual(self.disjuntor.estado, EstadoDisjuntor.MEIO_ABERTO)
        self.assertTrue(self.disjuntor.permitir())
        self.disjuntor.registrar_falha()  # a chamada de teste falhou: abre de novo
        self.assertEqual(self.disjuntor.estado, EstadoDisjuntor.ABERTO)
        self.agora = 61
        self.disjuntor.registrar_sucesso()
        self.assertEqual(self.disjuntor.estado, EstadoDisjuntor.FECHADO)


class NovasTentativasTestes(BancoIsoladoTestCase):
    def setUp(self):
        super().setUp()
        livro = self.criar_livro(titulo="Redes")
        self.exemplar = self.criar_exemplar(livro["id"])
        self.usuario = self.criar_usuario(nome="André")

    def falhar_n_vezes(self, trecho, vezes, resposta_ou_erro):
        """Faz as primeiras ``vezes`` chamadas que contêm ``trecho`` falharem."""
        original = self.servicos.cliente._transport.handler
        restantes = {"n": vezes}

        def com_falhas(pedido):
            if trecho in str(pedido.url) and restantes["n"] > 0:
                restantes["n"] -= 1
                self.chamadas_remotas.append(f"FALHA {pedido.method} {pedido.url.path}")
                if isinstance(resposta_ou_erro, Exception):
                    raise resposta_ou_erro
                return httpx.Response(resposta_ou_erro, json={"detail": "erro"})
            return original(pedido)

        self.servicos.cliente._transport.handler = com_falhas

    def emprestar(self):
        return self.requisicao(
            "POST", "/emprestimos", {"usuario_id": self.usuario["id"], "exemplar_id": self.exemplar["id"]}
        )

    def test_falha_de_conexao_passageira_e_superada_com_nova_tentativa(self):
        self.falhar_n_vezes(":8002", 2, httpx.ConnectError("recusada"))
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            resposta = self.emprestar()
        self.assertEqual(resposta.status_code, 201, resposta.text)
        self.assertEqual(len(self.esperas), 2)
        self.assertLess(self.esperas[0], self.esperas[1])  # espera crescente
        self.assertEqual(self.disjuntores["Usuários"].estado, EstadoDisjuntor.FECHADO)

    def test_retirada_nao_e_repetida_apos_erro_5xx(self):
        """Repetir uma retirada que pode ter acontecido seria perigoso: não repete."""
        self.falhar_n_vezes("/retirada", 1, 500)
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            resposta = self.emprestar()
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(sum("retirada" in c for c in self.chamadas_remotas), 1)
        self.assertEqual(self.esperas, [])

    def test_liberacao_idempotente_e_repetida_apos_erro_5xx(self):
        emprestimo = self.emprestar().json()
        self.falhar_n_vezes("/liberacao", 1, 500)
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            devolucao = self.requisicao("POST", f"/emprestimos/{emprestimo['id']}/devolucao")
        self.assertEqual(devolucao.status_code, 200)
        self.assertEqual(sum("liberacao" in c for c in self.chamadas_remotas), 2)

    def test_disjuntor_aberto_falha_na_hora_e_fecha_quando_o_servico_volta(self):
        self.simular_falha(":8002", httpx.ConnectError("fora do ar"))
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            self.assertEqual(self.emprestar().status_code, 503)  # 3 tentativas → abre
        self.assertEqual(self.disjuntores["Usuários"].estado, EstadoDisjuntor.ABERTO)

        chamadas_antes = len(self.chamadas_remotas)
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            rapida = self.emprestar()
        self.assertEqual(rapida.status_code, 503)
        self.assertIn("Nova tentativa em 30 s", rapida.json()["detail"])
        self.assertEqual(len(self.chamadas_remotas), chamadas_antes)  # nem tentou chamar

        estado = self.requisicao("GET", "/health/dependencias", servico="emprestimos").json()
        self.assertEqual(estado["disjuntores"]["Usuários"]["estado"], "ABERTO")
        self.assertEqual(estado["disjuntores"]["Catálogo"]["estado"], "FECHADO")

        self.falhas.clear()
        self.avancar_relogio(30)
        self.assertEqual(self.emprestar().status_code, 201)
        self.assertEqual(self.disjuntores["Usuários"].estado, EstadoDisjuntor.FECHADO)


class ReconciliacaoTestes(BancoIsoladoTestCase):
    def setUp(self):
        super().setUp()
        reconciliacao.ultima_execucao = None
        self.livro = self.criar_livro()

    def marcar_emprestado(self, exemplar, ha_segundos):
        alterado = datetime.now(timezone.utc) - timedelta(seconds=ha_segundos)
        with self.sessoes() as sessao:
            sessao.execute(
                update(Exemplar).where(Exemplar.id == exemplar["id"])
                .values(status="EMPRESTADO", alterado_em=alterado)
            )
            sessao.commit()

    def status(self, exemplar):
        return self.requisicao("GET", f"/exemplares/{exemplar['id']}").json()["status"]

    def test_libera_somente_exemplar_preso_ha_mais_tempo_que_a_carencia(self):
        preso = self.criar_exemplar(self.livro["id"], codigo_tombo="PRESO-1")
        recente = self.criar_exemplar(self.livro["id"], codigo_tombo="RECENTE-1")
        emprestado = self.criar_exemplar(self.livro["id"], codigo_tombo="EMPRESTADO-1")
        usuario = self.criar_usuario()
        self.requisicao("POST", "/emprestimos", {"usuario_id": usuario["id"], "exemplar_id": emprestado["id"]})
        self.marcar_emprestado(preso, ha_segundos=3600)
        self.marcar_emprestado(recente, ha_segundos=5)  # pode estar no meio de uma saga
        self.marcar_emprestado(emprestado, ha_segundos=3600)

        with self.assertLogs("booknet.reconciliacao", level="WARNING"):
            resultado = self.requisicao("POST", "/emprestimos/reconciliacao").json()
        self.assertEqual(resultado["verificados"], 2)
        self.assertEqual(resultado["liberados"], ["PRESO-1"])
        self.assertEqual(self.status(preso), "DISPONIVEL")
        self.assertEqual(self.status(recente), "EMPRESTADO")
        self.assertEqual(self.status(emprestado), "EMPRESTADO")
        estado = self.requisicao("GET", "/health/dependencias", servico="emprestimos").json()
        self.assertEqual(estado["ultima_reconciliacao"]["liberados"], ["PRESO-1"])

    def test_sem_diferencas_nao_altera_nada(self):
        resultado = self.requisicao("POST", "/emprestimos/reconciliacao").json()
        self.assertEqual((resultado["verificados"], resultado["liberados"]), (0, []))

    def test_catalogo_fora_do_ar_impede_a_reconciliacao_sem_estragar_dados(self):
        preso = self.criar_exemplar(self.livro["id"])
        self.marcar_emprestado(preso, ha_segundos=3600)
        self.simular_falha(":8001", httpx.ConnectError("fora do ar"))
        with self.assertLogs("booknet.servicos_remotos", level="WARNING"):
            resposta = self.requisicao("POST", "/emprestimos/reconciliacao")
        self.assertEqual(resposta.status_code, 503)
        self.assertIsNone(reconciliacao.ultima_execucao)
        self.falhas.clear()
        self.assertEqual(self.status(preso), "EMPRESTADO")

    def test_execucao_periodica_repete_e_sobrevive_a_falhas(self):
        execucoes = []

        def executar():
            execucoes.append(1)
            if len(execucoes) == 1:
                raise RuntimeError("Catálogo fora do ar")

        async def cenario():
            with (
                patch.object(config, "RECONCILIACAO_INTERVALO_SEGUNDOS", 0.01),
                patch.object(reconciliacao, "_executar_agendada", executar),
            ):
                tarefa = asyncio.create_task(reconciliacao.reconciliar_periodicamente())
                await asyncio.sleep(0.1)
                tarefa.cancel()

        with self.assertLogs("booknet.reconciliacao", level="WARNING"):
            asyncio.run(cenario())
        self.assertGreaterEqual(len(execucoes), 2)  # continuou depois da primeira falha


if __name__ == "__main__":
    unittest.main()
