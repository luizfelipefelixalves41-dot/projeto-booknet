"""Estrutura comum aos três serviços do BookNet (V3).

Cada serviço é um processo independente, com porta, documentação (/docs),
verificações de saúde e canal de eventos próprios. O que muda entre eles é
apenas o conjunto de rotas, ou seja, a responsabilidade de cada um.
"""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import database
from backend.errors import configurar_tratamento_erros
from backend.eventos import CentralDeEventos
from backend.eventos import router as eventos_router
from backend.origens import ORIGENS_PERMITIDAS, REGEX_REDE_LOCAL

VERSAO = "V3"


def criar_servico(
    nome: str, titulo: str, descricao: str, routers: list[APIRouter], tags: list[dict]
) -> FastAPI:
    app = FastAPI(
        title=f"BookNet · {titulo}",
        description=descricao,
        version="3.0.0",
        openapi_tags=[
            {"name": "Sistema", "description": "Identificação e verificações de saúde."},
            *tags,
            {"name": "Eventos", "description": "Canal WebSocket /ws/eventos (V2)."},
        ],
    )
    app.state.central = CentralDeEventos()
    configurar_tratamento_erros(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGENS_PERMITIDAS,
        allow_origin_regex=REGEX_REDE_LOCAL,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/", tags=["Sistema"])
    def identificar_servico() -> dict[str, str]:
        return {"projeto": "BookNet", "servico": nome, "status": "online", "versao": VERSAO}

    @app.get("/health", tags=["Sistema"])
    def verificar_saude() -> dict[str, str]:
        return {"status": "ok", "servico": nome}

    @app.get("/health/database", tags=["Sistema"])
    def verificar_banco() -> JSONResponse:
        if database.testar_conexao_banco():
            return JSONResponse(status_code=200, content={"database": "online"})
        return JSONResponse(status_code=503, content={"database": "offline"})

    for router in routers:
        app.include_router(router)
    app.include_router(eventos_router)
    return app
