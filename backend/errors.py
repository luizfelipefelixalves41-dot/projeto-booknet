"""Respostas e logs sem SQL, parâmetros ou detalhes internos de exceções."""

import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import (
    DisconnectionError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
    TimeoutError,
)


logger = logging.getLogger("booknet.banco")

# Nomes de constraints conhecidos; o PostgreSQL informa o nome sem expor a consulta.
_MENSAGENS_UNICIDADE = {
    "uq_livros_isbn": "ISBN já cadastrado.",
    "uq_exemplares_codigo_tombo": "Código de tombo já cadastrado.",
    "uq_usuarios_email": "E-mail já cadastrado.",
    "uq_usuarios_matricula": "Matrícula já cadastrada.",
    "uq_emprestimos_exemplar_ativo": "Exemplar não está disponível.",
}


async def tratar_erro_banco(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    if isinstance(exc, IntegrityError):
        # Inspecionar códigos, nunca converter a exceção ou a consulta em texto.
        sqlstate = getattr(exc.orig, "sqlstate", None)
        sqlite_code = getattr(exc.orig, "sqlite_errorcode", None)
        if sqlstate == "23505" or sqlite_code in {
            sqlite3.SQLITE_CONSTRAINT_UNIQUE,
            sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
        }:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            logger.warning("Conflito de unicidade no banco.")
            return JSONResponse(
                status_code=409,
                content={
                    "detail": _MENSAGENS_UNICIDADE.get(
                        constraint, "Já existe um registro com esses dados."
                    )
                },
            )
        logger.warning("Dados rejeitados pelas regras de integridade do banco.")
        return JSONResponse(
            status_code=400, content={"detail": "Dados incompatíveis com as regras do sistema."}
        )

    if isinstance(exc, (OperationalError, InterfaceError, DisconnectionError, TimeoutError)):
        logger.warning("Banco de dados indisponível.")
        return JSONResponse(
            status_code=503, content={"detail": "Serviço de banco de dados indisponível."}
        )

    logger.error("Falha inesperada na operação de banco.")
    return JSONResponse(
        status_code=500, content={"detail": "Não foi possível concluir a operação."}
    )


async def tratar_erro_inesperado(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        # Evita que exceções não previstas sejam repassadas ao log de traceback
        # do servidor com dados internos de bibliotecas ou da configuração.
        logger.error("Falha inesperada ao atender uma requisição da API.")
        return JSONResponse(
            status_code=500, content={"detail": "Não foi possível concluir a operação."}
        )


def configurar_tratamento_erros(app: FastAPI) -> None:
    app.add_exception_handler(SQLAlchemyError, tratar_erro_banco)
    app.middleware("http")(tratar_erro_inesperado)
