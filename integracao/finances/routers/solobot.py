# -*- coding: utf-8 -*-
"""
Solo Finances ↔ Solo Bot.

Duas portas:
  /api/solobot/*        o usuário logado (aba Bots): conectar e ver o estado
  /interno/bot/*        só o Solo Bot, com o token de serviço, pela rede interna

O cérebro continua sendo bot/nucleo.py. Este arquivo só traduz.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import solobot_ponte as ponte
from auth.router import get_usuario_atual
from bot import nucleo
from database import Usuario, get_db

log = logging.getLogger("solobot")

publico = APIRouter(prefix="/api/solobot", tags=["solobot"])
interno = APIRouter(prefix="/interno/bot", tags=["solobot-interno"],
                    dependencies=[Depends(ponte.exigir_token)])


# ── Aba Bots ──────────────────────────────────────────────────────
@publico.get("/status")
def status(usuario: Usuario = Depends(get_usuario_atual)):
    return ponte.situacao(usuario.id)


@publico.post("/conectar")
def conectar(usuario: Usuario = Depends(get_usuario_atual)):
    if not ponte.disponivel():
        raise HTTPException(503, "O Solo Bot ainda não foi configurado neste servidor.")
    return {"url": ponte.url_conectar(usuario.id)}


# ── Solo Bot → Finances ───────────────────────────────────────────
class Resgate(BaseModel):
    codigo: str


class Mensagem(BaseModel):
    usuario_id: str
    canal: str = "telegram"
    origem: str = ""
    texto: Optional[str] = None
    dados: Optional[str] = None
    nome: Optional[str] = None


def _usuario(db: Session, usuario_id: str) -> Optional[Usuario]:
    try:
        u = db.get(Usuario, int(usuario_id))
    except (TypeError, ValueError):
        return None
    return u if u and u.ativo else None


@interno.post("/resgatar")
def resgatar(r: Resgate, db: Session = Depends(get_db)):
    uid = ponte.resgatar(r.codigo)
    u = _usuario(db, uid) if uid else None
    if not u:
        raise HTTPException(404, "código inválido")
    return {"usuario_id": str(u.id), "nome": u.nome or u.login}


@interno.post("/mensagem")
def mensagem(m: Mensagem, db: Session = Depends(get_db)):
    u = _usuario(db, m.usuario_id)
    if not u:
        return {"desvinculado": True, "mensagens": []}
    # O núcleo separa sessão por (canal, id_externo). A origem que o Solo Bot
    # manda ("solo:<conta>:<canal>") é estável por conversa — é o que basta.
    canal = (m.canal or "telegram").upper()
    texto = (m.texto or "").strip()
    if texto.lower().split(" ")[0] in ("/vincular", "/desvincular"):
        return {"mensagens": [{"texto": "🔗 Os vínculos agora moram no painel do Solo Bot (/conta)."}]}
    resposta = nucleo.responder(db, canal, m.origem or f"solo:{u.id}", u, texto)
    return {"mensagens": [{"texto": resposta, "opcoes": []}]}


@interno.post("/acao")
def acao(m: Mensagem, db: Session = Depends(get_db)):
    # O Finances ainda não oferece botões. Se um dia oferecer, é aqui.
    return {"mensagens": [], "curta": "Essa opção não existe mais."}


@interno.post("/desvinculado")
def desvinculado(m: Mensagem):
    log.info("Usuário %s desconectou o Finances do Solo Bot", m.usuario_id)
    return {"ok": True}
