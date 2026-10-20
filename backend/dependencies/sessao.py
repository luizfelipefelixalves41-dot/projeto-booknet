"""Quem está chamando? Cada serviço responde sozinho, conferindo o token de sessão.

- Navegador: cabeçalho ``Authorization: Bearer <token>`` recebido no login.
- Outro serviço do BookNet: cabeçalho ``X-Servico-Token`` (chamadas internas).

Sem sessão válida → 401. Sessão válida sem permissão para a ação → 403.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from backend.autenticacao import Sessao, TokenInvalido, ler_token
from backend.dependencies.interno import CABECALHO_TOKEN, token_interno_valido

SESSAO_SERVICO = Sessao(usuario_id=0, nome="Serviço interno do BookNet", papel="SERVICO")


def obter_sessao(
    authorization: Annotated[str | None, Header()] = None,
    x_servico_token: Annotated[str | None, Header(alias=CABECALHO_TOKEN)] = None,
) -> Sessao:
    if x_servico_token is not None and token_interno_valido(x_servico_token):
        return SESSAO_SERVICO
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Faça login para continuar.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return ler_token(authorization.removeprefix("Bearer ").strip())
    except TokenInvalido:
        raise HTTPException(
            status_code=401,
            detail="Sessão inválida ou expirada. Entre novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


SessaoAtual = Annotated[Sessao, Depends(obter_sessao)]


def exigir_bibliotecario(sessao: SessaoAtual) -> Sessao:
    if not sessao.bibliotecario:
        raise HTTPException(status_code=403, detail="Apenas bibliotecários podem fazer isso.")
    return sessao


Bibliotecario = Annotated[Sessao, Depends(exigir_bibliotecario)]


def exigir_dono_ou_bibliotecario(sessao: Sessao, usuario_id: int) -> None:
    """Aluno só acessa os próprios dados; bibliotecário e serviços internos acessam tudo."""
    if not sessao.bibliotecario and sessao.usuario_id != usuario_id:
        raise HTTPException(status_code=403, detail="Você só pode acessar os seus próprios dados.")
