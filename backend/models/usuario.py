"""Modelo de usuário da biblioteca: aluno ou bibliotecário."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SQLAlchemyEnum
from sqlalchemy import String, UniqueConstraint, func, true
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class TipoUsuario(str, Enum):
    ALUNO = "ALUNO"
    BIBLIOTECARIO = "BIBLIOTECARIO"


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        UniqueConstraint("email", name="uq_usuarios_email"),
        UniqueConstraint("matricula", name="uq_usuarios_matricula"),
        CheckConstraint(
            "length(trim(nome)) > 0 AND length(nome) <= 255",
            name="ck_usuarios_nome_valido",
        ),
        CheckConstraint(
            "length(trim(email)) > 0 AND length(email) <= 255",
            name="ck_usuarios_email_valido",
        ),
        CheckConstraint(
            "length(trim(matricula)) > 0 AND length(matricula) <= 30",
            name="ck_usuarios_matricula_valida",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    matricula: Mapped[str] = mapped_column(String(30), nullable=False)
    tipo: Mapped[TipoUsuario] = mapped_column(
        SQLAlchemyEnum(
            TipoUsuario,
            name="ck_usuarios_tipo",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=13,
        ),
        nullable=False,
        server_default=TipoUsuario.ALUNO.value,
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    # Login: só o hash da senha é guardado (PBKDF2-SHA256 com sal). Sem senha
    # definida, o usuário existe, mas ainda não consegue entrar no sistema.
    senha_hash: Mapped[str | None] = mapped_column(String(255))

    @property
    def tem_senha(self) -> bool:
        return bool(self.senha_hash)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
