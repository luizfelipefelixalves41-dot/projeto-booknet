"""Operações iniciais do catálogo, sem exclusão de registros."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from backend.dependencies.database import get_db
from backend.dependencies.interno import exigir_token_interno
from backend.eventos import Central
from backend.models.exemplar import Exemplar, StatusExemplar
from backend.models.livro import Livro
from backend.schemas.exemplar import ExemplarCreate, ExemplarResponse, ExemplarRetiradaResponse
from backend.schemas.livro import LivroCreate, LivroResponse, LivroUpdate


router = APIRouter(prefix="/livros", tags=["Catálogo"])
router_exemplares = APIRouter(prefix="/exemplares", tags=["Catálogo"])
# Rotas chamadas pelo Serviço de Empréstimos, não pelo navegador.
router_interno = APIRouter(
    prefix="/interno/exemplares",
    tags=["Catálogo (interno)"],
    dependencies=[Depends(exigir_token_interno)],
)
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
def criar_livro(dados: LivroCreate, db: Banco, tarefas: BackgroundTasks, central: Central) -> Livro:
    livro = Livro(**dados.model_dump())
    db.add(livro)
    db.commit()
    db.refresh(livro)
    logger.info("Livro cadastrado com sucesso. id=%s", livro.id)
    tarefas.add_task(central.publicar, "livro.criado", LivroResponse.model_validate(livro))
    return livro


@router.put("/{livro_id}", response_model=LivroResponse, summary="Atualizar livro")
def atualizar_livro(
    livro_id: LivroId, dados: LivroUpdate, db: Banco, tarefas: BackgroundTasks, central: Central
) -> Livro:
    livro = _buscar_livro(db, livro_id)
    for campo, valor in dados.model_dump().items():
        setattr(livro, campo, valor)
    db.commit()
    db.refresh(livro)
    logger.info("Livro atualizado com sucesso. id=%s", livro.id)
    tarefas.add_task(central.publicar, "livro.atualizado", LivroResponse.model_validate(livro))
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
def criar_exemplar(
    livro_id: LivroId, dados: ExemplarCreate, db: Banco, tarefas: BackgroundTasks, central: Central
) -> Exemplar:
    _buscar_livro(db, livro_id)
    exemplar = Exemplar(livro_id=livro_id, **dados.model_dump())
    db.add(exemplar)
    db.commit()
    db.refresh(exemplar)
    logger.info("Exemplar cadastrado com sucesso. id=%s", exemplar.id)
    tarefas.add_task(
        central.publicar, "exemplar.criado", ExemplarResponse.model_validate(exemplar)
    )
    return exemplar


@router_exemplares.get(
    "/{exemplar_id}", response_model=ExemplarResponse, summary="Consultar disponibilidade do exemplar"
)
def consultar_exemplar(exemplar_id: Annotated[int, Path(gt=0)], db: Banco) -> Exemplar:
    return _buscar_exemplar(db, exemplar_id)


def _buscar_exemplar(db: Session, exemplar_id: int) -> Exemplar:
    exemplar = db.get(Exemplar, exemplar_id)
    if exemplar is None:
        raise HTTPException(status_code=404, detail="Exemplar não encontrado.")
    return exemplar


@router_interno.post(
    "/{exemplar_id}/retirada",
    response_model=ExemplarRetiradaResponse,
    summary="Reservar o exemplar para um empréstimo (atômico)",
)
def retirar_exemplar(exemplar_id: Annotated[int, Path(gt=0)], db: Banco) -> dict:
    """Falha 2 da V0: o UPDATE condicional só altera o exemplar se ele ainda estiver
    DISPONIVEL. Com pedidos simultâneos, o PostgreSQL bloqueia a linha e apenas o
    primeiro altera o status; os demais encontram 0 linhas e recebem 409."""
    exemplar = _buscar_exemplar(db, exemplar_id)
    livro = db.get(Livro, exemplar.livro_id)
    if not livro.ativo:
        raise HTTPException(status_code=409, detail="O livro deste exemplar está inativo.")
    retirada = db.execute(
        update(Exemplar)
        .where(Exemplar.id == exemplar_id, Exemplar.status == StatusExemplar.DISPONIVEL)
        .values(status=StatusExemplar.EMPRESTADO, alterado_em=func.now())
    )
    if retirada.rowcount != 1:
        raise HTTPException(status_code=409, detail="Exemplar não está disponível.")
    db.commit()
    db.refresh(exemplar)
    logger.info("Exemplar retirado para empréstimo. id=%s", exemplar_id)
    return {**ExemplarResponse.model_validate(exemplar).model_dump(), "livro_titulo": livro.titulo}


@router_interno.post(
    "/{exemplar_id}/liberacao",
    response_model=ExemplarResponse,
    summary="Devolver o exemplar ao acervo (devolução ou compensação)",
)
def liberar_exemplar(exemplar_id: Annotated[int, Path(gt=0)], db: Banco) -> Exemplar:
    """Idempotente: liberar um exemplar já disponível não é erro. Assim o Serviço de
    Empréstimos pode repetir o pedido com segurança se a primeira resposta se perder."""
    exemplar = _buscar_exemplar(db, exemplar_id)
    db.execute(
        update(Exemplar)
        .where(Exemplar.id == exemplar_id, Exemplar.status == StatusExemplar.EMPRESTADO)
        .values(status=StatusExemplar.DISPONIVEL, alterado_em=func.now())
    )
    db.commit()
    db.refresh(exemplar)
    logger.info("Exemplar liberado. id=%s", exemplar_id)
    return exemplar


@router_interno.get(
    "/emprestados",
    response_model=list[ExemplarResponse],
    summary="Listar exemplares emprestados (usado pela reconciliação)",
)
def listar_emprestados(
    db: Banco, alterados_ha_segundos: Annotated[int, Query(ge=0, le=86400)] = 0
) -> list[Exemplar]:
    """Só devolve exemplares que estão EMPRESTADO há pelo menos ``alterados_ha_segundos``:
    os mais recentes podem pertencer a um empréstimo que ainda está sendo gravado."""
    limite = datetime.now(timezone.utc) - timedelta(seconds=alterados_ha_segundos)
    consulta = (
        select(Exemplar)
        .where(Exemplar.status == StatusExemplar.EMPRESTADO, Exemplar.alterado_em <= limite)
        .order_by(Exemplar.id)
    )
    return list(db.scalars(consulta).all())
