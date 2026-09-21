"""Conexão PostgreSQL e fábrica de sessões; sem criação automática de tabelas."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.config import DATABASE_URL


try:
    _url = make_url(DATABASE_URL)
    if _url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("O banco deve usar PostgreSQL.")
    _url = _url.set(drivername="postgresql+psycopg")
    engine = create_engine(
        _url,
        pool_pre_ping=True,
        hide_parameters=True,
        echo=False,
        connect_args={"connect_timeout": 10},
    )
except Exception:
    raise RuntimeError(
        "Não foi possível configurar o PostgreSQL. "
        "Verifique DATABASE_URL e as dependências do projeto."
    ) from None


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def testar_conexao_banco() -> bool:
    """Executa SELECT 1 e retorna o estado da conexão sem expor dados internos."""
    try:
        with engine.connect() as conexao:
            return conexao.execute(text("SELECT 1")).scalar_one() == 1
    except Exception:
        return False
