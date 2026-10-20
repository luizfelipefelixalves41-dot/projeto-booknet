"""V6: eventos entre réplicas por um intermediário de mensagens (Redis Pub/Sub).

O Redis é substituído por um intermediário em memória com o mesmo comportamento:
toda mensagem publicada num canal chega a todos os assinantes daquele canal.

Execução: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from backend import broker as modulo_broker
from backend import config
from backend.autenticacao import Sessao
from backend.eventos import CentralDeEventos


class BrokerEmMemoria:
    def __init__(self):
        self.assinantes: dict[str, list[asyncio.Queue]] = {}
        self.falhar_publicacao = False

    async def publicar(self, canal, mensagem):
        if self.falhar_publicacao:
            raise ConnectionError("Redis fora do ar")
        for fila in self.assinantes.get(canal, []):
            fila.put_nowait(mensagem)

    async def escutar(self, canal):
        fila = asyncio.Queue()
        self.assinantes.setdefault(canal, []).append(fila)
        try:
            while True:
                yield await fila.get()
        finally:
            self.assinantes[canal].remove(fila)

    async def fechar(self):
        pass


class ConexaoFalsa:
    def __init__(self):
        self.recebidas = []

    async def accept(self):
        pass

    async def send_json(self, mensagem):
        self.recebidas.append(mensagem)

    def tipos(self):
        return [m["tipo"] for m in self.recebidas]


BIBLIOTECARIA = Sessao(usuario_id=1, nome="Bibliotecária", papel="BIBLIOTECARIO")
ALUNO = Sessao(usuario_id=7, nome="Aluno", papel="ALUNO")


class ReplicasTestes(unittest.TestCase):
    def test_evento_publicado_numa_replica_chega_aos_navegadores_da_outra(self):
        async def cenario():
            redis = BrokerEmMemoria()
            replica_a = CentralDeEventos("catalogo", redis)
            replica_b = CentralDeEventos("catalogo", redis)
            outro_servico = CentralDeEventos("usuarios", redis)
            for central in (replica_a, replica_b, outro_servico):
                await central.iniciar()
            await asyncio.sleep(0)
            em_a, em_b, em_usuarios = ConexaoFalsa(), ConexaoFalsa(), ConexaoFalsa()
            await replica_a.conectar(em_a, BIBLIOTECARIA)
            await replica_b.conectar(em_b, BIBLIOTECARIA)
            await outro_servico.conectar(em_usuarios, BIBLIOTECARIA)

            await replica_b.publicar("livro.criado", {"id": 1, "titulo": "Redes"})  # atendido pela réplica B
            await asyncio.sleep(0.05)
            self.assertIn("livro.criado", em_a.tipos())  # chegou também a quem está na réplica A
            self.assertIn("livro.criado", em_b.tipos())
            self.assertNotIn("livro.criado", em_usuarios.tipos())  # canal de outro serviço
            for central in (replica_a, replica_b, outro_servico):
                await central.encerrar()

        asyncio.run(cenario())

    def test_filtro_por_perfil_continua_valendo_entre_replicas(self):
        async def cenario():
            redis = BrokerEmMemoria()
            replica_a, replica_b = CentralDeEventos("emprestimos", redis), CentralDeEventos("emprestimos", redis)
            await replica_a.iniciar()
            await replica_b.iniciar()
            await asyncio.sleep(0)
            aluno, outro_aluno, biblio = ConexaoFalsa(), ConexaoFalsa(), ConexaoFalsa()
            await replica_a.conectar(aluno, ALUNO)
            await replica_a.conectar(outro_aluno, Sessao(usuario_id=8, nome="Outro", papel="ALUNO"))
            await replica_a.conectar(biblio, BIBLIOTECARIA)
            await replica_b.publicar("emprestimo.criado", {"id": 3}, dono_id=7)
            await asyncio.sleep(0.05)
            self.assertIn("emprestimo.criado", aluno.tipos())
            self.assertIn("emprestimo.criado", biblio.tipos())
            self.assertNotIn("emprestimo.criado", outro_aluno.tipos())
            await replica_a.encerrar()
            await replica_b.encerrar()

        asyncio.run(cenario())

    def test_sem_intermediario_entrega_direto_como_na_v2(self):
        async def cenario():
            central = CentralDeEventos("catalogo")
            await central.iniciar()
            navegador = ConexaoFalsa()
            await central.conectar(navegador, BIBLIOTECARIA)
            await central.publicar("livro.criado", {"id": 1})
            self.assertIn("livro.criado", navegador.tipos())
            await central.encerrar()

        asyncio.run(cenario())

    def test_redis_fora_do_ar_entrega_ao_menos_nesta_replica(self):
        async def cenario():
            redis = BrokerEmMemoria()
            central = CentralDeEventos("catalogo", redis)
            navegador = ConexaoFalsa()
            await central.conectar(navegador, BIBLIOTECARIA)
            redis.falhar_publicacao = True
            with self.assertLogs("booknet.eventos", level="WARNING"):
                await central.publicar("livro.criado", {"id": 1})
            self.assertIn("livro.criado", navegador.tipos())

        asyncio.run(cenario())

    def test_escuta_do_redis_se_recupera_de_quedas(self):
        class BrokerInstavel(BrokerEmMemoria):
            def __init__(self):
                super().__init__()
                self.quedas = 1

            async def escutar(self, canal):
                if self.quedas:
                    self.quedas -= 1
                    raise ConnectionError("conexão com o Redis caiu")
                async for mensagem in super().escutar(canal):
                    yield mensagem

        dormir_de_verdade = asyncio.sleep

        async def cenario():
            redis = BrokerInstavel()
            central = CentralDeEventos("catalogo", redis)
            navegador = ConexaoFalsa()
            await central.conectar(navegador, BIBLIOTECARIA)
            with patch("backend.eventos.asyncio.sleep", new=lambda _s: dormir_de_verdade(0)):
                await central.iniciar()
                for _ in range(5):
                    await dormir_de_verdade(0)
            await central.publicar("livro.criado", {"id": 1})
            await dormir_de_verdade(0.05)
            self.assertIn("livro.criado", navegador.tipos())
            await central.encerrar()

        with self.assertLogs("booknet.eventos", level="WARNING"):
            asyncio.run(cenario())

    def test_broker_so_e_criado_com_redis_configurado(self):
        with patch.object(config, "REDIS_URL", ""):
            self.assertIsNone(modulo_broker.criar_broker())
        with patch.object(config, "REDIS_URL", "redis://redis:6379/0"):
            self.assertIsInstance(modulo_broker.criar_broker(), modulo_broker.BrokerRedis)


if __name__ == "__main__":
    unittest.main()
