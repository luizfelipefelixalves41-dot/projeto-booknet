"""API BookNet V2: catálogo, usuários, empréstimos, devoluções e eventos em tempo real."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database import testar_conexao_banco
from backend.errors import configurar_tratamento_erros
from backend.eventos import router as eventos_router
from backend.origens import ORIGENS_LOCAIS, REGEX_REDE_LOCAL
from backend.routers.catalogo import router as catalogo_router
from backend.routers.catalogo import router_exemplares
from backend.routers.emprestimos import router as emprestimos_router
from backend.routers.usuarios import router as usuarios_router


app = FastAPI(
    title="BookNet API",
    version="2.0.0",
    openapi_tags=[
        {"name": "Sistema", "description": "Identificação e verificações de disponibilidade."},
        {"name": "Catálogo", "description": "Livros, exemplares e disponibilidade."},
        {"name": "Usuários", "description": "Alunos e bibliotecários."},
        {"name": "Empréstimos", "description": "Empréstimos e devoluções de exemplares."},
    ],
)

configurar_tratamento_erros(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENS_LOCAIS,
    allow_origin_regex=REGEX_REDE_LOCAL,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/", tags=["Sistema"])
def identificar_projeto() -> dict[str, str]:
    return {"projeto": "BookNet", "status": "online", "versao": "V2"}


@app.get("/health", tags=["Sistema"])
def verificar_saude() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/database", tags=["Sistema"])
def verificar_banco() -> JSONResponse:
    if testar_conexao_banco():
        return JSONResponse(status_code=200, content={"database": "online"})
    return JSONResponse(status_code=503, content={"database": "offline"})


app.include_router(catalogo_router)
app.include_router(router_exemplares)
app.include_router(usuarios_router)
app.include_router(emprestimos_router)
app.include_router(eventos_router)
