"""V5: disjuntor (circuit breaker) para as chamadas entre serviços.

Funciona como o disjuntor de uma casa:

    FECHADO ──(N falhas seguidas)──▶ ABERTO ──(espera T segundos)──▶ MEIO_ABERTO
       ▲                                ▲                               │
       └────────── 1 sucesso ───────────┼──────────── 1 falha ──────────┘

- FECHADO: tudo normal, as chamadas passam.
- ABERTO: o serviço remoto está com problemas; as chamadas falham na hora, sem
  esperar o tempo limite. Isso evita filas de requisições paradas e dá tempo
  para o serviço doente se recuperar.
- MEIO_ABERTO: passado o tempo de espera, uma chamada de teste é liberada. Se
  der certo, o circuito fecha; se falhar, abre de novo.
"""

import threading
import time
from enum import Enum
from typing import Callable


class EstadoDisjuntor(str, Enum):
    FECHADO = "FECHADO"
    ABERTO = "ABERTO"
    MEIO_ABERTO = "MEIO_ABERTO"


class Disjuntor:
    def __init__(
        self,
        nome: str,
        limite_falhas: int = 3,
        segundos_aberto: float = 30.0,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.nome = nome
        self.limite_falhas = limite_falhas
        self.segundos_aberto = segundos_aberto
        self._relogio = relogio
        self._trava = threading.Lock()  # rotas síncronas rodam em várias threads
        self._estado = EstadoDisjuntor.FECHADO
        self._falhas_seguidas = 0
        self._aberto_em = 0.0

    @property
    def estado(self) -> EstadoDisjuntor:
        with self._trava:
            self._atualizar()
            return self._estado

    def _atualizar(self) -> None:
        if (
            self._estado == EstadoDisjuntor.ABERTO
            and self._relogio() - self._aberto_em >= self.segundos_aberto
        ):
            self._estado = EstadoDisjuntor.MEIO_ABERTO

    def permitir(self) -> bool:
        with self._trava:
            self._atualizar()
            return self._estado != EstadoDisjuntor.ABERTO

    def registrar_sucesso(self) -> None:
        with self._trava:
            self._estado = EstadoDisjuntor.FECHADO
            self._falhas_seguidas = 0

    def registrar_falha(self) -> None:
        with self._trava:
            self._falhas_seguidas += 1
            if (
                self._estado == EstadoDisjuntor.MEIO_ABERTO
                or self._falhas_seguidas >= self.limite_falhas
            ):
                self._estado = EstadoDisjuntor.ABERTO
                self._aberto_em = self._relogio()

    def segundos_para_nova_tentativa(self) -> int:
        with self._trava:
            if self._estado != EstadoDisjuntor.ABERTO:
                return 0
            restante = self.segundos_aberto - (self._relogio() - self._aberto_em)
            return max(0, round(restante))

    def resumo(self) -> dict:
        estado = self.estado
        return {
            "estado": estado.value,
            "falhas_seguidas": self._falhas_seguidas,
            "nova_tentativa_em_segundos": self.segundos_para_nova_tentativa(),
        }
