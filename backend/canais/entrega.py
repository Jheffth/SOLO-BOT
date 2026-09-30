# -*- coding: utf-8 -*-
"""
A última milha: uma Resposta do roteador vira mensagem no aplicativo.

É o ÚNICO lugar que sabe que o Telegram tem botão e o WhatsApp não.
"""
from sqlalchemy.orm import Session

from canais import evolution, telegram
from nucleo import render, roteador


def entregar(db: Session, canal: str, origem: str, resposta: "roteador.Resposta"):
    if canal == "telegram":
        for m in resposta.mensagens:
            if m["texto"]:
                telegram.enviar(origem, m["texto"], render.teclado_telegram(m.get("opcoes")))
            _voz(canal, origem, m.get("audio"))
        return

    # WhatsApp: numeração CONTÍNUA entre as mensagens do mesmo lote, e uma
    # lista só guardada — a de agora substitui a anterior.
    itens_total = []
    for m in resposta.mensagens:
        corpo = render.para_whatsapp(m["texto"])
        itens = render.plano(m.get("opcoes"))
        if itens:
            corpo = f"{corpo}\n\n{render.lista_whatsapp(itens, inicio=len(itens_total))}"
            itens_total += itens
        if corpo:
            evolution.enviar(origem, corpo)
        _voz(canal, origem, m.get("audio"))
    if itens_total:
        roteador.guardar_escolhas(db, canal, origem, itens_total)


def _voz(canal: str, origem: str, audio):
    """A voz é um a mais: vai depois do texto, e falha aqui não derruba nada."""
    if not audio or not audio.get("base64"):
        return
    try:
        if canal == "telegram":
            import base64
            telegram.enviar_voz(origem, base64.b64decode(audio["base64"]), audio.get("mime") or "audio/ogg")
        else:
            evolution.enviar_audio(origem, audio["base64"])
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("solobot.entrega").exception("Falha ao entregar voz")
