"""API BookNet V1.1: catálogo preparado e verificações de disponibilidade."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database import testar_conexao_banco
from backend.errors import configurar_tratamento_erros
from backend.routers.catalogo import router as catalogo_router


app = FastAPI(
    title="BookNet API",
    version="1.1.0",
    openapi_tags=[
        {"name": "Sistema", "description": "Identificação e verificações de disponibilidade."},
        {"name": "Catálogo", "description": "Livros e exemplares; migration pendente no Neon."},
    ],
)

configurar_tratamento_erros(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/", tags=["Sistema"])
def identificar_projeto() -> dict[str, str]:
    return {"projeto": "BookNet", "status": "online", "versao": "V1"}


@app.get("/health", tags=["Sistema"])
def verificar_saude() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database", tags=["Sistema"])
def verificar_banco() -> JSONResponse:
    if testar_conexao_banco():
        return JSONResponse(status_code=200, content={"database": "online"})
    return JSONResponse(status_code=503, content={"database": "offline"})


app.include_router(catalogo_router)
