"""Demonstra a falha 2 da V0: vários usuários pedindo o MESMO exemplar ao mesmo tempo.

Pede a senha do bibliotecário (BIB-001) ou usa BOOKNET_SENHA.
Uso, com os serviços em execução e os dados de demonstração cadastrados:
    .venv\\Scripts\\python.exe scripts\\teste_concorrencia.py

O script cria um exemplar novo, dispara requisições simultâneas de usuários
diferentes e confere o resultado: exatamente um 201 e os demais 409. Ao final,
devolve o empréstimo para deixar o exemplar disponível.
"""

import json
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORTAS = {"/usuarios": 8002, "/auth": 8002, "/emprestimos": 8003}  # V3: o resto é do Catálogo (8001)
TOKEN = None  # preenchido pelo login


def url_do_servico(caminho: str) -> str:
    porta = next((p for prefixo, p in PORTAS.items() if caminho.startswith(prefixo)), 8001)
    return f"http://{HOST}:{porta}{caminho}"


def chamar(metodo, caminho, dados=None):
    corpo = json.dumps(dados).encode("utf-8") if dados is not None else None
    cabecalhos = {"Content-Type": "application/json"}
    if TOKEN:
        cabecalhos["Authorization"] = f"Bearer {TOKEN}"
    requisicao = Request(url_do_servico(caminho), data=corpo, method=metodo, headers=cabecalhos)
    try:
        with urlopen(requisicao, timeout=30) as resposta:
            return resposta.status, json.loads(resposta.read())
    except HTTPError as erro:
        return erro.code, json.loads(erro.read() or b"{}")


def entrar_como_bibliotecario() -> str:
    """Desde o login, os serviços exigem um token de sessão de bibliotecário.
    A senha vem de BOOKNET_SENHA ou é pedida no terminal (sem aparecer na tela)."""
    import getpass
    import os

    matricula = os.getenv("BOOKNET_MATRICULA", "BIB-001")
    senha = os.getenv("BOOKNET_SENHA") or getpass.getpass(f"Senha de {matricula}: ")
    status, corpo = chamar("POST", "/auth/login", {"matricula": matricula, "senha": senha})
    if status != 200:
        sys.exit(f"Login recusado: {corpo.get('detail')}")
    return corpo["token"]


def main() -> None:
    global TOKEN
    TOKEN = entrar_como_bibliotecario()
    _, usuarios = chamar("GET", "/usuarios?limit=100")
    _, livros = chamar("GET", "/livros?limit=1")
    if len(usuarios) < 2 or not livros:
        sys.exit("Cadastre ao menos 1 livro e 2 usuários (scripts/popular_dados.py).")

    tombo = f"CONC-{int(time.time())}"
    _, exemplar = chamar("POST", f"/livros/{livros[0]['id']}/exemplares", {"codigo_tombo": tombo})
    print(f"Exemplar disputado: id={exemplar['id']} tombo={tombo}")

    resultados = []
    largada = threading.Barrier(len(usuarios))

    def pedir(usuario):
        largada.wait()  # todas as threads disparam juntas
        status, corpo = chamar(
            "POST", "/emprestimos", {"usuario_id": usuario["id"], "exemplar_id": exemplar["id"]}
        )
        resultados.append((usuario["nome"], status, corpo))

    threads = [threading.Thread(target=pedir, args=(usuario,)) for usuario in usuarios]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for nome, status, corpo in sorted(resultados, key=lambda item: item[1]):
        detalhe = f"empréstimo {corpo['id']}" if status == 201 else corpo.get("detail")
        print(f"  {nome:<25} HTTP {status}  {detalhe}")

    sucessos = [corpo for _, status, corpo in resultados if status == 201]
    print(f"\nPedidos simultâneos: {len(resultados)} | aprovados: {len(sucessos)}")
    print("RESULTADO:", "OK - apenas um empréstimo registrado." if len(sucessos) == 1 else "FALHA")

    for corpo in sucessos:
        chamar("POST", f"/emprestimos/{corpo['id']}/devolucao")
    sys.exit(0 if len(sucessos) == 1 else 1)


if __name__ == "__main__":
    main()
