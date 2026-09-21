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


logger = logging.getLogger("booknet.catalogo")


async def tratar_erro_banco(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    if isinstance(exc, IntegrityError):
        # Inspecionar códigos, nunca converter a exceção ou a consulta em texto.
        sqlstate = getattr(exc.orig, "sqlstate", None)
        sqlite_code = getattr(exc.orig, "sqlite_errorcode", None)
        if sqlstate == "23505" or sqlite_code in {
            sqlite3.SQLITE_CONSTRAINT_UNIQUE,
            sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
        }:
            logger.warning("Conflito de unicidade no catálogo.")
            return JSONResponse(
                status_code=409,
                content={"detail": "ISBN ou código de tombo já cadastrado."},
            )
        logger.warning("Dados rejeitados pelas regras de integridade do catálogo.")
        return JSONResponse(
            status_code=400, content={"detail": "Dados incompatíveis com as regras do catálogo."}
        )

    if isinstance(exc, (OperationalError, InterfaceError, DisconnectionError, TimeoutError)):
        logger.warning("Banco de dados indisponível para atender ao catálogo.")
        return JSONResponse(
            status_code=503, content={"detail": "Serviço de banco de dados indisponível."}
        )

    logger.error("Falha inesperada na operação de banco do catálogo.")
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
