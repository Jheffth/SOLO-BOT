# -*- coding: utf-8 -*-
"""
OS AVISOS — sistema decide QUANDO e O QUÊ; o Solo Bot decide COMO e POR ONDE.

O que é da Conta Solo (painel → Avisos):
  · canais que recebem  — o `avisos` de cada canal (Telegram / WhatsApp)
  · horário de silêncio — ex.: 22:00 → 07:00. Aviso que chega nessa janela
    ESPERA numa fila e sai quando o silêncio termina. Nada se perde.
  · voz nos avisos      — "sistema" (padrão, "Personalizada" no painel): fala quando o sistema pede
                          (o Finances pede nos avisos em formato áudio);
                          "sempre"; "nunca".

A voz, quando vai, usa o `falado` que o sistema mandou (o roteiro para
ouvido que o Finances escreve) ou, na falta, o resumo falado da nucleo/fala.
"""
import json
import logging
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

import config
from database import AvisoPendente, Conta, VinculoSistema
from nucleo import modulos, render, roteador

log = logging.getLogger("solobot.avisos")

VOZ_AVISOS = ("sistema", "sempre", "nunca")


def agora_local() -> datetime:
    return datetime.now(ZoneInfo(config.FUSO))


def _hora(txt: Optional[str]) -> Optional[time]:
    try:
        h, m = (txt or "").split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def silencio(conta: Conta) -> Optional[tuple]:
    de, ate = _hora(conta.avisos_silencio_de), _hora(conta.avisos_silencio_ate)
    return (de, ate) if de and ate and de != ate else None


def em_silencio(conta: Conta, agora: Optional[datetime] = None) -> bool:
    janela = silencio(conta)
    if not janela:
        return False
    de, ate = janela
    t = (agora or agora_local()).time().replace(second=0, microsecond=0)
    return (de <= t < ate) if de < ate else (t >= de or t < ate)       # atravessa a meia-noite


def fim_do_silencio(conta: Conta, agora: Optional[datetime] = None) -> Optional[datetime]:
    if not em_silencio(conta, agora):
        return None
    agora = agora or agora_local()
    fim = agora.replace(hour=silencio(conta)[1].hour, minute=silencio(conta)[1].minute, second=0, microsecond=0)
    return fim if fim > agora else fim + timedelta(days=1)


def quer_voz(conta: Conta, pedido_do_sistema: Optional[bool]) -> bool:
    p = conta.avisos_voz if conta.avisos_voz in VOZ_AVISOS else "sistema"
    return p == "sempre" or (p == "sistema" and bool(pedido_do_sistema))


def _entregar(db: Session, conta: Conta, canal: str, origem: str, app: str, mensagens: list, voz: bool):
    from canais import entrega
    s = roteador.sessao_de(db, canal, origem)
    roteador._entrar_modo(db, s, app)           # responder ao aviso cai no sistema dele
    r = roteador.Resposta()
    r.mensagens = mensagens
    entrega.entregar(db, canal, origem, r, falar=voz, forcar_voz=voz)


def receber(db: Session, mod: modulos.Modulo, usuario_id: str, texto: str, opcoes=None,
            falado: Optional[str] = None, voz: Optional[bool] = None) -> dict:
    """Um aviso de um sistema. Entrega agora ou guarda para depois do silêncio."""
    v = db.query(VinculoSistema).filter(VinculoSistema.app == mod.chave,
                                        VinculoSistema.usuario_id == str(usuario_id)).first()
    if not v:
        return {"entregues": 0, "adiados": 0, "vinculado": None}
    conta = v.conta
    canais = [c for c in conta.canais if c.avisos]
    msg = {"texto": f"{mod.selo}\n{texto}", "opcoes": render.prefixar(opcoes, mod.chave)}
    if falado:
        msg["falado"] = str(falado)[:900]
    com_voz = quer_voz(conta, voz)
    entregues = adiados = 0
    silencioso = em_silencio(conta)
    for c in canais:
        if silencioso:
            db.add(AvisoPendente(conta_id=conta.id, canal=c.canal, origem=c.origem, app=mod.chave,
                                 mensagens=json.dumps([msg], ensure_ascii=False), voz=com_voz))
            adiados += 1
        else:
            _entregar(db, conta, c.canal, c.origem, mod.chave, [dict(msg)], com_voz)
            entregues += 1
    db.commit()
    roteador._registrar(db, conta, None, mod.chave, "aviso",
                        "Aviso guardado (silêncio)" if adiados else "Aviso recebido")
    return {"entregues": entregues, "adiados": adiados, "vinculado": bool(canais) or None}


def despachar_pendentes(db: Session, agora: Optional[datetime] = None) -> int:
    """Entrega o que esperava o silêncio acabar. Chamado a cada minuto."""
    n = 0
    for p in db.query(AvisoPendente).order_by(AvisoPendente.criado_em).all():
        conta = db.get(Conta, p.conta_id)
        if conta is None:
            db.delete(p)
            continue
        if em_silencio(conta, agora):
            continue
        try:
            _entregar(db, conta, p.canal, p.origem, p.app, json.loads(p.mensagens), bool(p.voz))
            n += 1
        except Exception:  # noqa: BLE001
            log.exception("Falha ao despachar aviso guardado")
        db.delete(p)
    db.commit()
    return n
