"""Schemas para cadastro e consulta das unidades físicas de um livro."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from backend.models.exemplar import StatusExemplar


class ExemplarCreate(BaseModel):
    """Todo exemplar nasce DISPONIVEL; só empréstimos e devoluções alteram o status."""

    model_config = ConfigDict(extra="forbid")

    codigo_tombo: Annotated[
        str,
        StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=50),
    ]
    status: Literal[StatusExemplar.DISPONIVEL] = StatusExemplar.DISPONIVEL


class ExemplarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    livro_id: int
    codigo_tombo: str
    status: StatusExemplar
    criado_em: datetime


class ExemplarRetiradaResponse(ExemplarResponse):
    """Resposta da retirada: inclui o título para o Serviço de Empréstimos guardar."""

    livro_titulo: str
