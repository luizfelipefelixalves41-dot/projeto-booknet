"""Login: senhas com hash e tokens de sessão assinados (JWT HS256).

Senhas
------
Nunca são guardadas. O banco guarda só o resultado do PBKDF2-SHA256, com um
"sal" aleatório por usuário e 600 mil repetições: calcular é rápido para um
login, mas lento demais para quem tentasse adivinhar milhões de senhas.

    pbkdf2_sha256$600000$<sal em base64>$<hash em base64>

Tokens de sessão (o ponto distribuído do login)
-----------------------------------------------
Ao entrar, o Serviço de Usuários devolve um token JWT assinado com um segredo
compartilhado pelos três serviços (``BOOKNET_SEGREDO_SESSAO``):

    cabeçalho.dados.assinatura      dados = {"sub": 3, "nome": "Luiz", "papel": "ALUNO", "exp": ...}

Cada serviço **confere o token sozinho**, recalculando a assinatura, sem
perguntar ao Serviço de Usuários a cada requisição. Assim, Catálogo e
Empréstimos continuam autenticando mesmo que o Serviço de Usuários esteja fora
do ar. Alterar qualquer letra dos dados (por exemplo, trocar ALUNO por
BIBLIOTECARIO) invalida a assinatura.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from backend import config

ALGORITMO_SENHA = "pbkdf2_sha256"
REPETICOES_SENHA = 600_000


def gerar_hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, REPETICOES_SENHA)
    return "$".join(
        [ALGORITMO_SENHA, str(REPETICOES_SENHA), _b64(sal), _b64(derivada)]
    )


def verificar_senha(senha: str, armazenado: str | None) -> bool:
    if not armazenado:
        return False
    try:
        algoritmo, repeticoes, sal, esperado = armazenado.split("$")
        if algoritmo != ALGORITMO_SENHA:
            return False
        derivada = hashlib.pbkdf2_hmac(
            "sha256", senha.encode("utf-8"), _de_b64(sal), int(repeticoes)
        )
    except (ValueError, TypeError):
        return False
    # Comparação em tempo constante: o tempo não revela quantos bytes acertaram.
    return hmac.compare_digest(derivada, _de_b64(esperado))


@dataclass(frozen=True)
class Sessao:
    usuario_id: int
    nome: str
    papel: str  # "ALUNO", "BIBLIOTECARIO" ou "SERVICO" (chamada interna entre serviços)

    @property
    def bibliotecario(self) -> bool:
        return self.papel in ("BIBLIOTECARIO", "SERVICO")


class TokenInvalido(Exception):
    pass


_CABECALHO_JWT = {"alg": "HS256", "typ": "JWT"}


def criar_token(usuario_id: int, nome: str, papel: str, validade_segundos: float | None = None) -> str:
    agora = int(time.time())
    validade = validade_segundos if validade_segundos is not None else config.SESSAO_VALIDADE_HORAS * 3600
    dados = {"sub": str(usuario_id), "nome": nome, "papel": papel, "iat": agora, "exp": agora + int(validade)}
    partes = [_b64_json(_CABECALHO_JWT), _b64_json(dados)]
    partes.append(_b64(_assinar(".".join(partes))))
    return ".".join(partes)


def ler_token(token: str) -> Sessao:
    try:
        cabecalho_b64, dados_b64, assinatura_b64 = token.split(".")
        cabecalho = json.loads(_de_b64(cabecalho_b64))
        # Só aceita o algoritmo esperado: bloqueia o truque de mandar "alg": "none".
        if cabecalho != _CABECALHO_JWT:
            raise TokenInvalido("Cabeçalho inválido.")
        esperado = _assinar(f"{cabecalho_b64}.{dados_b64}")
        if not hmac.compare_digest(esperado, _de_b64(assinatura_b64)):
            raise TokenInvalido("Assinatura inválida.")
        dados = json.loads(_de_b64(dados_b64))
        if int(dados["exp"]) <= time.time():
            raise TokenInvalido("Sessão expirada.")
        if dados["papel"] not in ("ALUNO", "BIBLIOTECARIO"):
            raise TokenInvalido("Papel inválido.")
        return Sessao(usuario_id=int(dados["sub"]), nome=str(dados["nome"]), papel=dados["papel"])
    except TokenInvalido:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise TokenInvalido("Token malformado.") from None


def _assinar(conteudo: str) -> bytes:
    return hmac.new(config.SEGREDO_SESSAO.encode("utf-8"), conteudo.encode("ascii"), hashlib.sha256).digest()


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _b64_json(objeto: dict) -> str:
    return _b64(json.dumps(objeto, separators=(",", ":")).encode("utf-8"))
