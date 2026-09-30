# -*- coding: utf-8 -*-
"""
As duas portas de entrada: Telegram e WhatsApp.

Respondem 200 na hora e processam em segundo plano — os sistemas podem
levar alguns segundos, e o Telegram/Evolution reentregam o que demora.
A idempotência cuida das reentregas que escaparem.
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

import config
from canais import entrega, telegram
from database import SessionLocal
from nucleo import roteador
from seguranca import iguais

log = logging.getLogger("solobot.webhooks")
router = APIRouter(prefix="/api", tags=["webhooks"])

# O último QR que a Evolution mandou — o painel admin mostra.
ULTIMO_QR = {"base64": None, "estado": None}


# ══════════════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════════════
def _processar_telegram(update: dict):
    db = SessionLocal()
    try:
        if not roteador.ja_processada(db, "telegram", f"u{update.get('update_id')}"):
            toque = update.get("callback_query")
            if toque:
                chat = str(((toque.get("message") or {}).get("chat") or {}).get("id") or "")
                if chat:
                    r = roteador.atender_toque(db, "telegram", chat, toque.get("data") or "")
                    telegram.responder_toque(toque["id"], r.curta or "")
                    entrega.entregar(db, "telegram", chat, r)
                return
            msg = update.get("message") or {}
            chat = msg.get("chat") or {}
            if chat.get("type") != "private":
                return                       # grupo não é conosco
            texto = msg.get("text") or ""
            if not texto:
                telegram.enviar(str(chat["id"]), "Por enquanto eu só leio texto. 🙂")
                return
            de = msg.get("from") or {}
            rotulo = ("@" + de["username"]) if de.get("username") else de.get("first_name")
            r = roteador.atender_texto(db, "telegram", str(chat["id"]), texto, rotulo)
            entrega.entregar(db, "telegram", str(chat["id"]), r)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao processar update do Telegram")
        db.rollback()
    finally:
        db.close()


@router.post("/telegram/webhook")
async def webhook_telegram(request: Request, background: BackgroundTasks):
    # Sem segredo configurado, recusa TUDO: bot mudo é suporte, bot que responde a estranhos é estrago.
    if not config.TELEGRAM_SECRET:
        raise HTTPException(503, "TELEGRAM_SECRET ausente")
    if not iguais(request.headers.get("x-telegram-bot-api-secret-token", ""), config.TELEGRAM_SECRET):
        raise HTTPException(403, "segredo inválido")
    background.add_task(_processar_telegram, await request.json())
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════
# WHATSAPP (Evolution)
# ══════════════════════════════════════════════════════════════════════
def _texto(mensagem: dict) -> str:
    return (mensagem.get("conversation")
            or (mensagem.get("extendedTextMessage") or {}).get("text")
            or "").strip()


def _remetente(data: dict) -> Optional[str]:
    chave = data.get("key") or {}
    jid = chave.get("remoteJid") or ""
    if jid.endswith("@s.whatsapp.net"):
        return jid
    if jid.endswith("@lid"):
        alt = chave.get("remoteJidAlt") or chave.get("senderPn") or data.get("senderPn") or ""
        return alt if alt.endswith("@s.whatsapp.net") else jid
    return None     # grupo, status, newsletter


def _processar_whatsapp(evento: dict):
    db = SessionLocal()
    try:
        data = evento.get("data") or {}
        chave = data.get("key") or {}
        jid = _remetente(data)
        texto = _texto(data.get("message") or {})
        if not jid or not texto:
            return
        # O ECO DO PRÓPRIO APARELHO. O número do bot pode ser o celular do
        # dono: tudo que ele digita — para qualquer pessoa — e tudo que o bot
        # responde volta marcado `fromMe`. Só passa o que é inequivocamente
        # para o bot: comando, código de vínculo, ou número de uma lista
        # que acabamos de oferecer. (Mesma regra que o Rotinas já usava.)
        if chave.get("fromMe"):
            t = texto.strip()
            eh_escolha = t.isdigit() and len(t) <= 2 and bool(roteador.sessao_de(db, "whatsapp", jid).escolhas)
            if not (t.startswith("/") or roteador.RE_WHATS.match(t) or eh_escolha):
                return
            # Um "/ok" digitado para um amigo não pode fazer o bot falar com o amigo.
            if not roteador.RE_WHATS.match(t) and not roteador.conta_de(db, "whatsapp", jid):
                return
        if roteador.ja_processada(db, "whatsapp", chave.get("id")):
            return
        r = roteador.atender_texto(db, "whatsapp", jid, texto, data.get("pushName"))
        entrega.entregar(db, "whatsapp", jid, r)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao processar mensagem do WhatsApp")
        db.rollback()
    finally:
        db.close()


@router.post("/whatsapp/webhook/{segredo}")
@router.post("/whatsapp/webhook/{segredo}/{evento:path}")
async def webhook_whatsapp(segredo: str, request: Request, background: BackgroundTasks,
                           evento: str = ""):
    if not iguais(segredo, config.EVOLUTION_WEBHOOK_SECRET):
        raise HTTPException(403, "segredo inválido")
    corpo = await request.json()
    tipo = (corpo.get("event") or evento or "").lower().replace("_", ".").replace("-", ".")
    if tipo == "qrcode.updated":
        ULTIMO_QR["base64"] = ((corpo.get("data") or {}).get("qrcode") or {}).get("base64")
    elif tipo == "connection.update":
        ULTIMO_QR["estado"] = (corpo.get("data") or {}).get("state")
        if ULTIMO_QR["estado"] == "open":
            ULTIMO_QR["base64"] = None
    elif tipo == "messages.upsert":
        background.add_task(_processar_whatsapp, corpo)
    return {"ok": True}
