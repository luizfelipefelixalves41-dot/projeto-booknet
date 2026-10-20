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
# Senha de login: mínimo de 6 caracteres; espaços contam (não são removidos).
TextoSenha = Annotated[str, StringConstraints(strict=True, min_length=6, max_length=128)]


class UsuarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: TextoNome
    email: TextoEmail
    matricula: TextoMatricula
    tipo: TipoUsuario = TipoUsuario.ALUNO
    ativo: bool = True
    # Opcional: sem senha, o usuário é cadastrado mas ainda não consegue entrar.
    senha: TextoSenha | None = None


class UsuarioUpdate(UsuarioCreate):
    """PUT substitui os campos editáveis; nome, e-mail e matrícula são obrigatórios.

    ``senha`` omitida mantém a senha atual; informada, define uma nova."""


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    matricula: str
    tipo: TipoUsuario
    ativo: bool
    tem_senha: bool
    criado_em: datetime
    atualizado_em: datetime


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matricula: TextoMatricula
    senha: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
    # Aba escolhida na tela de login; se não combinar com a conta, o login é recusado.
    perfil: TipoUsuario | None = None


class LoginResponse(BaseModel):
    token: str
    expira_em_segundos: int
    usuario: UsuarioResponse
