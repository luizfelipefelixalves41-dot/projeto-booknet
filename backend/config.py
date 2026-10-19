"""Configuração carregada a partir da raiz do projeto."""

import logging
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

# V3: endereços dos serviços consultados pelo Serviço de Empréstimos.
# Na V4 (Docker) passam a ser nomes de contêiner, como http://catalogo:8001.
URL_CATALOGO = os.getenv("BOOKNET_URL_CATALOGO", "http://127.0.0.1:8001").rstrip("/")
URL_USUARIOS = os.getenv("BOOKNET_URL_USUARIOS", "http://127.0.0.1:8002").rstrip("/")

# Tempo máximo de espera por outro serviço (falha 3 da V0: a resposta não chega).
TIMEOUT_SERVICOS = float(os.getenv("BOOKNET_TIMEOUT_SERVICOS", "3"))

# Senha compartilhada entre os serviços para as rotas internas (retirada/liberação
# de exemplar). O valor padrão serve só para desenvolvimento: defina outro no .env.
TOKEN_PADRAO_DESENVOLVIMENTO = "booknet-desenvolvimento"
TOKEN_INTERNO = os.getenv("BOOKNET_TOKEN_INTERNO", TOKEN_PADRAO_DESENVOLVIMENTO)
if TOKEN_INTERNO == TOKEN_PADRAO_DESENVOLVIMENTO:
    logging.getLogger("booknet.config").warning(
        "BOOKNET_TOKEN_INTERNO não definido: usando o token padrão de desenvolvimento."
    )
