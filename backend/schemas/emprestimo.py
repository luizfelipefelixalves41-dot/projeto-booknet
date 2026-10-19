"""Schemas de empréstimo e devolução."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from backend.models.emprestimo import StatusEmprestimo


PRAZO_PADRAO_DIAS = 14


class EmprestimoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: Annotated[int, Field(strict=True, gt=0)]
    exemplar_id: Annotated[int, Field(strict=True, gt=0)]
    prazo_dias: Annotated[int, Field(strict=True, ge=1, le=60)] = PRAZO_PADRAO_DIAS


class EmprestimoResponse(BaseModel):
    """Empréstimo com dados de leitura do usuário e do livro para exibição no cliente."""

    id: int
    usuario_id: int
    exemplar_id: int
    data_emprestimo: datetime
    data_prevista_devolucao: date
    data_devolucao: datetime | None
    status: StatusEmprestimo
    atrasado: bool
    usuario_nome: str
    codigo_tombo: str
    livro_id: int
    livro_titulo: str
