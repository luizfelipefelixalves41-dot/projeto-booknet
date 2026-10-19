"""Modelo de empréstimo: relaciona um usuário a um exemplar físico."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum as SQLAlchemyEnum
from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class StatusEmprestimo(str, Enum):
    ATIVO = "ATIVO"
    DEVOLVIDO = "DEVOLVIDO"


class Emprestimo(Base):
    __tablename__ = "emprestimos"
    __table_args__ = (
        CheckConstraint(
            "(status = 'ATIVO' AND data_devolucao IS NULL) OR "
            "(status = 'DEVOLVIDO' AND data_devolucao IS NOT NULL)",
            name="ck_emprestimos_devolucao_coerente",
        ),
        Index("ix_emprestimos_usuario_id", "usuario_id"),
        Index("ix_emprestimos_exemplar_id", "exemplar_id"),
        # Garantia final contra concorrência: no máximo um empréstimo ATIVO por exemplar.
        Index(
            "uq_emprestimos_exemplar_ativo",
            "exemplar_id",
            unique=True,
            postgresql_where=text("status = 'ATIVO'"),
            sqlite_where=text("status = 'ATIVO'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", name="fk_emprestimos_usuario_id_usuarios", ondelete="RESTRICT"),
        nullable=False,
    )
    exemplar_id: Mapped[int] = mapped_column(
        ForeignKey(
            "exemplares.id", name="fk_emprestimos_exemplar_id_exemplares", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    data_emprestimo: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    data_prevista_devolucao: Mapped[date] = mapped_column(Date, nullable=False)
    data_devolucao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[StatusEmprestimo] = mapped_column(
        SQLAlchemyEnum(
            StatusEmprestimo,
            name="ck_emprestimos_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=9,
        ),
        nullable=False,
        server_default=StatusEmprestimo.ATIVO.value,
    )

    # V3: cópia dos dados de outros serviços no momento do empréstimo. Assim o
    # Serviço de Empréstimos lista e exibe seus registros sem consultar as tabelas
    # de Usuários e Catálogo, e continua funcionando se eles estiverem fora do ar.
    usuario_nome: Mapped[str] = mapped_column(String(255), nullable=False)
    codigo_tombo: Mapped[str] = mapped_column(String(50), nullable=False)
    livro_id: Mapped[int] = mapped_column(nullable=False)
    livro_titulo: Mapped[str] = mapped_column(String(255), nullable=False)
