"""Prepara as tabelas de livros e exemplares do catálogo V1.1.

Revision ID: 0001_catalogo
Revises: nenhuma

Migration preparada, ainda não aplicada ao Neon. O downgrade é apenas a
definição da reversão e não deve ser executado sem autorização específica.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_catalogo"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria somente as duas tabelas novas e o índice da chave estrangeira."""
    op.create_table(
        "livros",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("autor", sa.String(length=255), nullable=False),
        sa.Column("isbn", sa.String(length=20), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("isbn", name="uq_livros_isbn"),
        sa.CheckConstraint(
            "length(trim(titulo)) > 0 AND length(titulo) <= 255",
            name="ck_livros_titulo_valido",
        ),
        sa.CheckConstraint(
            "length(trim(autor)) > 0 AND length(autor) <= 255",
            name="ck_livros_autor_valido",
        ),
        sa.CheckConstraint(
            "length(trim(isbn)) > 0 AND length(isbn) <= 20", name="ck_livros_isbn_valido"
        ),
    )
    op.create_table(
        "exemplares",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("livro_id", sa.Integer(), nullable=False),
        sa.Column("codigo_tombo", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="DISPONIVEL", nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["livro_id"], ["livros.id"], name="fk_exemplares_livro_id_livros", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("codigo_tombo", name="uq_exemplares_codigo_tombo"),
        sa.CheckConstraint(
            "length(trim(codigo_tombo)) > 0 AND length(codigo_tombo) <= 50",
            name="ck_exemplares_codigo_tombo_valido",
        ),
        sa.CheckConstraint(
            "status IN ('DISPONIVEL', 'EMPRESTADO')", name="ck_exemplares_status"
        ),
    )
    op.create_index("ix_exemplares_livro_id", "exemplares", ["livro_id"], unique=False)


def downgrade() -> None:
    """Define a reversão; sua execução removeria dados e exige autorização."""
    op.drop_index("ix_exemplares_livro_id", table_name="exemplares")
    op.drop_table("exemplares")
    op.drop_table("livros")

