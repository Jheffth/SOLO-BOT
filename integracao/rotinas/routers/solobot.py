# -*- coding: utf-8 -*-
"""
Solo Rotinas ↔ Solo Bot.

Duas portas:
  /api/solobot/*        o hunter logado (aba Bots): conectar e ver o estado
  /interno/bot/*        só o Solo Bot, com o token de serviço, pela rede interna

O cérebro continua sendo motors/conversa.py — a mesma conversa que o
Telegram e o WhatsApp próprios usavam. Aqui ela ganha um terceiro canal,
que não entrega nada: RECOLHE o que o motor quis dizer e devolve ao Solo
Bot, que desenha (botão no Telegram, lista numerada no WhatsApp).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import solobot_ponte as ponte
from auth.router import get_usuario_atual
from database import Usuario, get_db
from motors import conversa

log = logging.getLogger("solobot")

publico = APIRouter(prefix="/api/solobot", tags=["solobot"])
interno = APIRouter(prefix="/interno/bot", tags=["solobot-interno"],
                    dependencies=[Depends(ponte.exigir_token)])


class CanalSoloBot(conversa.Canal):
    """
    O canal que recolhe.

    `nome = "solobot"` separa o `/desfazer` deste canal dos outros (AtoBot
    é por canal). `usuario` vai FIXO: quem prova quem é o hunter é o
    vínculo do Solo Bot, não um chat_id — ver o ajuste em conversa._processar.
    `botoes = True` porque o Solo Bot desenha as opções nos dois aplicativos.
    """
    nome = "solobot"
    botoes = True

    def __init__(self, origem: str, usuario: Usuario, rotulo: Optional[str] = None):
        super().__init__(origem, rotulo)
        self.usuario = usuario
        self.saida = []

    def enviar(self, texto: str, opcoes=None):
        self.saida.append({"texto": texto or "", "opcoes": opcoes or []})
        return {"ok": True}


# ── Aba Bots ──────────────────────────────────────────────────────
@publico.get("/status")
def status(usuario: Usuario = Depends(get_usuario_atual)):
    return ponte.situacao(usuario.id)


@publico.post("/conectar")
def conectar(usuario: Usuario = Depends(get_usuario_atual)):
    if not ponte.disponivel():
        raise HTTPException(503, "O Solo Bot ainda não foi configurado neste servidor.")
    return {"url": ponte.url_conectar(usuario.id)}


# ── Solo Bot → Rotinas ────────────────────────────────────────────
class Resgate(BaseModel):
    codigo: str


class Mensagem(BaseModel):
    usuario_id: str
    canal: str = "telegram"
    origem: str = ""
    texto: Optional[str] = None
    dados: Optional[str] = None
    nome: Optional[str] = None


def _usuario(db: Session, usuario_id) -> Optional[Usuario]:
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
    texto = (m.texto or "").strip() or "/ajuda"
    if texto.lower().split(" ")[0] in ("/vincular", "/desvincular"):
        return {"mensagens": [{"texto": "🔗 Os vínculos agora moram no painel do Solo Bot (/conta)."}]}
    canal = CanalSoloBot(m.origem or f"solo:{u.id}", u, m.nome)
    conversa.processar(canal, texto, db)
    return {"mensagens": canal.saida}


@interno.post("/acao")
def acao(m: Mensagem, db: Session = Depends(get_db)):
    u = _usuario(db, m.usuario_id)
    if not u:
        return {"desvinculado": True, "mensagens": []}
    if (m.dados or "") == "nada":
        return {"mensagens": []}
    canal = CanalSoloBot(m.origem or f"solo:{u.id}", u, m.nome)
    ok, curta, longa = conversa.agir(db, u, canal, m.dados or "")
    if ok and isinstance(longa, tuple) and longa and longa[0] == "__bloco__":
        conversa.mostrar_blocos(db, u, canal, longa[1])
        return {"mensagens": canal.saida, "curta": curta}
    if longa:
        canal.enviar(longa)
    elif not canal.saida:
        canal.enviar(("✅ " if ok else "⚠️ ") + (curta or ""))
    return {"mensagens": canal.saida, "curta": curta}


@interno.post("/desvinculado")
def desvinculado(m: Mensagem):
    log.info("Hunter %s desconectou o Rotinas do Solo Bot", m.usuario_id)
    return {"ok": True}
