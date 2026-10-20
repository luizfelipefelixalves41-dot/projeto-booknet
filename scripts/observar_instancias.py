"""V6: mostra o orquestrador trabalhando (balanceamento e disponibilidade).

Uso, com o BookNet rodando no Docker Swarm (docker-stack.yml):
    .venv\\Scripts\\python.exe scripts\\observar_instancias.py catalogo            # quem responde?
    .venv\\Scripts\\python.exe scripts\\observar_instancias.py catalogo --por 60   # 60 s sem parar

O /health de cada serviço informa o nome da réplica (contêiner) que respondeu.
- Modo rápido: 12 pedidos seguidos; com 2 réplicas, as respostas se alternam.
- Modo contínuo: 4 pedidos por segundo. Rode-o enquanto derruba uma réplica ou faz
  "docker service update --force booknet_catalogo" e veja se algum pedido falha.
"""

import argparse
import json
import time
from collections import Counter
from urllib.request import urlopen

PORTAS = {"catalogo": 8001, "usuarios": 8002, "emprestimos": 8003}


def consultar(url: str) -> str | None:
    try:
        with urlopen(url, timeout=3) as resposta:
            return json.loads(resposta.read())["instancia"]
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("servico", choices=PORTAS)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--por", type=float, default=0, help="segundos de observação contínua")
    args = parser.parse_args()
    url = f"http://{args.host}:{PORTAS[args.servico]}/health"

    if not args.por:
        respostas = [consultar(url) for _ in range(12)]
        for numero, instancia in enumerate(respostas, 1):
            print(f"  pedido {numero:>2} → {instancia or 'FALHOU'}")
        print("\nRéplicas que responderam:", dict(Counter(r for r in respostas if r)))
        return

    print(f"Observando {url} por {args.por:.0f} s (4 pedidos/s)...")
    contagem, falhas, fim = Counter(), 0, time.monotonic() + args.por
    while time.monotonic() < fim:
        instancia = consultar(url)
        if instancia is None:
            falhas += 1
            print(f"  {time.strftime('%H:%M:%S')}  FALHOU", flush=True)
        else:
            if instancia not in contagem:
                print(f"  {time.strftime('%H:%M:%S')}  réplica respondendo: {instancia}", flush=True)
            contagem[instancia] += 1
        time.sleep(0.25)
    total = sum(contagem.values()) + falhas
    print(f"\n{total} pedidos · {falhas} falha(s) · disponibilidade {100 * (total - falhas) / total:.1f}%")
    print("Respostas por réplica:", dict(contagem))


if __name__ == "__main__":
    main()
