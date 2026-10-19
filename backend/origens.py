"""Origens do navegador autorizadas a usar a API (CORS no HTTP e verificação no WebSocket)."""

import os
import re

ORIGENS_LOCAIS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]

# Na nuvem: endereço público do Cliente Web, ex.: https://booknet-luizfelipe.onrender.com.
# Vários endereços podem ser separados por vírgula.
ORIGENS_EXTRAS = [
    origem.strip().rstrip("/")
    for origem in os.getenv("BOOKNET_ORIGENS_EXTRAS", "").split(",")
    if origem.strip()
]
ORIGENS_PERMITIDAS = ORIGENS_LOCAIS + ORIGENS_EXTRAS

# Demonstração em duas máquinas: cliente servido em outro PC da rede local
# (faixas privadas 10.x, 172.16-31.x e 192.168.x), nas mesmas portas.
REGEX_REDE_LOCAL = (
    r"^http://(10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}"
    r"|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2}):(8080|5500)$"
)


def origem_permitida(origem: str | None) -> bool:
    """O CORS não protege WebSockets; o servidor precisa conferir a origem por conta própria.

    Sem cabeçalho Origin, a conexão não vem de uma página web (ex.: script de terminal)
    e é aceita, assim como clientes HTTP fora do navegador não são limitados pelo CORS.
    """
    if origem is None:
        return True
    return origem in ORIGENS_PERMITIDAS or re.fullmatch(REGEX_REDE_LOCAL, origem) is not None
