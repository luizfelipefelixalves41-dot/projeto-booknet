"""Modelo de exemplar com integridade garantida também pelo banco."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum as SQLAlchemyEnum
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.livro import Livro


class StatusExemplar(str, Enum):
    DISPONIVEL = "DISPONIVEL"
    EMPRESTADO = "EMPRESTADO"


class Exemplar(Base):
    __tablename__ = "exemplares"
    __table_args__ = (
        UniqueConstraint("codigo_tombo", name="uq_exemplares_codigo_tombo"),
        CheckConstraint(
            "length(trim(codigo_tombo)) > 0 AND length(codigo_tombo) <= 50",
            name="ck_exemplares_codigo_tombo_valido",
        ),
        Index("ix_exemplares_livro_id", "livro_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    livro_id: Mapped[int] = mapped_column(
        ForeignKey("livros.id", name="fk_exemplares_livro_id_livros", ondelete="RESTRICT"),
        nullable=False,
    )
    codigo_tombo: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[StatusExemplar] = mapped_column(
        SQLAlchemyEnum(
            StatusExemplar,
            name="ck_exemplares_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=10,
        ),
        nullable=False,
        server_default=StatusExemplar.DISPONIVEL.value,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # V5: momento da última mudança de status (retirada ou liberação). A reconciliação
    # usa isso para não mexer em exemplares que podem estar no meio de um empréstimo.
    alterado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    livro: Mapped[Livro] = relationship(back_populates="exemplares", lazy="raise")

