"""Alembic com conexão existente; inspeção offline não lê o arquivo .env."""

from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError

from backend.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emite SQL PostgreSQL sem importar a configuração ou abrir conexão."""
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Reutiliza o engine seguro; só deve ser usado mediante autorização."""
    try:
        from backend.database import engine

        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    except Exception:
        # Não propagar mensagens do driver: podem conter host ou credenciais.
        raise CommandError(
            "Não foi possível executar a operação de migration. "
            "Verifique a configuração, a disponibilidade do banco e a revisão solicitada."
        ) from None


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

