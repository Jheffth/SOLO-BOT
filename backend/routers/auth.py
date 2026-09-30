# -*- coding: utf-8 -*-
"""Cadastro, entrada e saída da Conta Solo."""
import re
import time
from collections import defaultdict, deque
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import config
from database import Atividade, Conta, get_db
from seguranca import COOKIE, conferir_senha, conta_atual, criar_token, hash_senha

router = APIRouter(prefix="/api/auth", tags=["auth"])

RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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
    email: str = Field(max_length=200)
    senha: str = Field(min_length=8, max_length=128)


class Entrada(BaseModel):
    email: str
    senha: str


def _abrir_sessao(response: Response, conta: Conta):
    response.set_cookie(COOKIE, criar_token(conta.id), httponly=True, samesite="lax",
                        secure=not config.DEV, max_age=config.SESSAO_HORAS * 3600, path="/")


def conta_publica(c: Conta) -> dict:
    return {"id": c.id, "nome": c.nome, "email": c.email, "admin": c.admin,
            "criado_em": c.criado_em.isoformat() if c.criado_em else None}


@router.post("/cadastro")
def cadastro(dados: Cadastro, request: Request, response: Response, db: Session = Depends(get_db)):
    _frear(request)
    email = dados.email.strip().lower()
    if not RE_EMAIL.match(email):
        raise HTTPException(422, "E-mail inválido.")
    if db.query(Conta).filter(Conta.email == email).first():
        raise HTTPException(409, "Já existe uma Conta Solo com esse e-mail.")
    conta = Conta(nome=dados.nome.strip(), email=email, senha_hash=hash_senha(dados.senha),
                  admin=email in config.ADMIN_EMAILS, ultimo_acesso=datetime.utcnow())
    db.add(conta)
    db.commit()
    db.add(Atividade(conta_id=conta.id, tipo="conta", resumo="Conta Solo criada"))
    db.commit()
    _abrir_sessao(response, conta)
    return conta_publica(conta)


@router.post("/entrar")
def entrar(dados: Entrada, request: Request, response: Response, db: Session = Depends(get_db)):
    _frear(request)
    conta = db.query(Conta).filter(Conta.email == dados.email.strip().lower()).first()
    # Mesma mensagem para e-mail inexistente e senha errada: não confirma quem tem conta.
    if not conta or not conta.ativo or not conferir_senha(dados.senha, conta.senha_hash):
        raise HTTPException(401, "E-mail ou senha não conferem.")
    conta.ultimo_acesso = datetime.utcnow()
    if conta.email in config.ADMIN_EMAILS and not conta.admin:
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
