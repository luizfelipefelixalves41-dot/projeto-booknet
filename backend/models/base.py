"""Base declarativa compartilhada pelos modelos do catálogo."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Metadados usados pelo ORM e pelo Alembic, sem criar tabelas ao importar."""

