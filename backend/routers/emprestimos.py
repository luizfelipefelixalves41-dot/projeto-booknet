"""Empréstimos e devoluções com mudanças de estado atômicas.

Concorrência (falha 2 da V0): a retirada usa um UPDATE condicional
``status = 'DISPONIVEL'``. Se duas requisições disputarem o mesmo exemplar, o
PostgreSQL bloqueia a linha e apenas a primeira altera o status; a segunda
recebe 0 linhas afetadas e responde 409. O índice único parcial
``uq_emprestimos_exemplar_ativo`` é a garantia final no banco.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, status
from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from backend.dependencies.database import get_db
from backend.eventos import central
from backend.models.emprestimo import Emprestimo, StatusEmprestimo
from backend.models.exemplar import Exemplar, StatusExemplar
from backend.models.livro import Livro
from backend.models.usuario import Usuario
from backend.schemas.emprestimo import EmprestimoCreate, EmprestimoResponse


router = APIRouter(prefix="/emprestimos", tags=["Empréstimos"])
logger = logging.getLogger("booknet.emprestimos")
Banco = Annotated[Session, Depends(get_db, scope="function")]
EmprestimoId = Annotated[int, Path(gt=0)]

LIMITE_EMPRESTIMOS_ATIVOS = 3


def _consulta_detalhada() -> Select:
    return (
        select(Emprestimo, Usuario.nome, Exemplar.codigo_tombo, Livro.id, Livro.titulo)
        .join(Usuario, Usuario.id == Emprestimo.usuario_id)
        .join(Exemplar, Exemplar.id == Emprestimo.exemplar_id)
        .join(Livro, Livro.id == Exemplar.livro_id)
        .execution_options(populate_existing=True)
    )


def _montar_resposta(linha) -> dict[str, Any]:
    emprestimo, usuario_nome, codigo_tombo, livro_id, livro_titulo = linha
    return {
        "id": emprestimo.id,
        "usuario_id": emprestimo.usuario_id,
        "exemplar_id": emprestimo.exemplar_id,
        "data_emprestimo": emprestimo.data_emprestimo,
        "data_prevista_devolucao": emprestimo.data_prevista_devolucao,
        "data_devolucao": emprestimo.data_devolucao,
        "status": emprestimo.status,
        "atrasado": emprestimo.status == StatusEmprestimo.ATIVO
        and emprestimo.data_prevista_devolucao < date.today(),
        "usuario_nome": usuario_nome,
        "codigo_tombo": codigo_tombo,
        "livro_id": livro_id,
        "livro_titulo": livro_titulo,
    }


def _detalhar(db: Session, emprestimo_id: int) -> dict[str, Any]:
    linha = db.execute(_consulta_detalhada().where(Emprestimo.id == emprestimo_id)).one_or_none()
    if linha is None:
        raise HTTPException(status_code=404, detail="Empréstimo não encontrado.")
    return _montar_resposta(linha)


@router.get("", response_model=list[EmprestimoResponse], summary="Listar empréstimos")
def listar_emprestimos(
    db: Banco,
    usuario_id: Annotated[int | None, Query(gt=0)] = None,
    status_emprestimo: Annotated[StatusEmprestimo | None, Query(alias="status")] = None,
    atrasados: bool = False,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    consulta = _consulta_detalhada()
    if usuario_id is not None:
        consulta = consulta.where(Emprestimo.usuario_id == usuario_id)
    if status_emprestimo is not None:
        consulta = consulta.where(Emprestimo.status == status_emprestimo)
    if atrasados:
        consulta = consulta.where(
            Emprestimo.status == StatusEmprestimo.ATIVO,
            Emprestimo.data_prevista_devolucao < date.today(),
        )
    consulta = consulta.order_by(Emprestimo.id.desc()).offset(skip).limit(limit)
    return [_montar_resposta(linha) for linha in db.execute(consulta).all()]


@router.get("/{emprestimo_id}", response_model=EmprestimoResponse, summary="Consultar empréstimo")
def consultar_emprestimo(emprestimo_id: EmprestimoId, db: Banco) -> dict[str, Any]:
    return _detalhar(db, emprestimo_id)


@router.post(
    "",
    response_model=EmprestimoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar empréstimo",
)
def criar_emprestimo(
    dados: EmprestimoCreate, db: Banco, tarefas: BackgroundTasks
) -> dict[str, Any]:
    # FOR UPDATE serializa pedidos simultâneos do mesmo usuário (limite de ativos).
    usuario = db.get(Usuario, dados.usuario_id, with_for_update=True)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if not usuario.ativo:
        raise HTTPException(status_code=409, detail="Usuário inativo não pode realizar empréstimos.")

    filtro_ativos = (
        Emprestimo.usuario_id == usuario.id,
        Emprestimo.status == StatusEmprestimo.ATIVO,
    )
    if db.scalar(select(func.count()).where(*filtro_ativos)) >= LIMITE_EMPRESTIMOS_ATIVOS:
        raise HTTPException(
            status_code=409,
            detail=f"Usuário já possui {LIMITE_EMPRESTIMOS_ATIVOS} empréstimos ativos.",
        )
    atrasado = select(Emprestimo.id).where(
        *filtro_ativos, Emprestimo.data_prevista_devolucao < date.today()
    )
    if db.scalar(atrasado.limit(1)) is not None:
        raise HTTPException(status_code=409, detail="Usuário possui empréstimo em atraso.")

    exemplar = db.get(Exemplar, dados.exemplar_id)
    if exemplar is None:
        raise HTTPException(status_code=404, detail="Exemplar não encontrado.")
    if not db.scalar(select(Livro.ativo).where(Livro.id == exemplar.livro_id)):
        raise HTTPException(status_code=409, detail="O livro deste exemplar está inativo.")

    retirada = db.execute(
        update(Exemplar)
        .where(Exemplar.id == exemplar.id, Exemplar.status == StatusExemplar.DISPONIVEL)
        .values(status=StatusExemplar.EMPRESTADO)
    )
    if retirada.rowcount != 1:
        raise HTTPException(status_code=409, detail="Exemplar não está disponível.")

    agora = datetime.now(timezone.utc)
    emprestimo = Emprestimo(
        usuario_id=usuario.id,
        exemplar_id=exemplar.id,
        data_emprestimo=agora,
        data_prevista_devolucao=date.today() + timedelta(days=dados.prazo_dias),
        status=StatusEmprestimo.ATIVO,
    )
    db.add(emprestimo)
    db.commit()
    logger.info("Empréstimo registrado com sucesso. id=%s", emprestimo.id)
    resposta = _detalhar(db, emprestimo.id)
    tarefas.add_task(central.publicar, "emprestimo.criado", resposta)
    return resposta


@router.post(
    "/{emprestimo_id}/devolucao",
    response_model=EmprestimoResponse,
    summary="Registrar devolução",
)
def devolver_emprestimo(
    emprestimo_id: EmprestimoId, db: Banco, tarefas: BackgroundTasks
) -> dict[str, Any]:
    emprestimo = db.get(Emprestimo, emprestimo_id)
    if emprestimo is None:
        raise HTTPException(status_code=404, detail="Empréstimo não encontrado.")

    devolucao = db.execute(
        update(Emprestimo)
        .where(Emprestimo.id == emprestimo_id, Emprestimo.status == StatusEmprestimo.ATIVO)
        .values(status=StatusEmprestimo.DEVOLVIDO, data_devolucao=datetime.now(timezone.utc))
    )
    if devolucao.rowcount != 1:
        raise HTTPException(status_code=409, detail="Empréstimo já devolvido.")
    db.execute(
        update(Exemplar)
        .where(Exemplar.id == emprestimo.exemplar_id)
        .values(status=StatusExemplar.DISPONIVEL)
    )
    db.commit()
    logger.info("Devolução registrada com sucesso. id=%s", emprestimo_id)
    resposta = _detalhar(db, emprestimo_id)
    tarefas.add_task(central.publicar, "emprestimo.devolvido", resposta)
    return resposta
