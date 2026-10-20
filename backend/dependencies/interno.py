"""Proteção das rotas internas: apenas outros serviços do BookNet podem chamá-las."""

import hmac
from typing import Annotated

from fastapi import Header, HTTPException

from backend import config

CABECALHO_TOKEN = "X-Servico-Token"


def token_interno_valido(valor: str) -> bool:
    # compare_digest evita que o tempo da comparação revele o token aos poucos.
    return hmac.compare_digest(valor.encode(), config.TOKEN_INTERNO.encode())


def exigir_token_interno(
    x_servico_token: Annotated[str | None, Header(alias=CABECALHO_TOKEN)] = None,
) -> None:
    if x_servico_token is None or not token_interno_valido(x_servico_token):
        raise HTTPException(
            status_code=403, detail="Rota interna: acesso restrito aos serviços do BookNet."
        )
