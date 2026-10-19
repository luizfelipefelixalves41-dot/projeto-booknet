"""Sobe os três serviços do BookNet e o Cliente Web com um único comando (V3).

Uso, na raiz booknet/:
    .venv\\Scripts\\python.exe scripts\\iniciar_servicos.py           # só este computador
    .venv\\Scripts\\python.exe scripts\\iniciar_servicos.py --rede    # aceita outros PCs da rede
    .venv\\Scripts\\python.exe scripts\\iniciar_servicos.py --sem catalogo   # para demonstrar falhas

Cada serviço é um processo separado. Os logs aparecem juntos, identificados pelo
nome do serviço. Ctrl+C encerra todos.
"""

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SERVICOS = {
    "catalogo": ("backend.servicos.catalogo:app", 8001),
    "usuarios": ("backend.servicos.usuarios:app", 8002),
    "emprestimos": ("backend.servicos.emprestimos:app", 8003),
}


def repassar_saida(nome: str, processo: subprocess.Popen) -> None:
    for linha in processo.stdout:
        print(f"[{nome:<11}] {linha.rstrip()}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rede", action="store_true", help="escuta em 0.0.0.0 (outros PCs da rede)")
    parser.add_argument("--sem", nargs="*", default=[], choices=list(SERVICOS), help="serviços que não sobem")
    argumentos = parser.parse_args()
    host = "0.0.0.0" if argumentos.rede else "127.0.0.1"

    comandos = {
        nome: [sys.executable, "-m", "uvicorn", alvo, "--host", host, "--port", str(porta)]
        for nome, (alvo, porta) in SERVICOS.items()
        if nome not in argumentos.sem
    }
    # O servidor estático serve SOMENTE cliente/: a raiz contém o .env.
    comandos["cliente"] = [
        sys.executable, "-m", "http.server", "8080", "--bind", host, "--directory", str(RAIZ / "cliente"),
    ]

    processos = {}
    for nome, comando in comandos.items():
        processos[nome] = subprocess.Popen(
            comando, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        threading.Thread(target=repassar_saida, args=(nome, processos[nome]), daemon=True).start()

    endereco = "IP_DESTE_PC" if argumentos.rede else "127.0.0.1"
    print(f"\nBookNet V3 iniciando. Cliente Web: http://{endereco}:8080", flush=True)
    for nome, (_, porta) in SERVICOS.items():
        situacao = "desligado (--sem)" if nome in argumentos.sem else f"http://{endereco}:{porta}/docs"
        print(f"  {nome:<11} porta {porta}  {situacao}", flush=True)
    print("Ctrl+C encerra todos os serviços.\n", flush=True)

    try:
        # Um serviço que cai NÃO derruba os outros: é isso que permite demonstrar
        # a falha 1 (Empréstimos fora do ar enquanto o Catálogo continua atendendo).
        avisados = set()
        while any(processo.poll() is None for processo in processos.values()):
            for nome, processo in processos.items():
                if processo.poll() is not None and nome not in avisados:
                    avisados.add(nome)
                    print(f"\n*** {nome} parou (código {processo.returncode}). Os demais continuam. ***\n", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nEncerrando...", flush=True)
    finally:
        for processo in processos.values():
            if processo.poll() is None:
                processo.terminate()
        for processo in processos.values():
            try:
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.kill()


if __name__ == "__main__":
    main()
