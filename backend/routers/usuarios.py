"""Cadastro e consulta de alunos e bibliotecários, sem exclusão de registros.

Também é o serviço de **login**: confere matrícula e senha e entrega o token de
sessão que os três serviços sabem verificar sozinhos.
"""

import logging
import threading
import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend import config
from backend.autenticacao import criar_token, gerar_hash_senha, verificar_senha
from backend.dependencies.database import get_db
from backend.dependencies.sessao import (
    Bibliotecario,
    SessaoAtual,
    exigir_dono_ou_bibliotecario,
)
from backend.eventos import Central
from backend.models.usuario import TipoUsuario, Usuario
from backend.schemas.usuario import (
    LoginRequest,
    LoginResponse,
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)


router = APIRouter(prefix="/usuarios", tags=["Usuários"])
router_auth = APIRouter(prefix="/auth", tags=["Login"])
logger = logging.getLogger("booknet.usuarios")
Banco = Annotated[Session, Depends(get_db, scope="function")]
UsuarioId = Annotated[int, Path(gt=0)]

# Freio contra quem tenta adivinhar senhas: 5 erros em 5 minutos bloqueiam a matrícula.
MAX_TENTATIVAS_LOGIN = 5
JANELA_TENTATIVAS_SEGUNDOS = 300
_tentativas_falhas: dict[str, list[float]] = {}
_trava_tentativas = threading.Lock()
# Hash de uma senha qualquer: usado quando a matrícula não existe, para o tempo de
# resposta não revelar se a matrícula está cadastrada.
_HASH_FICTICIO = gerar_hash_senha("senha-ficticia-para-tempo-constante")


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


def _bloqueado(matricula: str) -> bool:
    agora = time.monotonic()
    with _trava_tentativas:
        recentes = [t for t in _tentativas_falhas.get(matricula, []) if agora - t < JANELA_TENTATIVAS_SEGUNDOS]
        _tentativas_falhas[matricula] = recentes
        return len(recentes) >= MAX_TENTATIVAS_LOGIN


def _registrar_falha(matricula: str) -> None:
    with _trava_tentativas:
        _tentativas_falhas.setdefault(matricula, []).append(time.monotonic())


@router_auth.post("/login", response_model=LoginResponse, summary="Entrar com matrícula e senha")
def entrar(dados: LoginRequest, db: Banco) -> dict:
    if _bloqueado(dados.matricula):
        raise HTTPException(
            status_code=429, detail="Muitas tentativas sem sucesso. Aguarde alguns minutos."
        )
    usuario = db.scalar(select(Usuario).where(Usuario.matricula == dados.matricula))
    senha_confere = verificar_senha(
        dados.senha, usuario.senha_hash if usuario and usuario.senha_hash else _HASH_FICTICIO
    )
    if usuario is None or not usuario.senha_hash or not senha_confere:
        _registrar_falha(dados.matricula)
        logger.info("Tentativa de login recusada.")
        raise HTTPException(status_code=401, detail="Matrícula ou senha incorretos.")
    if not usuario.ativo:
        raise HTTPException(status_code=403, detail="Conta desativada. Procure a biblioteca.")
    if dados.perfil is not None and dados.perfil != usuario.tipo:
        aba = "Aluno" if usuario.tipo == TipoUsuario.ALUNO else "Bibliotecário"
        raise HTTPException(status_code=403, detail=f"Esta conta não é deste perfil. Use a aba {aba}.")
    validade = int(config.SESSAO_VALIDADE_HORAS * 3600)
    logger.info("Login realizado. id=%s", usuario.id)
    return {
        "token": criar_token(usuario.id, usuario.nome, usuario.tipo.value, validade),
        "expira_em_segundos": validade,
        "usuario": usuario,
    }


@router_auth.get("/eu", response_model=UsuarioResponse, summary="Dados de quem está logado")
def quem_sou_eu(sessao: SessaoAtual, db: Banco) -> Usuario:
    return buscar_usuario(db, sessao.usuario_id)


@router.get("", response_model=list[UsuarioResponse], summary="Listar usuários ativos")
def listar_usuarios(
    db: Banco,
    _: Bibliotecario,
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
def consultar_usuario(usuario_id: UsuarioId, db: Banco, sessao: SessaoAtual) -> Usuario:
    exigir_dono_ou_bibliotecario(sessao, usuario_id)
    return buscar_usuario(db, usuario_id)


@router.post(
    "", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED, summary="Cadastrar usuário"
)
def criar_usuario(
    dados: UsuarioCreate, db: Banco, tarefas: BackgroundTasks, central: Central, _: Bibliotecario
) -> Usuario:
    _verificar_unicidade(db, dados)
    usuario = Usuario(**dados.model_dump(exclude={"senha"}))
    if dados.senha:
        usuario.senha_hash = gerar_hash_senha(dados.senha)
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    logger.info("Usuário cadastrado com sucesso. id=%s", usuario.id)
    tarefas.add_task(
        central.publicar, "usuario.criado", UsuarioResponse.model_validate(usuario),
        somente_bibliotecarios=True,
    )
    return usuario


@router.put("/{usuario_id}", response_model=UsuarioResponse, summary="Atualizar usuário")
def atualizar_usuario(
    usuario_id: UsuarioId,
    dados: UsuarioUpdate,
    db: Banco,
    tarefas: BackgroundTasks,
    central: Central,
    _: Bibliotecario,
) -> Usuario:
    usuario = buscar_usuario(db, usuario_id)
    _verificar_unicidade(db, dados, ignorar_id=usuario_id)
    for campo, valor in dados.model_dump(exclude={"senha"}).items():
        setattr(usuario, campo, valor)
    if dados.senha:
        usuario.senha_hash = gerar_hash_senha(dados.senha)
    db.commit()
    db.refresh(usuario)
    logger.info("Usuário atualizado com sucesso. id=%s", usuario.id)
    tarefas.add_task(
        central.publicar, "usuario.atualizado", UsuarioResponse.model_validate(usuario),
        somente_bibliotecarios=True,
    )
    return usuario
