"""Define (ou troca) a senha de login de um usuário direto no banco.

Uso, na raiz booknet/ (usa a DATABASE_URL do .env):
    .venv\\Scripts\\python.exe scripts\\definir_senha.py <matricula>

A senha é pedida no terminal, sem aparecer na tela. Serve para criar o primeiro
acesso de bibliotecário; depois disso, as senhas podem ser definidas pela tela de
Usuários do próprio sistema. Só o hash da senha é gravado.
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from backend.autenticacao import gerar_hash_senha  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.models import Usuario  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    matricula = sys.argv[1]
    with SessionLocal() as sessao:
        usuario = sessao.scalar(select(Usuario).where(Usuario.matricula == matricula))
        if usuario is None:
            sys.exit(f"Nenhum usuário com a matrícula {matricula}.")
        senha = getpass.getpass(f"Nova senha para {usuario.nome} ({usuario.tipo.value}): ")
        if len(senha) < 6:
            sys.exit("A senha precisa ter pelo menos 6 caracteres.")
        if getpass.getpass("Repita a senha: ") != senha:
            sys.exit("As senhas não conferem.")
        usuario.senha_hash = gerar_hash_senha(senha)
        sessao.commit()
    print(f"Senha definida para {usuario.nome}.")


if __name__ == "__main__":
    main()
