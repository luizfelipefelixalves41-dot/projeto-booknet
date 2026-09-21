"""Uma sessão de banco por requisição, sempre encerrada ao final."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from backend import database


def get_db() -> Generator[Session, None, None]:
    sessao = database.SessionLocal()
    try:
        yield sessao
    except Exception:
        sessao.rollback()
        raise
    finally:
        sessao.close()
