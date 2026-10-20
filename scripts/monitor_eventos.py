"""Painel de terminal que escuta os eventos do BookNet em tempo real (V2/V3).

Uso, com os serviços em execução:
    .venv\\Scripts\\python.exe scripts\\monitor_eventos.py                # mesma máquina
    .venv\\Scripts\\python.exe scripts\\monitor_eventos.py 192.168.0.101  # outro computador

Mostra que o canal de mensagens não depende do navegador: qualquer programa que
abra um WebSocket recebe os mesmos eventos. Na V3 cada serviço tem seu canal, e
o monitor escuta os três ao mesmo tempo. Encerre com Ctrl+C.
"""

import getpass
import json
import os
import sys
import threading
import time
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
CANAIS = {"catalogo": 8001, "usuarios": 8002, "emprestimos": 8003}
_saida = threading.Lock()
TOKEN = ""


def entrar() -> str:
    """O canal de eventos exige login. Bibliotecário recebe todos os eventos;
    aluno, só os do acervo e os próprios empréstimos."""
    matricula = os.getenv("BOOKNET_MATRICULA") or input("Matrícula: ")
    senha = os.getenv("BOOKNET_SENHA") or getpass.getpass("Senha: ")
    pedido = Request(
        f"http://{HOST}:8002/auth/login", method="POST",
        data=json.dumps({"matricula": matricula, "senha": senha}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(pedido, timeout=90) as resposta:
            return json.loads(resposta.read())["token"]
    except HTTPError as erro:
        sys.exit(f"Login recusado: {json.loads(erro.read()).get('detail')}")


def mostrar(texto: str) -> None:
    with _saida:
        print(texto, flush=True)


def formatar(servico: str, evento: dict) -> str:
    dados = evento["dados"]
    hora = datetime.fromisoformat(evento["momento"]).astimezone().strftime("%H:%M:%S")
    tipo = evento["tipo"]
    if tipo in ("conectado", "conexoes.alteradas"):
        detalhe = f"{dados['conexoes']} conexão(ões) abertas"
    elif tipo.startswith("emprestimo."):
        detalhe = f"#{dados['id']} {dados['usuario_nome']} · {dados['livro_titulo']} · {dados['codigo_tombo']}"
    else:
        detalhe = dados.get("titulo") or dados.get("nome") or dados.get("codigo_tombo") or ""
    return f"[{hora}] {servico:<11} {tipo:<22} {detalhe}"


def escutar(servico: str, porta: int) -> None:
    url = f"ws://{HOST}:{porta}/ws/eventos?token={quote(TOKEN)}"
    espera = 1
    while True:
        try:
            with connect(url, open_timeout=10) as ws:
                mostrar(f"Conectado ao canal do serviço {servico} (porta {porta})")
                espera = 1
                for bruta in ws:
                    mostrar(formatar(servico, json.loads(bruta)))
        except (OSError, ConnectionClosed, TimeoutError):
            mostrar(f"[{servico}] sem conexão (porta {porta}). Nova tentativa em {espera}s.")
            time.sleep(espera)
            espera = min(espera * 2, 30)


def main() -> None:
    global TOKEN
    TOKEN = entrar()
    for servico, porta in CANAIS.items():
        threading.Thread(target=escutar, args=(servico, porta), daemon=True).start()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
