"""Cadastro e consulta de alunos e bibliotecários, sem exclusão de registros."""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.dependencies.database import get_db
from backend.eventos import Central
from backend.models.usuario import TipoUsuario, Usuario
from backend.schemas.usuario import UsuarioCreate, UsuarioResponse, UsuarioUpdate


router = APIRouter(prefix="/usuarios", tags=["Usuários"])
logger = logging.getLogger("booknet.usuarios")
Banco = Annotated[Session, Depends(get_db, scope="function")]
UsuarioId = Annotated[int, Path(gt=0)]


def buscar_usuario(db: Session, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return usuario


def _verificar_unicidade(db: Session, dados: UsuarioCreate, ignorar_id: int | None = None) -> None:
    """Mensagens específicas para duplicidades; a constraint do banco continua sendo a garantia."""
    for campo, mensagem in (("email", "E-mail já cadastrado."), ("matricula", "Matrícula já cadastrada.")):
        consulta = select(Usuario.id).where(getattr(Usuario, campo) == getattr(dados, campo))
        if ignorar_id is not None:
            consulta = consulta.where(Usuario.id != ignorar_id)
        if db.scalar(consulta) is not None:
            raise HTTPException(status_code=409, detail=mensagem)


@router.get("", response_model=list[UsuarioResponse], summary="Listar usuários ativos")
def listar_usuarios(
    db: Banco,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=255)] = None,
    tipo: TipoUsuario | None = None,
) -> list[Usuario]:
    consulta = select(Usuario).where(Usuario.ativo.is_(True))
    if tipo is not None:
        consulta = consulta.where(Usuario.tipo == tipo)
    if q and (busca := q.strip()):
        consulta = consulta.where(
            or_(
                Usuario.nome.icontains(busca, autoescape=True),
                Usuario.email.icontains(busca, autoescape=True),
                Usuario.matricula.icontains(busca, autoescape=True),
            )
        )
    consulta = consulta.order_by(Usuario.id).offset(skip).limit(limit)
    return list(db.scalars(consulta).all())


@router.get("/{usuario_id}", response_model=UsuarioResponse, summary="Consultar usuário")
def consultar_usuario(usuario_id: UsuarioId, db: Banco) -> Usuario:
    return buscar_usuario(db, usuario_id)


@router.post(
    "", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED, summary="Cadastrar usuário"
)
def criar_usuario(dados: UsuarioCreate, db: Banco, tarefas: BackgroundTasks, central: Central) -> Usuario:
    _verificar_unicidade(db, dados)
    usuario = Usuario(**dados.model_dump())
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    logger.info("Usuário cadastrado com sucesso. id=%s", usuario.id)
    tarefas.add_task(central.publicar, "usuario.criado", UsuarioResponse.model_validate(usuario))
    return usuario


@router.put("/{usuario_id}", response_model=UsuarioResponse, summary="Atualizar usuário")
def atualizar_usuario(
    usuario_id: UsuarioId, dados: UsuarioUpdate, db: Banco, tarefas: BackgroundTasks, central: Central
) -> Usuario:
    usuario = buscar_usuario(db, usuario_id)
    _verificar_unicidade(db, dados, ignorar_id=usuario_id)
    for campo, valor in dados.model_dump().items():
        setattr(usuario, campo, valor)
    db.commit()
    db.refresh(usuario)
    logger.info("Usuário atualizado com sucesso. id=%s", usuario.id)
    tarefas.add_task(
        central.publicar, "usuario.atualizado", UsuarioResponse.model_validate(usuario)
    )
    return usuario
