"""Modelo de livro; cada exemplar representa uma cópia física."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.exemplar import Exemplar


class Livro(Base):
    __tablename__ = "livros"
    __table_args__ = (
        UniqueConstraint("isbn", name="uq_livros_isbn"),
        CheckConstraint(
            "length(trim(titulo)) > 0 AND length(titulo) <= 255",
            name="ck_livros_titulo_valido",
        ),
        CheckConstraint(
            "length(trim(autor)) > 0 AND length(autor) <= 255",
            name="ck_livros_autor_valido",
        ),
        CheckConstraint(
            "length(trim(isbn)) > 0 AND length(isbn) <= 20",
            name="ck_livros_isbn_valido",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    autor: Mapped[str] = mapped_column(String(255), nullable=False)
    isbn: Mapped[str] = mapped_column(String(20), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    exemplares: Mapped[list[Exemplar]] = relationship(
        back_populates="livro",
        lazy="raise",
        cascade="save-update, merge",
        passive_deletes="all",
    )

