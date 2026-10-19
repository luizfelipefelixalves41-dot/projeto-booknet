"""Cadastra dados de demonstração pela API (cliente HTTP, sem acesso direto ao banco).

Uso, com a API em execução na porta 8000:
    .venv\\Scripts\\python.exe scripts\\popular_dados.py

Pode ser executado mais de uma vez: registros já existentes (409) são ignorados.
"""

import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

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
    requisicao = Request(
        API + caminho, data=corpo, method=metodo, headers={"Content-Type": "application/json"}
    )
    try:
        with urlopen(requisicao, timeout=30) as resposta:
            return resposta.status, json.loads(resposta.read())
    except HTTPError as erro:
        return erro.code, json.loads(erro.read() or b"{}")


def main() -> None:
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
