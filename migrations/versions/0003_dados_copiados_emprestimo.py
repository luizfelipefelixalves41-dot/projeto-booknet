"""V3: empréstimos guardam cópia dos dados de usuário e exemplar.

Revision ID: 0003_dados_copiados_emprestimo
Revises: 0002_usuarios_emprestimos

Com serviços separados, o Serviço de Empréstimos não consulta mais as tabelas
de usuários, exemplares e livros. Ele passa a guardar, no próprio registro, os
dados de que precisa para exibir o empréstimo. Os empréstimos já existentes são
preenchidos a partir das tabelas atuais antes de as colunas virarem obrigatórias.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_dados_copiados_emprestimo"
down_revision: Union[str, Sequence[str], None] = "0002_usuarios_emprestimos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUNAS = {
    "usuario_nome": sa.String(length=255),
    "codigo_tombo": sa.String(length=50),
    "livro_id": sa.Integer(),
    "livro_titulo": sa.String(length=255),
}


def upgrade() -> None:
    for nome, tipo in COLUNAS.items():
        op.add_column("emprestimos", sa.Column(nome, tipo, nullable=True))
    op.execute(
        """
        UPDATE emprestimos AS e
           SET usuario_nome = u.nome,
               codigo_tombo = x.codigo_tombo,
               livro_id     = l.id,
               livro_titulo = l.titulo
          FROM usuarios AS u, exemplares AS x, livros AS l
         WHERE u.id = e.usuario_id
           AND x.id = e.exemplar_id
           AND l.id = x.livro_id
        """
    )
    for nome, tipo in COLUNAS.items():
        op.alter_column("emprestimos", nome, existing_type=tipo, nullable=False)


def downgrade() -> None:
    """Remove as cópias; os dados originais continuam nas tabelas de origem."""
    for nome in reversed(list(COLUNAS)):
        op.drop_column("emprestimos", nome)
