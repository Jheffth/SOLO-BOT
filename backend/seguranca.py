# -*- coding: utf-8 -*-
"""Senha, sessão (JWT) e comparação de segredos."""
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import config
from database import Conta, get_db

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE = "solo_sessao"


def hash_senha(senha: str) -> str:
    return _ctx.hash(senha)


def conferir_senha(senha: str, hash_: str) -> bool:
    try:
        return _ctx.verify(senha, hash_)
    except Exception:  # noqa: BLE001
        return False


def criar_token(conta_id: int) -> str:
    exp = datetime.utcnow() + timedelta(hours=config.SESSAO_HORAS)
    return jwt.encode({"sub": str(conta_id), "exp": exp}, config.SECRET_KEY, algorithm=config.ALGORITHM)


def _conta_do_token(db: Session, token: str) -> Optional[Conta]:
    try:
        dados = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        conta_id = int(dados.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None
    conta = db.get(Conta, conta_id)
    return conta if conta and conta.ativo else None


def _token_da_requisicao(request: Request) -> Optional[str]:
    # Cookie httpOnly é o caminho do painel; Bearer existe para scripts.
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE)


def conta_opcional(request: Request, db: Session = Depends(get_db)) -> Optional[Conta]:
    token = _token_da_requisicao(request)
    return _conta_do_token(db, token) if token else None


def conta_atual(conta: Optional[Conta] = Depends(conta_opcional)) -> Conta:
    if not conta:
        raise HTTPException(401, "Sessão ausente ou expirada.")
    return conta


def conta_admin(conta: Conta = Depends(conta_atual)) -> Conta:
    if not conta.admin:
        raise HTTPException(403, "Só o administrador.")
    return conta


def iguais(a: str, b: str) -> bool:
    """Comparação em tempo constante. Vazio nunca é igual a nada."""
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())


def token_curto() -> str:
    """Seis dígitos — o que cabe numa mensagem digitada (WhatsApp)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def token_longo() -> str:
    """Para o deep link do Telegram: só [A-Za-z0-9_-], até 64 caracteres."""
    return secrets.token_urlsafe(24)
