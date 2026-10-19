"""Schemas de entrada e saída dos usuários da biblioteca."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from backend.models.usuario import TipoUsuario


TextoNome = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=255)
]
# Validação simples de formato; não confirma que o endereço exista.
TextoEmail = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]
TextoMatricula = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=30)
]


class UsuarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: TextoNome
    email: TextoEmail
    matricula: TextoMatricula
    tipo: TipoUsuario = TipoUsuario.ALUNO
    ativo: bool = True


class UsuarioUpdate(UsuarioCreate):
    """PUT substitui os campos editáveis; nome, e-mail e matrícula são obrigatórios."""


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    matricula: str
    tipo: TipoUsuario
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
