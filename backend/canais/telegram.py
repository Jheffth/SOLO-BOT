# -*- coding: utf-8 -*-
"""Transporte do Telegram. Só HTTP — nenhuma regra mora aqui."""
import logging

import httpx

import config

log = logging.getLogger("solobot.telegram")


def disponivel() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


def _chamar(metodo: str, corpo: dict) -> dict:
    if not disponivel():
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN ausente"}
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{metodo}"
    try:
        with httpx.Client(timeout=15) as c:
            return c.post(url, json=corpo).json()
    except Exception:  # noqa: BLE001
        log.exception("Telegram %s falhou", metodo)
        return {"ok": False, "description": "falha de rede"}


def enviar(chat_id: str, texto: str, teclado=None) -> dict:
    corpo = {"chat_id": chat_id, "text": texto[:4000], "parse_mode": "Markdown",
             "disable_web_page_preview": True}
    if teclado:
        corpo["reply_markup"] = teclado
    r = _chamar("sendMessage", corpo)
    if not r.get("ok") and "parse" in str(r.get("description", "")).lower():
        # Markdown quebrado (um "_" solto num nome) não pode calar o bot.
        corpo.pop("parse_mode")
        r = _chamar("sendMessage", corpo)
    return r


def baixar(file_id: str) -> bytes:
    """O arquivo que a pessoa mandou (getFile + download). b"" se falhar."""
    info = _chamar("getFile", {"file_id": file_id})
    caminho = (info.get("result") or {}).get("file_path")
    if not caminho:
        return b""
    try:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{caminho}")
        return r.content if r.status_code == 200 else b""
    except Exception:  # noqa: BLE001
        log.exception("Telegram: download do arquivo falhou")
        return b""


def enviar_voz(chat_id: str, conteudo: bytes, mime: str) -> bool:
    """Ogg/Opus vira a "bolinha" de voz (sendVoice); outro formato vai como áudio."""
    if not disponivel():
        return False
    ogg = mime.startswith("audio/ogg")
    metodo, campo, nome = ("sendVoice", "voice", "resposta.ogg") if ogg else ("sendAudio", "audio", "resposta.mp3")
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{metodo}"
    try:
        with httpx.Client(timeout=40) as c:
            r = c.post(url, data={"chat_id": chat_id}, files={campo: (nome, conteudo, mime)})
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        log.exception("Telegram: envio de voz falhou")
        return False


def responder_toque(callback_id: str, texto: str = "") -> dict:
    return _chamar("answerCallbackQuery", {"callback_query_id": callback_id, "text": texto[:190]})


def configurar_webhook(url: str) -> dict:
    return _chamar("setWebhook", {"url": url, "secret_token": config.TELEGRAM_SECRET,
                                  "allowed_updates": ["message", "callback_query"],
                                  "drop_pending_updates": False})


def info_webhook() -> dict:
    return _chamar("getWebhookInfo", {})


def configurar_comandos() -> dict:
    return _chamar("setMyCommands", {"commands": [
        {"command": "menu", "description": "Cartão inicial"},
        {"command": "fin", "description": "Falar com o Solo Finances"},
        {"command": "rot", "description": "Falar com o Solo Rotinas"},
        {"command": "sair", "description": "Voltar ao hub"},
        {"command": "conta", "description": "Canais e sistemas ligados"},
        {"command": "ajuda", "description": "Comandos"},
    ]})


def link_start(codigo: str) -> str:
    return f"https://t.me/{config.TELEGRAM_BOT_USERNAME}?start={codigo}"
