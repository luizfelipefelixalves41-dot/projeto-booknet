"""Serviço de Empréstimos (V3): coordena Usuários e Catálogo por HTTP.

Fluxo de um empréstimo (saga com compensação):

1. pergunta ao Serviço de Usuários se o usuário existe e está ativo;
2. confere as regras locais (limite de ativos e atraso), com o usuário travado;
3. pede ao Serviço de Catálogo a retirada atômica do exemplar (falha 2 da V0);
4. grava o empréstimo no próprio banco.

Se o passo 4 falhar depois de o Catálogo já ter retirado o exemplar, o serviço
executa a **compensação**: pede a liberação do exemplar, desfazendo o passo 3.
O índice único parcial ``uq_emprestimos_exemplar_ativo`` continua sendo a última
garantia de um empréstimo ativo por exemplar.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.dependencies.database import get_db
from backend.dependencies.sessao import (
    Bibliotecario,
    SessaoAtual,
    exigir_dono_ou_bibliotecario,
)
from backend import reconciliacao
from backend.eventos import Central
from backend.models.emprestimo import Emprestimo, StatusEmprestimo
from backend.schemas.emprestimo import EmprestimoCreate, EmprestimoResponse
from backend.servicos_remotos import ServicosRemotos, obter_servicos_remotos


router = APIRouter(prefix="/emprestimos", tags=["Empréstimos"])
router_sistema = APIRouter(tags=["Sistema"])
logger = logging.getLogger("booknet.emprestimos")
Banco = Annotated[Session, Depends(get_db, scope="function")]
Servicos = Annotated[ServicosRemotos, Depends(obter_servicos_remotos)]
EmprestimoId = Annotated[int, Path(gt=0)]

LIMITE_EMPRESTIMOS_ATIVOS = 3


def _montar_resposta(emprestimo: Emprestimo) -> dict[str, Any]:
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
        "usuario_nome": emprestimo.usuario_nome,
        "codigo_tombo": emprestimo.codigo_tombo,
        "livro_id": emprestimo.livro_id,
        "livro_titulo": emprestimo.livro_titulo,
    }


def _buscar(db: Session, emprestimo_id: int) -> Emprestimo:
    emprestimo = db.get(Emprestimo, emprestimo_id, populate_existing=True)
    if emprestimo is None:
        raise HTTPException(status_code=404, detail="Empréstimo não encontrado.")
    return emprestimo


def _travar_usuario(db: Session, usuario_id: int) -> None:
    """Serializa pedidos simultâneos do mesmo usuário até o fim da transação.

    Na V1 isso era um SELECT ... FOR UPDATE na tabela de usuários; agora essa tabela
    pertence a outro serviço, então usamos uma trava consultiva do PostgreSQL,
    identificada pelo número do usuário. O SQLite dos testes não tem esse recurso.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(usuario_id)))


def _compensar_retirada(servicos: ServicosRemotos, exemplar_id: int) -> None:
    try:
        servicos.liberar_exemplar(exemplar_id)
        logger.warning("Compensação executada: exemplar %s liberado.", exemplar_id)
    except Exception:
        # Sem a compensação, o exemplar fica EMPRESTADO sem empréstimo: a V5 trata
        # isso com novas tentativas. Aqui o problema fica registrado no log.
        logger.error("Compensação falhou: exemplar %s pode ter ficado indisponível.", exemplar_id)


