"""V5: reconciliação entre o Serviço de Empréstimos e o Serviço de Catálogo.

Em um sistema distribuído não existe uma transação única para dois serviços.
Se a compensação de uma saga falhar (por exemplo, o Catálogo caiu exatamente
naquele momento), um exemplar pode ficar EMPRESTADO sem nenhum empréstimo ativo:
um exemplar "preso", que nunca mais poderia ser emprestado.

A reconciliação compara as duas visões e corrige a diferença:

    Catálogo: exemplares EMPRESTADO há mais de 2 minutos   {4, 7, 9}
    Empréstimos: exemplares com empréstimo ATIVO            {4, 9}
                                                            ───────
    presos (liberar no Catálogo)                            {7}

Ela roda sozinha a cada 5 minutos e também pode ser executada pelo bibliotecário.
O intervalo de carência evita mexer em um exemplar recém-retirado cujo
empréstimo ainda está sendo gravado.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config, database
from backend.models.emprestimo import Emprestimo, StatusEmprestimo
from backend.servicos_remotos import ServicosRemotos, obter_servicos_remotos


logger = logging.getLogger("booknet.reconciliacao")
ultima_execucao: dict | None = None


def reconciliar(db: Session, servicos: ServicosRemotos) -> dict:
    global ultima_execucao
    emprestados = servicos.listar_exemplares_emprestados(config.RECONCILIACAO_CARENCIA_SEGUNDOS)
    com_emprestimo_ativo = set(
        db.scalars(
            select(Emprestimo.exemplar_id).where(Emprestimo.status == StatusEmprestimo.ATIVO)
        ).all()
    )
    presos = [exemplar for exemplar in emprestados if exemplar["id"] not in com_emprestimo_ativo]
    liberados, nao_liberados = [], []
    for exemplar in presos:
        try:
            servicos.liberar_exemplar(exemplar["id"])
            liberados.append(exemplar["codigo_tombo"])
            logger.warning("Reconciliação: exemplar %s estava preso e foi liberado.", exemplar["id"])
        except HTTPException:
            nao_liberados.append(exemplar["codigo_tombo"])
            logger.error("Reconciliação: não foi possível liberar o exemplar %s.", exemplar["id"])
    ultima_execucao = {
        "momento": datetime.now(timezone.utc).isoformat(),
        "verificados": len(emprestados),
        "liberados": liberados,
        "nao_liberados": nao_liberados,
    }
    return ultima_execucao


def _executar_agendada() -> None:
    with database.SessionLocal() as db:
        reconciliar(db, obter_servicos_remotos())


async def reconciliar_periodicamente() -> None:
    """Laço em segundo plano do Serviço de Empréstimos (desligado com intervalo 0)."""
    while True:
        await asyncio.sleep(config.RECONCILIACAO_INTERVALO_SEGUNDOS)
        try:
            await asyncio.to_thread(_executar_agendada)
        except Exception:
            # Catálogo fora do ar ou banco indisponível: tenta de novo no próximo ciclo.
            logger.warning("Reconciliação agendada não concluída; nova tentativa no próximo ciclo.")
