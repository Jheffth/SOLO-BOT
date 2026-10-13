# -*- coding: utf-8 -*-
"""Bella no Windows: chave própria, voz e sessão isoladas dos outros canais."""
import base64
import binascii
import hashlib
import io
import logging
import re
import secrets
import time
import wave
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import config
from database import Conta, get_db
from nucleo import fala, render, roteador, saudacoes, voz
from routers.atalho import _numero_falado, _sem_marcacao
from seguranca import conta_atual

router = APIRouter(tags=["bella"])
log = logging.getLogger("solobot.bella")
_JANELAS = {}
_JANELAS_SAUDACAO = {}
RE_CHAMADA = re.compile(r"^(?:(?:ei|oi|ola|olá)\s+)?(?:bella|bela)\b[\s,:.!?—-]*", re.I)


def _hash(chave):
    return hashlib.sha256(chave.encode()).hexdigest()


def _autenticar(db, chave):
    if not re.fullmatch(r"bella_[A-Za-z0-9_-]{40,80}", chave):
        raise HTTPException(401, "Chave da Bella inválida. Gere outra no painel.")
    conta = db.query(Conta).filter(Conta.bella_hash == _hash(chave)).first()
    if not conta or not conta.ativo:
        raise HTTPException(401, "Chave da Bella inválida. Gere outra no painel.")
    return conta


@router.get("/api/conta/bella")
def estado(conta: Conta = Depends(conta_atual)):
    return {"ativo": bool(conta.bella_hash), "servidor": config.URL_PUBLICA,
            "criado_em": conta.bella_criado_em.isoformat() if conta.bella_criado_em else None,
            "usado_em": conta.bella_usado_em.isoformat() if conta.bella_usado_em else None}


