"""Validação do catálogo, separada dos modelos de persistência."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


TextoLivro = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=255)
]
TextoISBN = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=20)
]


class LivroCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: TextoLivro
    autor: TextoLivro
    isbn: TextoISBN
    ativo: bool = True


class LivroUpdate(BaseModel):
    """PUT substitui os campos editáveis; título, autor e ISBN são obrigatórios."""

    model_config = ConfigDict(extra="forbid")

    titulo: TextoLivro
    autor: TextoLivro
    isbn: TextoISBN
    ativo: bool = True


class LivroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    autor: str
    isbn: str
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
