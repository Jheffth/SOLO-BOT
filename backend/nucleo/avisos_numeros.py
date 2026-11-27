# -*- coding: utf-8 -*-
"""
AVISOS PARA NÚMEROS AVULSOS — um sistema manda um aviso para números de WhatsApp que não têm Conta Solo.

Nasceu para a Ótica Elite: venda paga na loja → aviso no WhatsApp dos donos e de quem mais estiver na lista
que a própria loja guarda. O Solo Bot não guarda a lista: ele entrega.

Regras:
  · Idempotente por (app, referencia, numero). O sistema repete o pedido à vontade (fila com retentativa) e o
    número recebe uma vez só.
  · No máximo LIMITE_NUMEROS por pedido e LIMITE_POR_MINUTO entregas por sistema, para o chip do bot não
    parecer disparo em massa.
  · Na voz da modelo: se o sistema pedir (`persona`) e a persona estiver ativa na conta do Arquiteto
    (admin), o texto é reescrito UMA vez pela modelo selecionada e vai igual para todos. A conferência
    da persona garante que valores, números do pedido e datas continuam exatos; se falhar, vai o texto
    do sistema.
  · WhatsApp desconectado → nada é registrado e o sistema recebe 503 para tentar de novo depois.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from canais import evolution
from database import AvisoNumero, Conta
from nucleo import contatos_audio, modulos

log = logging.getLogger("solobot.avisos_numeros")

LIMITE_NUMEROS = 10
LIMITE_POR_MINUTO = 30


class WhatsAppIndisponivel(Exception):
    pass


class LimiteExcedido(Exception):
    pass


def _numeros(brutos):
    validos, recusados = [], []
    for n in brutos or []:
        try:
            v = contatos_audio.numero_de_contato(str(n))
        except contatos_audio.NumeroInvalido:
            recusados.append(str(n)[:35])
            continue
        if v not in validos:
            validos.append(v)
    return validos, recusados


def conta_da_persona(db: Session):
    """A conta do Arquiteto (primeiro admin), cuja modelo selecionada dá voz aos avisos avulsos."""
    return db.query(Conta).filter(Conta.admin.is_(True), Conta.ativo.is_(True)).order_by(Conta.id).first()


def _texto_final(db: Session, mod: modulos.Modulo, texto: str, persona: bool) -> tuple:
    """(texto, na_voz_da_modelo)."""
    original = f"{mod.selo}\n{texto}"
    if not persona:
        return original, False
    from nucleo import models_persona
    conta = conta_da_persona(db)
    if conta is None or not models_persona.ativa(db, conta):
        return original, False
    try:
        nomes = mod.nome.replace("Solo ", "")
        pronto = models_persona.aplicar(conta, nomes, mod.selo, [{"texto": original}], usuario=f"[Aviso do {nomes}]")
        ultima = pronto[-1] if pronto else {}
        if ultima.get("persona") and ultima.get("texto"):
            return ultima["texto"], True
    except Exception:  # noqa: BLE001  a modelo nunca impede o aviso
        log.exception("Persona indisponível no aviso avulso; vai o texto do sistema")
    return original, False


def _entregar(db: Session, ids: list, texto: str):
    for i in ids:
        a = db.get(AvisoNumero, i)
        if a is None or a.estado != "pendente":
            continue
        try:
            r = evolution.enviar_texto_confirmado(a.numero, texto)
        except Exception:  # noqa: BLE001
            r = {"estado": "incerto", "detalhe": "Falha inesperada no envio."}
        a.estado, a.detalhe, a.mensagem_id = r["estado"], r.get("detalhe"), r.get("mensagem_id")
        db.commit()


def resumo(db: Session, app: str) -> dict:
    """Estado dos avisos de um sistema, para o painel: último aviso e contagem dos últimos 7 dias."""
    desde = datetime.utcnow() - timedelta(days=7)
    base = db.query(AvisoNumero).filter(AvisoNumero.app == app)
    ultimo = base.order_by(AvisoNumero.criado_em.desc()).first()
    semana = base.filter(AvisoNumero.criado_em >= desde)
    return {"ultimo_em": ultimo.criado_em.isoformat() + "Z" if ultimo else None,
            "ultimo_estado": ultimo.estado if ultimo else None,
            "enviados_7d": semana.filter(AvisoNumero.estado == "enviado").count(),
            "falhas_7d": semana.filter(AvisoNumero.estado.in_(("falhou", "incerto"))).count(),
            "total": base.count()}


def receber(db: Session, mod: modulos.Modulo, numeros: list, texto: str, referencia: str,
            persona: bool = False) -> dict:
    validos, recusados = _numeros(numeros)
    if len(validos) > LIMITE_NUMEROS:
        raise LimiteExcedido(f"No máximo {LIMITE_NUMEROS} números por aviso.")
    if not validos:
        return {"aceitos": 0, "repetidos": 0, "recusados": recusados, "persona": False}
    ja = {a.numero for a in db.query(AvisoNumero).filter(AvisoNumero.app == mod.chave,
                                                          AvisoNumero.referencia == referencia,
                                                          AvisoNumero.numero.in_(validos))}
    novos = [n for n in validos if n not in ja]
    if not novos:
        return {"aceitos": 0, "repetidos": len(validos), "recusados": recusados, "persona": False}
    if not evolution.disponivel() or evolution.estado_simples() != "open":
        raise WhatsAppIndisponivel("O WhatsApp do Solo Bot não está conectado.")
    recentes = db.query(AvisoNumero).filter(AvisoNumero.app == mod.chave,
                                            AvisoNumero.criado_em >= datetime.utcnow() - timedelta(minutes=1)).count()
    if recentes + len(novos) > LIMITE_POR_MINUTO:
        raise LimiteExcedido("Muitos avisos em um minuto. Tente de novo em instantes.")
    ids, repetidos = [], len(validos) - len(novos)
    for n in novos:
        a = AvisoNumero(app=mod.chave, referencia=referencia, numero=n)
        db.add(a)
        try:
            db.commit()
        except IntegrityError:          # o mesmo pedido chegou duas vezes ao mesmo tempo
            db.rollback()
            repetidos += 1
            continue
        ids.append(a.id)
    if not ids:
        return {"aceitos": 0, "repetidos": repetidos, "recusados": recusados, "persona": False}

    from nucleo import models_persona
    conta = conta_da_persona(db) if persona else None
    if conta is not None and models_persona.ativa(db, conta):
        # A reescrita leva segundos: vai na fila da persona, fora da requisição do sistema.
        app = mod.chave

        def tarefa(db2, ids=list(ids)):
            m = modulos.por_chave(app)
            final, _ = _texto_final(db2, m, texto, True)
            _entregar(db2, ids, final)

        models_persona.enfileirar(tarefa)
        return {"aceitos": len(ids), "repetidos": repetidos, "recusados": recusados, "persona": True}
    final, _ = _texto_final(db, mod, texto, False)
    _entregar(db, ids, final)
    return {"aceitos": len(ids), "repetidos": repetidos, "recusados": recusados, "persona": False}
