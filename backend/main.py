"""API BookNet V1: catálogo, usuários, empréstimos e devoluções."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database import testar_conexao_banco
from backend.errors import configurar_tratamento_erros
from backend.routers.catalogo import router as catalogo_router
from backend.routers.catalogo import router_exemplares
from backend.routers.emprestimos import router as emprestimos_router
from backend.routers.usuarios import router as usuarios_router


app = FastAPI(
    title="BookNet API",
    version="1.2.0",
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
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    # Demonstração em duas máquinas: cliente servido em outro PC da rede local
    # (faixas privadas 10.x, 172.16-31.x e 192.168.x), nas mesmas portas.
    allow_origin_regex=(
        r"^http://(10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}"
        r"|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2}):(8080|5500)$"
    ),
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
app.include_router(router_exemplares)
app.include_router(usuarios_router)
app.include_router(emprestimos_router)
