"""V3: chamadas HTTP do Serviço de Empréstimos aos serviços de Usuários e Catálogo.

Cada chamada tem tempo limite (``BOOKNET_TIMEOUT_SERVICOS``). Falhas de rede
viram respostas claras para o cliente, em vez de travar a requisição:

- serviço desligado ou recusando conexão  → 503 Service Unavailable;
- serviço não respondeu dentro do prazo    → 504 Gateway Timeout (falha 3 da V0).
"""

import logging

import httpx
from fastapi import HTTPException

from backend import config
from backend.dependencies.interno import CABECALHO_TOKEN


logger = logging.getLogger("booknet.servicos_remotos")


class ServicosRemotos:
    def __init__(self, cliente: httpx.Client) -> None:
        self.cliente = cliente

    def _chamar(self, servico: str, metodo: str, url: str, **opcoes) -> httpx.Response:
        try:
            resposta = self.cliente.request(metodo, url, **opcoes)
        except httpx.TimeoutException:
            logger.warning("Serviço de %s não respondeu dentro do prazo.", servico)
            raise HTTPException(
                status_code=504, detail=f"O Serviço de {servico} não respondeu a tempo."
            ) from None
        except httpx.TransportError:
            logger.warning("Serviço de %s inacessível.", servico)
            raise HTTPException(
                status_code=503, detail=f"Serviço de {servico} indisponível no momento."
            ) from None
        if resposta.status_code >= 500:
            logger.warning("Serviço de %s respondeu com erro %s.", servico, resposta.status_code)
            raise HTTPException(
                status_code=503, detail=f"Serviço de {servico} com falha no momento."
            )
        return resposta

    @staticmethod
    def _repassar_erro(resposta: httpx.Response, servico: str) -> None:
        """404 e 409 são respostas de negócio do outro serviço: chegam ao cliente como estão."""
        if resposta.status_code in (404, 409):
            raise HTTPException(status_code=resposta.status_code, detail=resposta.json()["detail"])
        if resposta.status_code != 200:
            logger.error("Resposta inesperada do Serviço de %s: %s.", servico, resposta.status_code)
            raise HTTPException(
                status_code=502, detail=f"Resposta inesperada do Serviço de {servico}."
            )

    def buscar_usuario(self, usuario_id: int) -> dict:
        resposta = self._chamar("Usuários", "GET", f"{config.URL_USUARIOS}/usuarios/{usuario_id}")
        self._repassar_erro(resposta, "Usuários")
        return resposta.json()

    def retirar_exemplar(self, exemplar_id: int) -> dict:
        resposta = self._chamar(
            "Catálogo",
            "POST",
            f"{config.URL_CATALOGO}/interno/exemplares/{exemplar_id}/retirada",
            headers={CABECALHO_TOKEN: config.TOKEN_INTERNO},
        )
        self._repassar_erro(resposta, "Catálogo")
        return resposta.json()

    def liberar_exemplar(self, exemplar_id: int) -> dict:
        resposta = self._chamar(
            "Catálogo",
            "POST",
            f"{config.URL_CATALOGO}/interno/exemplares/{exemplar_id}/liberacao",
            headers={CABECALHO_TOKEN: config.TOKEN_INTERNO},
        )
        self._repassar_erro(resposta, "Catálogo")
        return resposta.json()


_servicos: ServicosRemotos | None = None


def obter_servicos_remotos() -> ServicosRemotos:
    """Um único cliente HTTP por processo: reaproveita conexões entre requisições."""
    global _servicos
    if _servicos is None:
        _servicos = ServicosRemotos(httpx.Client(timeout=config.TIMEOUT_SERVICOS))
    return _servicos
