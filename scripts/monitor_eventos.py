"""Painel de terminal que escuta os eventos do BookNet em tempo real (V2).

Uso, com a API em execução:
    .venv\\Scripts\\python.exe scripts\\monitor_eventos.py                # mesma máquina
    .venv\\Scripts\\python.exe scripts\\monitor_eventos.py 192.168.0.101  # outro computador

Mostra que o canal de mensagens não depende do navegador: qualquer programa que
abra um WebSocket recebe os mesmos eventos. Encerre com Ctrl+C.
"""

import json
import sys
import time
from datetime import datetime

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
URL = f"ws://{HOST}:8000/ws/eventos"


def formatar(evento: dict) -> str:
    dados = evento["dados"]
    hora = datetime.fromisoformat(evento["momento"]).astimezone().strftime("%H:%M:%S")
    tipo = evento["tipo"]
    if tipo in ("conectado", "conexoes.alteradas"):
        detalhe = f"{dados['conexoes']} conexão(ões) abertas"
    elif tipo.startswith("emprestimo."):
        detalhe = f"#{dados['id']} {dados['usuario_nome']} · {dados['livro_titulo']} · {dados['codigo_tombo']}"
    else:
        detalhe = dados.get("titulo") or dados.get("nome") or dados.get("codigo_tombo") or ""
    return f"[{hora}] {tipo:<22} {detalhe}"


def main() -> None:
    espera = 1
    while True:
        try:
            with connect(URL, open_timeout=10) as ws:
                print(f"Conectado a {URL}. Aguardando eventos...", flush=True)
                espera = 1
                for bruta in ws:
                    print(formatar(json.loads(bruta)), flush=True)
        except (OSError, ConnectionClosed, TimeoutError):
            print(f"Sem conexão com {URL}. Nova tentativa em {espera}s.", flush=True)
            time.sleep(espera)
            espera = min(espera * 2, 30)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
