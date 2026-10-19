"""Cria as tabelas de usuários e empréstimos da V1.

Revision ID: 0002_usuarios_emprestimos
Revises: 0001_catalogo

O índice único parcial garante no banco que um exemplar tenha no máximo um
empréstimo ATIVO, mesmo com requisições simultâneas.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_usuarios_emprestimos"
down_revision: Union[str, Sequence[str], None] = "0001_catalogo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("matricula", sa.String(length=30), nullable=False),
        sa.Column("tipo", sa.String(length=13), server_default="ALUNO", nullable=False),
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
        sa.UniqueConstraint("email", name="uq_usuarios_email"),
        sa.UniqueConstraint("matricula", name="uq_usuarios_matricula"),
        sa.CheckConstraint(
            "length(trim(nome)) > 0 AND length(nome) <= 255", name="ck_usuarios_nome_valido"
        ),
        sa.CheckConstraint(
            "length(trim(email)) > 0 AND length(email) <= 255", name="ck_usuarios_email_valido"
        ),
        sa.CheckConstraint(
            "length(trim(matricula)) > 0 AND length(matricula) <= 30",
            name="ck_usuarios_matricula_valida",
        ),
        sa.CheckConstraint("tipo IN ('ALUNO', 'BIBLIOTECARIO')", name="ck_usuarios_tipo"),
    )
    op.create_table(
        "emprestimos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("exemplar_id", sa.Integer(), nullable=False),
        sa.Column(
            "data_emprestimo",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("data_prevista_devolucao", sa.Date(), nullable=False),
        sa.Column("data_devolucao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=9), server_default="ATIVO", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_emprestimos_usuario_id_usuarios",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exemplar_id"],
            ["exemplares.id"],
            name="fk_emprestimos_exemplar_id_exemplares",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('ATIVO', 'DEVOLVIDO')", name="ck_emprestimos_status"),
        sa.CheckConstraint(
            "(status = 'ATIVO' AND data_devolucao IS NULL) OR "
            "(status = 'DEVOLVIDO' AND data_devolucao IS NOT NULL)",
            name="ck_emprestimos_devolucao_coerente",
        ),
    )
    op.create_index("ix_emprestimos_usuario_id", "emprestimos", ["usuario_id"], unique=False)
    op.create_index("ix_emprestimos_exemplar_id", "emprestimos", ["exemplar_id"], unique=False)
    op.create_index(
        "uq_emprestimos_exemplar_ativo",
        "emprestimos",
        ["exemplar_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ATIVO'"),
    )


def downgrade() -> None:
    """Remove usuários e empréstimos; a execução apagaria esses dados."""
    op.drop_index("uq_emprestimos_exemplar_ativo", table_name="emprestimos")
    op.drop_index("ix_emprestimos_exemplar_id", table_name="emprestimos")
    op.drop_index("ix_emprestimos_usuario_id", table_name="emprestimos")
    op.drop_table("emprestimos")
    op.drop_table("usuarios")
