# -*- coding: utf-8 -*-
"""
Solo Finances ↔ Solo Bot.

Duas portas:
  /api/solobot/*        o usuário logado (aba Bots): conectar e ver o estado
  /interno/bot/*        só o Solo Bot, com o token de serviço, pela rede interna

O cérebro continua sendo bot/nucleo.py. Este arquivo só traduz.
"""
import base64
import binascii
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
    # Áudio bruto: o manifesto diz ao Solo Bot que o Finances entende áudio,
    # então a voz chega inteira e é ouvida AQUI, com o contexto das contas
    # e a regra do "sim" antes de transferência (bot/voz.py).
    audio_base64: Optional[str] = None
    mime: Optional[str] = None
    via_audio: bool = False          # texto que o Solo Bot transcreveu (hub com dois sistemas)


def _usuario(db: Session, usuario_id: str) -> Optional[Usuario]:
    try:
        u = db.get(Usuario, int(usuario_id))
    except (TypeError, ValueError):
        return None
    return u if u and u.ativo else None


@interno.get("/manifesto")
def manifesto():
    """Os comandos que este sistema oferece — o Solo Bot busca de 10 em 10 min."""
    return ponte.ler_manifesto()


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
    if m.audio_base64:
        return {"mensagens": [_ouvir(db, canal, m.origem or f"solo:{u.id}", u, m)]}
    texto = (m.texto or "").strip()
    if texto.lower().split(" ")[0] in ("/vincular", "/desvincular"):
        return {"mensagens": [{"texto": "🔗 Os vínculos agora moram no painel do Solo Bot (/conta)."}]}
    if texto.lower().split(" ")[0] == "/audio":
        return {"mensagens": [{"texto": "🔊 A voz agora é do Solo Bot, para todos os sistemas: mande `/voz` "
                                        "(áudio, sempre ou nunca)."}]}
    resposta = nucleo.responder(db, canal, m.origem or f"solo:{u.id}", u, texto)
    return {"mensagens": [{"texto": resposta, "opcoes": []}]}


def _ouvir(db: Session, canal: str, origem: str, u: Usuario, m: "Mensagem") -> dict:
    """
    O mesmo caminho do áudio que chegava pelo Telegram e pelo WhatsApp próprios.

    A VOZ DE VOLTA É DO SOLO BOT: aqui só devolvemos `falado`, a versão da
    resposta pensada para o ouvido ("quarenta e cinco reais", com direção de
    atuação). Quem decide se fala (preferência /voz da Conta Solo) e quem
    sintetiza é o Solo Bot — uma voz só para todos os sistemas.
    """
    from bot import voz
    falado = None
    try:
        conteudo = base64.b64decode(m.audio_base64, validate=True)
        r = voz.processar_audio(db, canal, origem, u, conteudo, m.mime or "audio/ogg")
        texto, falado = r.texto, r.falado
    except (binascii.Error, ValueError):
        texto = "🎤 Não consegui ler o áudio. Tente de novo, ou mande por escrito."
    except voz.FalhaVoz as e:
        texto = str(e)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao processar áudio vindo do Solo Bot")
        db.rollback()
        texto = "🎤 Não consegui processar o áudio. Mande por escrito, por favor."
    msg = {"texto": texto, "opcoes": []}
    if falado:
        msg["falado"] = falado
    return msg


@interno.post("/acao")
def acao(m: Mensagem, db: Session = Depends(get_db)):
    # O Finances ainda não oferece botões. Se um dia oferecer, é aqui.
    return {"mensagens": [], "curta": "Essa opção não existe mais."}


@interno.post("/desvinculado")
def desvinculado(m: Mensagem):
    log.info("Usuário %s desconectou o Finances do Solo Bot", m.usuario_id)
    return {"ok": True}
