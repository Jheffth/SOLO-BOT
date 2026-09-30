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


# ══════════════════════════════════════════════════════════════════════
# PAREAR O NÚMERO — portado do motors/evolution.py do Rotinas, que por sua
# vez veio do Solo CMV. As armadilhas que eles já pagaram para aprender:
#
#   · O WEBHOOK DA v2 É UM OBJETO ({"webhook": {...}}); no formato antigo a
#     v2 aceita e ignora, e o QR nunca chega.
#   · O ESTADO É "close", SEM O D.
#   · Instância em "close" está TRAVADA: o /connect devolve {"count": 0} e
#     QR nenhum. Tem de apagar e recriar. Em "connecting" NÃO se recria —
#     alguém pode estar com o QR na mão.
#   · A instância pode nem existir (404): cria-se com o webhook já junto.
# ══════════════════════════════════════════════════════════════════════
EVENTOS = ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "QRCODE_UPDATED"]


def _chamar(metodo: str, caminho: str, corpo: dict = None, timeout: int = 15) -> tuple:
    """(status_http, dados). status 0 = não alcançou a Evolution."""
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.request(metodo, f"{config.EVOLUTION_API_URL}{caminho}", json=corpo,
                          headers={"apikey": config.EVOLUTION_API_KEY})
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {}
    except Exception as e:  # noqa: BLE001
        log.warning("Evolution %s %s falhou: %s", metodo, caminho, type(e).__name__)
        return 0, {}


def _bloco_webhook(url: str) -> dict:
    return {"enabled": True, "url": url, "byEvents": False, "base64": False, "events": EVENTOS}


def estado_simples() -> str:
    """'open' | 'connecting' | 'close' | 'inexistente' | 'inacessivel' | 'chave_invalida'."""
    st, d = _chamar("GET", f"/instance/connectionState/{config.EVOLUTION_INSTANCE}", timeout=8)
    if st == 0:
        return "inacessivel"
    if st in (401, 403):
        return "chave_invalida"
    if st == 404:
        return "inexistente"
    return ((d.get("instance") or {}).get("state") or d.get("state") or "close").lower()


def configurar_webhook(url: str) -> dict:
    st, d = _chamar("POST", f"/webhook/set/{config.EVOLUTION_INSTANCE}", {"webhook": _bloco_webhook(url)})
    return {"ok": st in (200, 201), "status": st}


def _criar_instancia(url: str) -> int:
    st, _ = _chamar("POST", "/instance/create", {
        "instanceName": config.EVOLUTION_INSTANCE, "qrcode": True,
        "integration": "WHATSAPP-BAILEYS", "webhook": _bloco_webhook(url)}, timeout=20)
    return st


def _normalizar_qr(b64):
    if b64 and not b64.startswith("data:"):
        return f"data:image/png;base64,{b64}"
    return b64


def parear(url_webhook: str) -> dict:
    """
    Deixa o número pronto para ler o QR. Devolve
    {estado, qr?, pairing_code?, webhook_ok, detalhe?}.
    """
    estado_atual = estado_simples()
    if estado_atual in ("inacessivel", "chave_invalida"):
        detalhe = ("Não alcancei a Evolution em " + config.EVOLUTION_API_URL
                   if estado_atual == "inacessivel" else "A Evolution recusou a EVOLUTION_API_KEY.")
        return {"estado": estado_atual, "webhook_ok": False, "detalhe": detalhe}

    if estado_atual == "open":
        wh = configurar_webhook(url_webhook)
        return {"estado": "open", "webhook_ok": wh["ok"],
                "detalhe": "O número já está conectado. Só o webhook foi reaplicado."}

    if estado_atual in ("close", "closed", "refused"):
        _chamar("DELETE", f"/instance/delete/{config.EVOLUTION_INSTANCE}", timeout=10)
        _criar_instancia(url_webhook)
    elif estado_atual == "inexistente":
        _criar_instancia(url_webhook)
    wh = configurar_webhook(url_webhook)

    st, d = _chamar("GET", f"/instance/connect/{config.EVOLUTION_INSTANCE}", timeout=20)
    if st not in (200, 201):
        return {"estado": estado_simples(), "webhook_ok": wh["ok"],
                "detalhe": f"A Evolution não devolveu o QR (HTTP {st})."}
    qr = _normalizar_qr(d.get("base64") or (d.get("qrcode") or {}).get("base64"))
    return {"estado": estado_simples(), "qr": qr, "pairing_code": d.get("pairingCode"),
            "webhook_ok": wh["ok"],
            "detalhe": None if qr else "A Evolution ainda não gerou o QR. Ele chega pelo webhook em segundos."}


def link_wa(texto: str) -> str:
    return f"https://wa.me/{config.WHATSAPP_NUMERO}?text={quote(texto)}"
