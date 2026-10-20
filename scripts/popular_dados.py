"""Cadastra dados de demonstração pela API (cliente HTTP, sem acesso direto ao banco).

Pede a senha do bibliotecário (BIB-001) ou usa BOOKNET_SENHA.
Uso, com os serviços em execução (scripts\\iniciar_servicos.py):
    .venv\\Scripts\\python.exe scripts\\popular_dados.py

Pode ser executado mais de uma vez: registros já existentes (409) são ignorados.
"""

import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORTAS = {"/usuarios": 8002, "/auth": 8002, "/emprestimos": 8003}  # V3: o resto é do Catálogo (8001)
TOKEN = None  # preenchido pelo login


def url_do_servico(caminho: str) -> str:
    porta = next((p for prefixo, p in PORTAS.items() if caminho.startswith(prefixo)), 8001)
    return f"http://{HOST}:{porta}{caminho}"

LIVROS = [
    ("Sistemas Distribuídos: Princípios e Paradigmas", "Andrew S. Tanenbaum", "9788576051428", 3),
    ("Redes de Computadores e a Internet", "James F. Kurose", "9788543014432", 2),
    ("Sistemas Operacionais Modernos", "Andrew S. Tanenbaum", "9788543005676", 2),
    ("Projeto de Banco de Dados", "Carlos A. Heuser", "9788577803828", 1),
    ("Arquitetura Limpa", "Robert C. Martin", "9788550804606", 1),
]
USUARIOS = [
    ("André", "andre@booknet.edu", "2026001", "ALUNO"),
    ("João Henrique", "joao.henrique@booknet.edu", "2026002", "ALUNO"),
    ("Luiz Felipe", "luiz.felipe@booknet.edu", "2026003", "ALUNO"),
    ("Bibliotecária BookNet", "biblioteca@booknet.edu", "BIB-001", "BIBLIOTECARIO"),
]


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
    for titulo, autor, isbn, copias in LIVROS:
        status, livro = chamar("POST", "/livros", {"titulo": titulo, "autor": autor, "isbn": isbn})
        if status == 409:
            print(f"Livro já cadastrado: {titulo}")
            continue
        print(f"Livro {livro['id']}: {titulo}")
        for numero in range(1, copias + 1):
            tombo = f"{isbn[-4:]}-{numero:02d}"
            chamar("POST", f"/livros/{livro['id']}/exemplares", {"codigo_tombo": tombo})
            print(f"  exemplar {tombo}")

    for nome, email, matricula, tipo in USUARIOS:
        status, _ = chamar(
            "POST", "/usuarios", {"nome": nome, "email": email, "matricula": matricula, "tipo": tipo}
        )
        print(("Usuário cadastrado: " if status == 201 else "Usuário já cadastrado: ") + nome)


if __name__ == "__main__":
    main()
