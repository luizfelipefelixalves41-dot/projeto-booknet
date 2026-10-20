"""V5: data da última mudança de status do exemplar e senha dos usuários.

Revision ID: 0004_recuperacao_e_login
Revises: 0003_dados_copiados_emprestimo

- exemplares.alterado_em: usada pela reconciliação para ignorar exemplares que
  mudaram há pouco (podem estar no meio de um empréstimo). Os existentes recebem
  o horário da migration.
- usuarios.senha_hash: hash PBKDF2 da senha de login. Fica vazia até alguém
  definir a senha; sem senha, o usuário não consegue entrar.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_recuperacao_e_login"
down_revision: Union[str, Sequence[str], None] = "0003_dados_copiados_emprestimo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exemplares",
        sa.Column(
            "alterado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column("usuarios", sa.Column("senha_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Remove as colunas; as senhas definidas seriam perdidas."""
    op.drop_column("usuarios", "senha_hash")
    op.drop_column("exemplares", "alterado_em")
