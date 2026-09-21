"""Operações iniciais do catálogo, sem exclusão de registros."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.dependencies.database import get_db
from backend.models.exemplar import Exemplar
from backend.models.livro import Livro
from backend.schemas.exemplar import ExemplarCreate, ExemplarResponse
from backend.schemas.livro import LivroCreate, LivroResponse, LivroUpdate


router = APIRouter(prefix="/livros", tags=["Catálogo"])
logger = logging.getLogger("booknet.catalogo")
Banco = Annotated[Session, Depends(get_db, scope="function")]
LivroId = Annotated[int, Path(gt=0)]


def _buscar_livro(db: Session, livro_id: int) -> Livro:
    livro = db.get(Livro, livro_id)
    if livro is None:
        raise HTTPException(status_code=404, detail="Livro não encontrado.")
    return livro


@router.get("", response_model=list[LivroResponse], summary="Listar livros ativos")
def listar_livros(
    db: Banco,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=255)] = None,
) -> list[Livro]:
    consulta = select(Livro).where(Livro.ativo.is_(True))
    if q and (busca := q.strip()):
        consulta = consulta.where(
            or_(
                Livro.titulo.icontains(busca, autoescape=True),
                Livro.autor.icontains(busca, autoescape=True),
                Livro.isbn.icontains(busca, autoescape=True),
            )
        )
    consulta = consulta.order_by(Livro.id).offset(skip).limit(limit)
    return list(db.scalars(consulta).all())


@router.get("/{livro_id}", response_model=LivroResponse, summary="Consultar livro")
def consultar_livro(livro_id: LivroId, db: Banco) -> Livro:
    return _buscar_livro(db, livro_id)


@router.post(
    "", response_model=LivroResponse, status_code=status.HTTP_201_CREATED, summary="Cadastrar livro"
)
def criar_livro(dados: LivroCreate, db: Banco) -> Livro:
    livro = Livro(**dados.model_dump())
    db.add(livro)
    db.commit()
    db.refresh(livro)
    logger.info("Livro cadastrado com sucesso. id=%s", livro.id)
    return livro


@router.put("/{livro_id}", response_model=LivroResponse, summary="Atualizar livro")
def atualizar_livro(livro_id: LivroId, dados: LivroUpdate, db: Banco) -> Livro:
    livro = _buscar_livro(db, livro_id)
    for campo, valor in dados.model_dump().items():
        setattr(livro, campo, valor)
    db.commit()
    db.refresh(livro)
    logger.info("Livro atualizado com sucesso. id=%s", livro.id)
    return livro


@router.get(
    "/{livro_id}/exemplares", response_model=list[ExemplarResponse], summary="Listar exemplares"
)
def listar_exemplares(livro_id: LivroId, db: Banco) -> list[Exemplar]:
    _buscar_livro(db, livro_id)
    consulta = select(Exemplar).where(Exemplar.livro_id == livro_id).order_by(Exemplar.id)
    return list(db.scalars(consulta).all())


@router.post(
    "/{livro_id}/exemplares",
    response_model=ExemplarResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar exemplar",
)
def criar_exemplar(livro_id: LivroId, dados: ExemplarCreate, db: Banco) -> Exemplar:
    _buscar_livro(db, livro_id)
    exemplar = Exemplar(livro_id=livro_id, **dados.model_dump())
    db.add(exemplar)
    db.commit()
    db.refresh(exemplar)
    logger.info("Exemplar cadastrado com sucesso. id=%s", exemplar.id)
    return exemplar
