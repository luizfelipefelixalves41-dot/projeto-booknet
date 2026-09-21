"""Configuração carregada a partir da raiz do projeto."""

import os
from pathlib import Path

from dotenv import load_dotenv


RAIZ_PROJETO = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=RAIZ_PROJETO / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.strip():
    raise RuntimeError(
        "DATABASE_URL não definida. Configure a variável no .env da raiz do projeto."
    )
