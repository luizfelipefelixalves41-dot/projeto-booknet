"""V2: canal WebSocket de eventos, testado por ASGI no próprio processo.

Execução: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import json
import unittest

from tests.apoio import APPS, BancoIsoladoTestCase, _requisicao_asgi, app_emprestimos
from backend.eventos import CentralDeEventos


class ConexaoWS:
    """Cliente WebSocket mínimo falando ASGI diretamente com a aplicação."""

    def __init__(self, origem: str | None = "http://localhost:8080", servico: str = "emprestimos"):
        self.origem = origem
        self.app = APPS[servico]
        self.entrada: asyncio.Queue = asyncio.Queue()
        self.saida: asyncio.Queue = asyncio.Queue()
        self.tarefa: asyncio.Task | None = None

    async def abrir(self) -> dict:
        cabecalhos = [(b"host", b"testserver")]
        if self.origem:
            cabecalhos.append((b"origin", self.origem.encode("ascii")))
        escopo = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": "/ws/eventos",
            "raw_path": b"/ws/eventos",
            "query_string": b"",
            "root_path": "",
            "headers": cabecalhos,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "subprotocols": [],
        }
        await self.entrada.put({"type": "websocket.connect"})
        self.tarefa = asyncio.create_task(self.app(escopo, self.entrada.get, self.saida.put))
        return await asyncio.wait_for(self.saida.get(), 2)

    async def receber(self, tipo: str) -> dict:
        """Lê mensagens até encontrar o tipo pedido (ignora avisos de conexões)."""
        while True:
            bruta = await asyncio.wait_for(self.saida.get(), 2)
            mensagem = json.loads(bruta["text"])
            if mensagem["tipo"] == tipo:
                return mensagem

    def pendentes(self) -> list[str]:
        tipos = []
        while not self.saida.empty():
            tipos.append(json.loads(self.saida.get_nowait()["text"])["tipo"])
        return tipos

    async def enviar(self, texto: str) -> None:
        await self.entrada.put({"type": "websocket.receive", "text": texto})

    async def fechar(self) -> None:
        await self.entrada.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(self.tarefa, 2)


class EventosTestes(BancoIsoladoTestCase):
    def executar(self, cenario):
        return asyncio.run(cenario())

    def test_conexao_recebe_boas_vindas_e_responde_ping(self):
        async def cenario():
            ws = ConexaoWS()
            self.assertEqual((await ws.abrir())["type"], "websocket.accept")
            self.assertEqual((await ws.receber("conectado"))["dados"], {"conexoes": 1})
            await ws.enviar("ping")
            self.assertEqual((await ws.receber("pong"))["dados"], {})
            await ws.fechar()
            self.assertEqual(app_emprestimos.state.central.total, 0)

        self.executar(cenario)

    def test_origem_nao_permitida_e_recusada_e_rede_local_aceita(self):
        async def cenario():
            for origem in ("https://site-malicioso.invalid", "http://8.8.8.8:8080"):
                with self.subTest(origem=origem):
                    resposta = await ConexaoWS(origem).abrir()
                    self.assertEqual(resposta["type"], "websocket.close")
                    self.assertEqual(resposta["code"], 1008)
            for origem in ("http://192.168.0.15:8080", None):
                with self.subTest(origem=origem):
                    ws = ConexaoWS(origem)
                    self.assertEqual((await ws.abrir())["type"], "websocket.accept")
                    await ws.fechar()
            self.assertEqual(app_emprestimos.state.central.total, 0)

        self.executar(cenario)

    def test_emprestimo_e_devolucao_sao_avisados_a_todas_as_telas(self):
        livro = self.criar_livro(titulo="Redes de Computadores")
        exemplar = self.criar_exemplar(livro["id"])
        usuario = self.criar_usuario(nome="André")

        async def cenario():
            telas = [ConexaoWS(), ConexaoWS("http://192.168.0.20:8080")]
            for tela in telas:
                await tela.abrir()
            self.assertEqual((await telas[1].receber("conectado"))["dados"], {"conexoes": 2})

            resposta = await _requisicao_asgi(
                "POST", "/emprestimos", {"usuario_id": usuario["id"], "exemplar_id": exemplar["id"]}
            )
            self.assertEqual(resposta.status_code, 201)
            for tela in telas:
                evento = await tela.receber("emprestimo.criado")
                self.assertEqual(evento["dados"], resposta.json())
                self.assertEqual(evento["dados"]["usuario_nome"], "André")
                self.assertTrue(evento["momento"])

            devolucao = await _requisicao_asgi("POST", f"/emprestimos/{resposta.json()['id']}/devolucao")
            for tela in telas:
                evento = await tela.receber("emprestimo.devolvido")
                self.assertEqual(evento["dados"]["status"], "DEVOLVIDO")
            self.assertEqual(devolucao.json(), evento["dados"])
            for tela in telas:
                await tela.fechar()

        self.executar(cenario)

    def test_operacao_recusada_nao_gera_evento(self):
        livro = self.criar_livro()
        exemplar = self.criar_exemplar(livro["id"])

        async def cenario():
            ws = ConexaoWS()
            await ws.abrir()
            await ws.receber("conectado")
            await ws.receber("conexoes.alteradas")
            falha = await _requisicao_asgi(
                "POST", "/emprestimos", {"usuario_id": 99999, "exemplar_id": exemplar["id"]}
            )
            self.assertEqual(falha.status_code, 404)
            duplicado = await _requisicao_asgi(
                "POST", "/livros", {"titulo": "X", "autor": "Y", "isbn": livro["isbn"]}
            )
            self.assertEqual(duplicado.status_code, 409)
            await asyncio.sleep(0)
            self.assertEqual(ws.pendentes(), [])
            await ws.fechar()

        self.executar(cenario)

    def test_cada_servico_avisa_no_proprio_canal(self):
        async def cenario():
            canais = {nome: ConexaoWS(servico=nome) for nome in ("catalogo", "usuarios", "emprestimos")}
            for canal in canais.values():
                await canal.abrir()
                await canal.receber("conexoes.alteradas")
            livro = (await _requisicao_asgi(
                "POST", "/livros", {"titulo": "Novo", "autor": "Autora", "isbn": "000999"}
            )).json()
            self.assertEqual((await canais["catalogo"].receber("livro.criado"))["dados"], livro)
            await _requisicao_asgi("POST", f"/livros/{livro['id']}/exemplares", {"codigo_tombo": "EV-1"})
            self.assertEqual(
                (await canais["catalogo"].receber("exemplar.criado"))["dados"]["codigo_tombo"], "EV-1"
            )
            await _requisicao_asgi(
                "POST", "/usuarios", {"nome": "Ana", "email": "ana@booknet.test", "matricula": "EV-9"}
            )
            self.assertEqual((await canais["usuarios"].receber("usuario.criado"))["dados"]["nome"], "Ana")
            await asyncio.sleep(0)
            # V3: processos separados, centrais separadas. Nada vaza para outro canal.
            self.assertEqual(canais["emprestimos"].pendentes(), [])
            self.assertEqual(canais["usuarios"].pendentes(), [])
            for canal in canais.values():
                await canal.fechar()

        self.executar(cenario)

    def test_conexao_quebrada_e_removida_sem_afetar_as_demais(self):
        class Quebrada:
            async def send_json(self, _):
                raise RuntimeError("conexão caiu")

        class Saudavel:
            def __init__(self):
                self.recebidas = []

            async def send_json(self, mensagem):
                self.recebidas.append(mensagem)

        nova = CentralDeEventos()
        saudavel = Saudavel()
        nova._conexoes.update({Quebrada(), saudavel})
        with self.assertLogs("booknet.eventos", level="INFO"):
            asyncio.run(nova.publicar("teste", {"n": 1}))
        self.assertEqual(nova.total, 1)
        self.assertEqual(saudavel.recebidas[0]["dados"], {"n": 1})

    def test_servicos_identificam_versao_3(self):
        for nome in APPS:
            with self.subTest(servico=nome):
                documento = self.requisicao("GET", "/openapi.json", servico=nome).json()
                self.assertEqual(documento["info"]["version"], "3.0.0")
                self.assertEqual(self.requisicao("GET", "/", servico=nome).json()["versao"], "V3")

if __name__ == "__main__":
    unittest.main()
