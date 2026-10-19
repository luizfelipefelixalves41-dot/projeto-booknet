"""Painel de terminal que escuta os eventos do BookNet em tempo real (V2/V3).

Uso, com os serviços em execução:
    .venv\\Scripts\\python.exe scripts\\monitor_eventos.py                # mesma máquina
    .venv\\Scripts\\python.exe scripts\\monitor_eventos.py 192.168.0.101  # outro computador

Mostra que o canal de mensagens não depende do navegador: qualquer programa que
abra um WebSocket recebe os mesmos eventos. Na V3 cada serviço tem seu canal, e
o monitor escuta os três ao mesmo tempo. Encerre com Ctrl+C.
"""

import json
import sys
import threading
import time
from datetime import datetime

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
CANAIS = {"catalogo": 8001, "usuarios": 8002, "emprestimos": 8003}
_saida = threading.Lock()


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
    url = f"ws://{HOST}:{porta}/ws/eventos"
    espera = 1
    while True:
        try:
            with connect(url, open_timeout=10) as ws:
                mostrar(f"Conectado a {url}")
                espera = 1
                for bruta in ws:
                    mostrar(formatar(servico, json.loads(bruta)))
        except (OSError, ConnectionClosed, TimeoutError):
            mostrar(f"[{servico}] sem conexão com {url}. Nova tentativa em {espera}s.")
            time.sleep(espera)
            espera = min(espera * 2, 30)


def main() -> None:
    for servico, porta in CANAIS.items():
        threading.Thread(target=escutar, args=(servico, porta), daemon=True).start()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
