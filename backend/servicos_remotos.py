"""Chamadas HTTP do Serviço de Empréstimos aos serviços de Usuários e Catálogo.

V3: cada chamada tem tempo limite (``BOOKNET_TIMEOUT_SERVICOS``) e falhas de rede
viram respostas claras, em vez de travar a requisição:

- serviço desligado ou recusando conexão  → 503 Service Unavailable;
- serviço não respondeu dentro do prazo    → 504 Gateway Timeout (falha 3 da V0).

V5: recuperação automática de falhas passageiras.

- **Novas tentativas** com espera crescente (0,3 s, 0,6 s, 1,2 s… mais um pouco de
  aleatoriedade, para vários clientes não tentarem de novo no mesmo instante).
  Só são repetidas chamadas em que repetir é seguro:
    * falha de conexão: o pedido nem chegou ao outro serviço;
    * erro 5xx em operação idempotente (consultar usuário, liberar exemplar).
  A retirada de exemplar não é repetida após um erro 5xx ou um tempo esgotado,
  porque ela pode ter sido feita; nesses casos quem resolve é a reconciliação.
- **Disjuntor** por serviço (veja ``backend/resiliencia.py``): depois de várias
  falhas seguidas, as chamadas falham na hora por alguns segundos.
"""

import logging
import random
import time
from typing import Callable

import httpx
from fastapi import HTTPException

from backend import config
from backend.dependencies.interno import CABECALHO_TOKEN
from backend.resiliencia import Disjuntor


logger = logging.getLogger("booknet.servicos_remotos")


class ServicosRemotos:
    def __init__(
        self,
        cliente: httpx.Client,
        disjuntores: dict[str, Disjuntor] | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cliente = cliente
        self.disjuntores = disjuntores or {
            nome: Disjuntor(
                nome,
                limite_falhas=config.DISJUNTOR_LIMITE_FALHAS,
                segundos_aberto=config.DISJUNTOR_SEGUNDOS_ABERTO,
            )
            for nome in ("Usuários", "Catálogo")
        }
        self._dormir = dormir

    def _esperar_antes_de_tentar(self, tentativa: int) -> None:
        espera = config.ESPERA_BASE_SEGUNDOS * 2 ** (tentativa - 1)
        self._dormir(espera + random.uniform(0, espera / 2))

    def _chamar(
        self, servico: str, metodo: str, url: str, idempotente: bool, **opcoes
    ) -> httpx.Response:
        disjuntor = self.disjuntores[servico]
        for tentativa in range(1, config.TENTATIVAS_SERVICOS + 1):
            if not disjuntor.permitir():
                logger.warning("Disjuntor do Serviço de %s aberto: chamada recusada.", servico)
                raise HTTPException(
                    status_code=503,
                    detail=f"Serviço de {servico} indisponível no momento. Nova tentativa em "
                    f"{disjuntor.segundos_para_nova_tentativa()} s.",
                )
            ultima = tentativa == config.TENTATIVAS_SERVICOS
            try:
                resposta = self.cliente.request(metodo, url, **opcoes)
            except httpx.ConnectError:
                # O pedido não chegou ao destino: repetir é seguro em qualquer operação.
                disjuntor.registrar_falha()
                logger.warning("Serviço de %s inacessível (tentativa %s).", servico, tentativa)
                if ultima or not disjuntor.permitir():
                    raise HTTPException(
                        status_code=503, detail=f"Serviço de {servico} indisponível no momento."
                    ) from None
                self._esperar_antes_de_tentar(tentativa)
                continue
            except httpx.TimeoutException:
                disjuntor.registrar_falha()
                logger.warning("Serviço de %s não respondeu dentro do prazo.", servico)
                raise HTTPException(
                    status_code=504, detail=f"O Serviço de {servico} não respondeu a tempo."
                ) from None
            except httpx.TransportError:
                disjuntor.registrar_falha()
                logger.warning("Falha de comunicação com o Serviço de %s.", servico)
                raise HTTPException(
                    status_code=503, detail=f"Serviço de {servico} indisponível no momento."
                ) from None

            if resposta.status_code >= 500:
                disjuntor.registrar_falha()
                logger.warning(
                    "Serviço de %s respondeu com erro %s (tentativa %s).",
                    servico, resposta.status_code, tentativa,
                )
                if idempotente and not ultima and disjuntor.permitir():
                    self._esperar_antes_de_tentar(tentativa)
                    continue
                raise HTTPException(
                    status_code=503, detail=f"Serviço de {servico} com falha no momento."
                )

            disjuntor.registrar_sucesso()
            if tentativa > 1:
                logger.info("Serviço de %s respondeu na tentativa %s.", servico, tentativa)
            return resposta
        raise AssertionError("inalcançável")

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

    @staticmethod
    def _cabecalho_interno() -> dict[str, str]:
        return {CABECALHO_TOKEN: config.TOKEN_INTERNO}

    def buscar_usuario(self, usuario_id: int) -> dict:
        resposta = self._chamar(
            "Usuários", "GET", f"{config.URL_USUARIOS}/usuarios/{usuario_id}",
            idempotente=True, headers=self._cabecalho_interno(),
        )
        self._repassar_erro(resposta, "Usuários")
        return resposta.json()

    def retirar_exemplar(self, exemplar_id: int) -> dict:
        resposta = self._chamar(
            "Catálogo", "POST", f"{config.URL_CATALOGO}/interno/exemplares/{exemplar_id}/retirada",
            idempotente=False, headers=self._cabecalho_interno(),
        )
        self._repassar_erro(resposta, "Catálogo")
        return resposta.json()

    def liberar_exemplar(self, exemplar_id: int) -> dict:
        resposta = self._chamar(
            "Catálogo", "POST", f"{config.URL_CATALOGO}/interno/exemplares/{exemplar_id}/liberacao",
            idempotente=True, headers=self._cabecalho_interno(),
        )
        self._repassar_erro(resposta, "Catálogo")
        return resposta.json()

    def listar_exemplares_emprestados(self, alterados_ha_segundos: int) -> list[dict]:
        resposta = self._chamar(
            "Catálogo", "GET", f"{config.URL_CATALOGO}/interno/exemplares/emprestados",
            idempotente=True, headers=self._cabecalho_interno(),
            params={"alterados_ha_segundos": alterados_ha_segundos},
        )
        self._repassar_erro(resposta, "Catálogo")
        return resposta.json()

    def resumo_disjuntores(self) -> dict:
        return {nome: disjuntor.resumo() for nome, disjuntor in self.disjuntores.items()}


_servicos: ServicosRemotos | None = None


def obter_servicos_remotos() -> ServicosRemotos:
    """Um único cliente HTTP e um par de disjuntores por processo."""
    global _servicos
    if _servicos is None:
        _servicos = ServicosRemotos(httpx.Client(timeout=config.TIMEOUT_SERVICOS))
    return _servicos