@router.get("", response_model=list[EmprestimoResponse], summary="Listar empréstimos")
def listar_emprestimos(
    db: Banco,
    sessao: SessaoAtual,
    usuario_id: Annotated[int | None, Query(gt=0)] = None,
    status_emprestimo: Annotated[StatusEmprestimo | None, Query(alias="status")] = None,
    atrasados: bool = False,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    if not sessao.bibliotecario:
        usuario_id = sessao.usuario_id  # aluno vê só os próprios empréstimos
    consulta = select(Emprestimo)
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
    return [_montar_resposta(item) for item in db.scalars(consulta).all()]


@router.get("/{emprestimo_id}", response_model=EmprestimoResponse, summary="Consultar empréstimo")
def consultar_emprestimo(emprestimo_id: EmprestimoId, db: Banco, sessao: SessaoAtual) -> dict[str, Any]:
    emprestimo = _buscar(db, emprestimo_id)
    exigir_dono_ou_bibliotecario(sessao, emprestimo.usuario_id)
    return _montar_resposta(emprestimo)


@router.post(
    "",
    response_model=EmprestimoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar empréstimo",
)
def criar_emprestimo(
    dados: EmprestimoCreate,
    db: Banco,
    servicos: Servicos,
    tarefas: BackgroundTasks,
    central: Central,
    sessao: SessaoAtual,
) -> dict[str, Any]:
    if not sessao.bibliotecario and dados.usuario_id != sessao.usuario_id:
        raise HTTPException(status_code=403, detail="Alunos só podem pegar livros para si mesmos.")

    # 1. Serviço de Usuários: o usuário existe e está ativo?
    usuario = servicos.buscar_usuario(dados.usuario_id)
    if not usuario["ativo"]:
        raise HTTPException(status_code=409, detail="Usuário inativo não pode realizar empréstimos.")

    # 2. Regras locais, com o usuário travado contra pedidos simultâneos.
    _travar_usuario(db, dados.usuario_id)
    filtro_ativos = (
        Emprestimo.usuario_id == dados.usuario_id,
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

    # 3. Serviço de Catálogo: retirada atômica (só um pedido concorrente vence).
    exemplar = servicos.retirar_exemplar(dados.exemplar_id)

    # 4. Registro local; se falhar, compensa a retirada feita no passo 3.
    emprestimo = Emprestimo(
        usuario_id=dados.usuario_id,
        exemplar_id=dados.exemplar_id,
        data_emprestimo=datetime.now(timezone.utc),
        data_prevista_devolucao=date.today() + timedelta(days=dados.prazo_dias),
        status=StatusEmprestimo.ATIVO,
        usuario_nome=usuario["nome"],
        codigo_tombo=exemplar["codigo_tombo"],
        livro_id=exemplar["livro_id"],
        livro_titulo=exemplar["livro_titulo"],
    )
    try:
        db.add(emprestimo)
        db.commit()
    except Exception:
        db.rollback()
        _compensar_retirada(servicos, dados.exemplar_id)
        raise
    logger.info("Empréstimo registrado com sucesso. id=%s", emprestimo.id)
    resposta = _montar_resposta(emprestimo)
    tarefas.add_task(
        central.publicar, "emprestimo.criado", EmprestimoResponse.model_validate(resposta),
        dono_id=emprestimo.usuario_id,
    )
    return resposta


@router.post(
    "/{emprestimo_id}/devolucao",
    response_model=EmprestimoResponse,
    summary="Registrar devolução",
)
def devolver_emprestimo(
    emprestimo_id: EmprestimoId,
    db: Banco,
    servicos: Servicos,
    tarefas: BackgroundTasks,
    central: Central,
    sessao: SessaoAtual,
) -> dict[str, Any]:
    emprestimo = _buscar(db, emprestimo_id)
    exigir_dono_ou_bibliotecario(sessao, emprestimo.usuario_id)
    devolucao = db.execute(
        update(Emprestimo)
        .where(Emprestimo.id == emprestimo_id, Emprestimo.status == StatusEmprestimo.ATIVO)
        .values(status=StatusEmprestimo.DEVOLVIDO, data_devolucao=datetime.now(timezone.utc))
    )
    if devolucao.rowcount != 1:
        raise HTTPException(status_code=409, detail="Empréstimo já devolvido.")
    # Só confirma a devolução se o Catálogo liberar o exemplar. Se ele estiver fora
    # do ar, a transação é desfeita (503/504) e a devolução pode ser repetida depois.
    servicos.liberar_exemplar(emprestimo.exemplar_id)
    db.commit()
    logger.info("Devolução registrada com sucesso. id=%s", emprestimo_id)
    resposta = _montar_resposta(_buscar(db, emprestimo_id))
    tarefas.add_task(
        central.publicar, "emprestimo.devolvido", EmprestimoResponse.model_validate(resposta),
        dono_id=emprestimo.usuario_id,
    )
    return resposta


@router.post("/reconciliacao", summary="Verificar e liberar exemplares presos (V5)")
def executar_reconciliacao(db: Banco, servicos: Servicos, _: Bibliotecario) -> dict[str, Any]:
    return reconciliacao.reconciliar(db, servicos)


@router_sistema.get("/health/dependencias", summary="Estado dos disjuntores e da reconciliação (V5)")
def estado_dependencias(servicos: Servicos) -> dict[str, Any]:
    return {
        "disjuntores": servicos.resumo_disjuntores(),
        "ultima_reconciliacao": reconciliacao.ultima_execucao,
    }