@router.post("/api/conta/bella")
def gerar(conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    chave = "bella_" + secrets.token_urlsafe(32)
    conta.bella_hash, conta.bella_criado_em, conta.bella_usado_em = _hash(chave), datetime.utcnow(), None
    db.commit()
    roteador._registrar(db, conta, None, None, "conta", "Chave da Bella gerada")
    return {"chave": chave, "servidor": config.URL_PUBLICA}


@router.delete("/api/conta/bella")
def revogar(conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    conta.bella_hash = conta.bella_criado_em = conta.bella_usado_em = None
    db.commit()
    return {"ok": True}


class Pedido(BaseModel):
    pedido_id: UUID
    texto: Optional[str] = Field(default=None, max_length=2000)
    audio_base64: Optional[str] = Field(default=None, max_length=4 * 1024 * 1024)
    voz: bool = True


@router.get("/api/bella/saudacoes")
def catalogo_saudacoes(x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    conta = _autenticar(db, x_bella_chave)
    return saudacoes.catalogo(conta)


class PedidoSaudacao(BaseModel):
    id: int = Field(ge=0, lt=len(saudacoes.FRASES))


@router.post("/api/bella/saudacao")
def saudacao(p: PedidoSaudacao, x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    conta = _autenticar(db, x_bella_chave)
    agora = time.monotonic()
    janela = [t for t in _JANELAS_SAUDACAO.get(conta.id, []) if agora - t < 60]
    if len(janela) >= 30:
        raise HTTPException(429, "Muitas chamadas. Espere um minuto.")
    _JANELAS_SAUDACAO[conta.id] = janela + [agora]
    try:
        return saudacoes.preparar(conta, p.id)
    except Exception:
        log.warning("Bella: não consegui preparar a saudação em áudio")
        atual = saudacoes.catalogo(conta)
        texto = atual["saudacoes"][p.id]["texto"]
        return {"id": p.id, "perfil": atual["perfil"], "texto": texto, "falar": texto}


def _audio(dados):
    try:
        conteudo = base64.b64decode(dados, validate=True)
        if not conteudo or len(conteudo) > voz.MAX_BYTES:
            raise ValueError()
        with wave.open(io.BytesIO(conteudo), "rb") as wav:
            segundos = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
                raise ValueError()
            if not 0 < segundos <= 30 or len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                raise ValueError()
        return conteudo
    except (binascii.Error, ValueError, wave.Error, EOFError, ZeroDivisionError):
        raise HTTPException(422, "Áudio inválido. Use WAV mono de 16 kHz, até 30 segundos.") from None


@router.post("/api/bella/mensagem")
def mensagem(p: Pedido, x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    conta = _autenticar(db, x_bella_chave)
    if bool(p.texto and p.texto.strip()) == bool(p.audio_base64):
        raise HTTPException(422, "Envie um pedido por texto ou áudio.")
    conteudo = _audio(p.audio_base64) if p.audio_base64 else None
    agora = time.monotonic()
    janela = [t for t in _JANELAS.get(conta.id, []) if agora - t < 60]
    if len(janela) >= 30:
        raise HTTPException(429, "Muitos pedidos. Espere um minuto.")
    _JANELAS[conta.id] = janela + [agora]
    if roteador.ja_processada(db, "bella", f"{conta.id}:{p.pedido_id}"):
        raise HTTPException(409, "Este pedido já foi recebido. Confira o resultado no sistema antes de repetir.")
    conta.bella_usado_em = datetime.utcnow()
    db.commit()
    texto = (p.texto or "").strip()
    if conteudo:
        try:
            texto = voz.transcrever(conteudo, "audio/wav")
        except voz.SemVoz:
            raise HTTPException(503, "A transcrição não está configurada no servidor. Use o campo de texto.")
        except voz.FalhaVoz as erro:
            raise HTTPException(502, "Não consegui ouvir. " + str(erro)) from None
        if not texto:
            raise HTTPException(422, "Não ouvi uma fala. Pode tentar de novo.")
    ouvido = texto
    texto = RE_CHAMADA.sub("", texto).strip()
    origem = f"bella:{conta.id}"
    s = roteador.sessao_de(db, "bella", origem)
    if s.escolhas:
        texto = _numero_falado(texto) or texto
    if not texto:
        saudacao = saudacoes.preparar(conta, secrets.randbelow(len(saudacoes.FRASES)), com_audio=p.voz)
        return {"pedido_id": str(p.pedido_id), "ouvido": ouvido, "opcoes": [], **saudacao}
    r = roteador.atender_texto(db, "bella", origem, texto, rotulo="Bella", via_audio=bool(conteudo))
    itens, blocos = [], []
    for m in r.mensagens:
        corpo = m.get("texto") or ""
        novos = render.plano(m.get("opcoes"))
        if novos:
            corpo += "\n\n" + render.lista_whatsapp(novos, inicio=len(itens)).replace("_Responda com o número._", "")
            itens += novos
        blocos.append(corpo)
    roteador.guardar_escolhas(db, "bella", origem, itens)
    try:
        falado = fala.o_que_falar(r.mensagens)
    except Exception:
        log.warning("Bella: não consegui preparar o resumo falado")
        falado = None
    falado = falado or (fala.texto_falavel("\n".join(blocos), None) or "Pronto.")[:fala.MAX_CARACTERES]
    if itens:
        falado += " Para escolher, diga o número."
    saida = {"pedido_id": str(p.pedido_id), "ouvido": ouvido, "texto": _sem_marcacao("\n\n".join(blocos)),
             "falar": falado, "opcoes": [{"numero": i, "rotulo": a["rotulo"], "titulo": a["titulo"]}
                                           for i, a in enumerate(itens, 1)]}
    if p.voz and fala.disponivel():
        try:
            audio = fala.sintetizar(falado, "whatsapp")
            if audio:
                saida.update(audio_base64=audio["base64"], mime=audio["mime"])
        except Exception:
            log.warning("Bella: falha na resposta em áudio; texto preservado")
    return saida
