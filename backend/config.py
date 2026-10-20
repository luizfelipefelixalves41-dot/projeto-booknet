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

# V5: novas tentativas e disjuntor nas chamadas entre serviços.
TENTATIVAS_SERVICOS = int(os.getenv("BOOKNET_TENTATIVAS_SERVICOS", "3"))
ESPERA_BASE_SEGUNDOS = float(os.getenv("BOOKNET_ESPERA_BASE_SEGUNDOS", "0.3"))
DISJUNTOR_LIMITE_FALHAS = int(os.getenv("BOOKNET_DISJUNTOR_LIMITE_FALHAS", "3"))
DISJUNTOR_SEGUNDOS_ABERTO = float(os.getenv("BOOKNET_DISJUNTOR_SEGUNDOS_ABERTO", "30"))

# V5: reconciliação periódica de exemplares presos (0 desliga a execução automática).
RECONCILIACAO_INTERVALO_SEGUNDOS = int(os.getenv("BOOKNET_RECONCILIACAO_INTERVALO_SEGUNDOS", "300"))
# Exemplares alterados há menos tempo que isto podem estar no meio de um empréstimo.
RECONCILIACAO_CARENCIA_SEGUNDOS = int(os.getenv("BOOKNET_RECONCILIACAO_CARENCIA_SEGUNDOS", "120"))

# Login: segredo que assina os tokens de sessão. Precisa ser o mesmo nos três
# serviços, porque cada um confere o token sozinho. Defina outro no .env.
SEGREDO_PADRAO_DESENVOLVIMENTO = "booknet-sessao-desenvolvimento"
SEGREDO_SESSAO = os.getenv("BOOKNET_SEGREDO_SESSAO", SEGREDO_PADRAO_DESENVOLVIMENTO)
if SEGREDO_SESSAO == SEGREDO_PADRAO_DESENVOLVIMENTO:
    logging.getLogger("booknet.config").warning(
        "BOOKNET_SEGREDO_SESSAO não definido: usando o segredo padrão de desenvolvimento."
    )
SESSAO_VALIDADE_HORAS = float(os.getenv("BOOKNET_SESSAO_VALIDADE_HORAS", "8"))

# V6: Redis Pub/Sub para os eventos chegarem a todas as réplicas de um serviço.
# Vazio: cada serviço entrega os próprios eventos (uma instância por serviço).
REDIS_URL = os.getenv("BOOKNET_REDIS_URL", "").strip()
