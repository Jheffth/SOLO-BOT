# -*- coding: utf-8 -*-
"""
A última milha: uma Resposta do roteador vira mensagem no aplicativo.

É o ÚNICO lugar que sabe que o Telegram tem botão e o WhatsApp não.
"""
import logging
import time

from sqlalchemy.orm import Session

from canais import evolution, telegram
from nucleo import render, roteador

log = logging.getLogger("solobot.entrega")


def entregar(db: Session, canal: str, origem: str, resposta: "roteador.Resposta",
             entrada_audio: bool = False, falar: bool = True, forcar_voz: bool = False):
    """
    `entrada_audio`: a pessoa mandou áudio (a preferência "audio" responde falado).
    `falar=False`: avisos e novidades saem só por escrito.
    """
    if canal == "whatsapp":
        return _entregar_whatsapp(db, origem, resposta, entrada_audio, falar, forcar_voz)
    _preparar_voz(db, canal, origem, resposta, entrada_audio, falar, forcar_voz)
    if canal == "telegram":
        for m in resposta.mensagens:
            exclusivo = m.get("formato") == "audio" and not m.get("opcoes")
            if exclusivo and _voz(canal, origem, m.get("audio")):
                continue
            if m["texto"]:
                telegram.enviar(origem, m["texto"], render.teclado_telegram(m.get("opcoes")))
            if not exclusivo:
                _voz(canal, origem, m.get("audio"))
        return


def _preparar_voz(db, canal, origem, resposta, entrada_audio, falar, forcar_voz):
    if not falar:
        return
    from nucleo import fala
    inicio = time.monotonic()
    try:
        fala.falar_resposta(roteador.conta_de(db, canal, origem), canal, resposta, entrada_audio,
                            forcar=forcar_voz)
    except Exception:  # a voz nunca derruba a entrega
        log.exception("Falha ao preparar a voz")
    finally:
        log.info("Entrega canal=%s etapa=preparar_voz segundos=%.3f", canal, time.monotonic() - inicio)


def _entregar_whatsapp(db, origem, resposta, entrada_audio, falar, forcar_voz):
    # Publica texto e lista antes de qualquer resumo/geração de voz.
    # As escolhas ficam disponíveis enquanto o motor de voz ainda está trabalhando.
    inicio = time.monotonic()
    itens_total = []
    mensagens = []
    for m in resposta.mensagens:
        exclusivo = m.get("formato") == "audio" and not m.get("opcoes")
        corpo = render.para_whatsapp(m["texto"])
        itens = render.plano(m.get("opcoes"))
        if itens:
            corpo = f"{corpo}\n\n{render.lista_whatsapp(itens, inicio=len(itens_total))}"
            itens_total += itens
        mensagens.append((m, corpo, exclusivo))
        if corpo and not exclusivo:
            evolution.enviar(origem, corpo)
    if itens_total:
        roteador.guardar_escolhas(db, "whatsapp", origem, itens_total)
    log.info("Entrega canal=whatsapp etapa=texto segundos=%.3f", time.monotonic() - inicio)

    _preparar_voz(db, "whatsapp", origem, resposta, entrada_audio, falar, forcar_voz)
    for m, corpo, exclusivo in mensagens:
        enviado = _voz("whatsapp", origem, m.get("audio"))
        if exclusivo and not enviado and corpo:
            evolution.enviar(origem, corpo)


def _voz(canal: str, origem: str, audio):
    """Confirma a entrega de voz; o chamador preserva texto quando necessário."""
    if not audio or not audio.get("base64"):
        return False
    try:
        if canal == "telegram":
            import base64
            return bool(telegram.enviar_voz(origem, base64.b64decode(audio["base64"]), audio.get("mime") or "audio/ogg"))
        else:
            r = evolution.enviar_audio(origem, audio["base64"])
            return bool(isinstance(r, dict) and (r.get("key") or {}).get("id") and not r.get("erro") and not r.get("error"))
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("solobot.entrega").exception("Falha ao entregar voz")
        return False
