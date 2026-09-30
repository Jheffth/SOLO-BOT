# -*- coding: utf-8 -*-
"""Cadastro, entrada e saída da Conta Solo."""
import re
import time
from typing import Optional
from collections import defaultdict, deque
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import config
from database import Atividade, Conta, get_db
from seguranca import COOKIE, conferir_senha, conta_atual, criar_token, eh_admin, hash_senha

router = APIRouter(prefix="/api/auth", tags=["auth"])

RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RE_USUARIO = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")

# Freio simples por IP. Um processo só na VPS: memória basta para frear
# força bruta; o bcrypt faz o resto.
_JANELA = 300
_LIMITE = 10
_tentativas = defaultdict(deque)


def _frear(request: Request):
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "?")
    agora = time.time()
    fila = _tentativas[ip]
    while fila and agora - fila[0] > _JANELA:
        fila.popleft()
    if len(fila) >= _LIMITE:
        raise HTTPException(429, "Muitas tentativas. Espere alguns minutos.")
    fila.append(agora)


class Cadastro(BaseModel):
    nome: str = Field(min_length=2, max_length=100)
    usuario: str = Field(min_length=3, max_length=30)
    email: Optional[str] = Field(default=None, max_length=200)   # opcional
    senha: str = Field(min_length=8, max_length=128)


class Entrada(BaseModel):
    login: Optional[str] = None      # usuário OU e-mail
    email: Optional[str] = None      # nome antigo do campo — continua aceito
    senha: str


def _abrir_sessao(response: Response, conta: Conta):
    response.set_cookie(COOKIE, criar_token(conta.id), httponly=True, samesite="lax",
                        secure=not config.DEV, max_age=config.SESSAO_HORAS * 3600, path="/")


def conta_publica(c: Conta) -> dict:
    return {"id": c.id, "nome": c.nome, "usuario": c.usuario, "email": c.email,
            "identificacao": c.usuario or c.email, "admin": c.admin,
            "criado_em": c.criado_em.isoformat() if c.criado_em else None}


def _por_login(db: Session, login: str):
    """Usuário ou e-mail, sem diferenciar maiúsculas."""
    x = (login or "").strip().lower()
    if not x:
        return None
    return db.query(Conta).filter(or_(func.lower(Conta.usuario) == x, func.lower(Conta.email) == x)).first()


@router.post("/cadastro")
def cadastro(dados: Cadastro, request: Request, response: Response, db: Session = Depends(get_db)):
    _frear(request)
    usuario = dados.usuario.strip()
    if not RE_USUARIO.match(usuario):
        raise HTTPException(422, "Usuário: 3 a 30 letras, números, ponto, hífen ou sublinhado.")
    email = (dados.email or "").strip().lower() or None
    if email and not RE_EMAIL.match(email):
        raise HTTPException(422, "E-mail inválido.")
    if _por_login(db, usuario) or (email and _por_login(db, email)):
        raise HTTPException(409, "Esse usuário ou e-mail já tem uma Conta Solo.")
    conta = Conta(nome=dados.nome.strip(), usuario=usuario, email=email, senha_hash=hash_senha(dados.senha),
                  admin=eh_admin(email, usuario), ultimo_acesso=datetime.utcnow())
    db.add(conta)
    db.commit()
    db.add(Atividade(conta_id=conta.id, tipo="conta", resumo="Conta Solo criada"))
    db.commit()
    _abrir_sessao(response, conta)
    return conta_publica(conta)


@router.post("/entrar")
def entrar(dados: Entrada, request: Request, response: Response, db: Session = Depends(get_db)):
    _frear(request)
    conta = _por_login(db, dados.login or dados.email)
    # Mesma mensagem para login inexistente e senha errada: não confirma quem tem conta.
    if not conta or not conta.ativo or not conferir_senha(dados.senha, conta.senha_hash):
        raise HTTPException(401, "Usuário ou senha não conferem.")
    conta.ultimo_acesso = datetime.utcnow()
    if not conta.admin and eh_admin(conta.email, conta.usuario):
        conta.admin = True
    db.commit()
    _abrir_sessao(response, conta)
    return conta_publica(conta)


@router.post("/sair")
def sair(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/eu")
def eu(conta: Conta = Depends(conta_atual)):
    return conta_publica(conta)
