# -*- coding: utf-8 -*-
"""Transporte do WhatsApp via Evolution API v2. Só HTTP."""
import logging
from urllib.parse import quote

import httpx

import config

log = logging.getLogger("solobot.evolution")


def disponivel() -> bool:
    return bool(config.EVOLUTION_API_KEY)


def _req(metodo: str, caminho: str, corpo: dict = None) -> dict:
    if not disponivel():
        return {"erro": "EVOLUTION_API_KEY ausente"}
    url = f"{config.EVOLUTION_API_URL}{caminho}"
    try:
        with httpx.Client(timeout=20) as c:
            r = c.request(metodo, url, json=corpo, headers={"apikey": config.EVOLUTION_API_KEY})
            try:
                return r.json()
            except ValueError:
                return {"status": r.status_code}
    except Exception:  # noqa: BLE001
        log.exception("Evolution %s %s falhou", metodo, caminho)
        return {"erro": "falha de rede"}


def enviar(jid: str, texto: str) -> dict:
    numero = jid.split("@")[0]
    return _req("POST", f"/message/sendText/{config.EVOLUTION_INSTANCE}",
                {"number": numero, "text": texto[:4000]})


def enviar_audio(jid: str, audio_b64: str) -> dict:
    """Mensagem de VOZ (a bolinha do microfone), não arquivo."""
    return _req("POST", f"/message/sendWhatsAppAudio/{config.EVOLUTION_INSTANCE}",
                {"number": jid.split("@")[0], "audio": audio_b64, "encoding": True, "delay": 200})


def midia_base64(chave: dict, mensagem: dict) -> dict:
    """O conteúdo de uma mídia recebida: {base64, mimetype}. {} se falhar."""
    r = _req("POST", f"/chat/getBase64FromMediaMessage/{config.EVOLUTION_INSTANCE}",
             {"message": {"key": chave, "message": mensagem}, "convertToMp4": False})
    return r if isinstance(r, dict) and r.get("base64") else {}


def estado() -> dict:
    return _req("GET", f"/instance/connectionState/{config.EVOLUTION_INSTANCE}")


def conectar() -> dict:
    """Devolve o QR (base64) quando a instância está desconectada."""
    return _req("GET", f"/instance/connect/{config.EVOLUTION_INSTANCE}")


def configurar_webhook(url: str) -> dict:
    return _req("POST", f"/webhook/set/{config.EVOLUTION_INSTANCE}", {"webhook": {
        "enabled": True, "url": url, "byEvents": False, "base64": False,
        "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "QRCODE_UPDATED"]}})


def link_wa(texto: str) -> str:
    return f"https://wa.me/{config.WHATSAPP_NUMERO}?text={quote(texto)}"
