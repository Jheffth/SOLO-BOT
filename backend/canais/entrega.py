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
            telegram.enviar(origem, m["texto"], render.teclado_telegram(m.get("opcoes")))
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
        evolution.enviar(origem, corpo)
    if itens_total:
        roteador.guardar_escolhas(db, canal, origem, itens_total)
