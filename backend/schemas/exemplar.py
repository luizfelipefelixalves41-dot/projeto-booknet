"""Schemas para cadastro e consulta das unidades físicas de um livro."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from backend.models.exemplar import StatusExemplar


class ExemplarCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo_tombo: Annotated[
        str,
        StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=50),
    ]
    status: StatusExemplar = StatusExemplar.DISPONIVEL


class ExemplarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    livro_id: int
    codigo_tombo: str
    status: StatusExemplar
    criado_em: datetime
