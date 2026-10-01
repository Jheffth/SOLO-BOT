# -*- coding: utf-8 -*-
"""
SIRI / ATALHOS DO iPHONE — "Ei Siri, Solo".

O atalho do iPhone dita o que a pessoa falou, manda para cá e fala a
resposta. Do lado de cá é só MAIS UM CANAL ("siri"): o mesmo roteador,
a mesma intenção, o mesmo modo ativo do Telegram e do WhatsApp.

POR QUE UMA CHAVE PRÓPRIA, E NÃO O LOGIN

O atalho roda sem tela, sem cookie, no relógio e no carro. Ele precisa de
algo que mora dentro dele: uma chave pessoal, gerada no painel. Guardamos
só o sha256 (quem lê o banco não fala em nome de ninguém), ela aparece UMA
vez e pode ser revogada ou trocada a qualquer momento.

O CONTRATO (o que o atalho faz)

  POST /api/atalho
  cabeçalho  X-Solo-Chave: solo_...
  corpo      {"texto": "some 25 na meta da noite", "voz": false}
  resposta   {"falar": "...", "texto": "...", "audio_base64"?: "...", "mime"?: "audio/mpeg"}

  `falar`  o que a Siri deve dizer (curto; listas viram resumo)
  `texto`  a resposta escrita, sem marcação, para "Mostrar resultado"
  `voz`    true = vem também o áudio na voz do Solo Bot (ElevenLabs)

Opções (botões) viram lista numerada; a próxima fala "dois" escolhe.
"""
import hashlib
import logging
import re
import secrets
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import config
from database import Conta, get_db
from nucleo import render, roteador
from seguranca import conta_atual

log = logging.getLogger("solobot.atalho")

router = APIRouter(tags=["atalho"])

PREFIXO = "solo_"
_JANELA: dict = {}                 # conta_id → [instantes]; freio simples contra laço
LIMITE_POR_MINUTO = 30

NUMEROS = {"um": 1, "uma": 1, "primeiro": 1, "primeira": 1, "dois": 2, "duas": 2, "segundo": 2,
           "segunda": 2, "tres": 3, "três": 3, "terceiro": 3, "terceira": 3, "quatro": 4,
           "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10}
RE_ESCOLHA = re.compile(r"^(?:(?:a|o)\s+)?(?:op[cç][aã]o|n[uú]mero|item)?\s*([\wçãéê]+)$", re.I)


def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def _origem(conta: Conta) -> str:
    return f"siri:{conta.id}"


def _conta_da_chave(db: Session, chave: str) -> Optional[Conta]:
    chave = (chave or "").strip()
    if not chave.startswith(PREFIXO) or len(chave) < 30:
        return None
    c = db.query(Conta).filter(Conta.atalho_hash == _hash(chave)).first()
    return c if c and c.ativo else None


def _freio(conta_id: int) -> bool:
    agora = time.time()
    janela = [t for t in _JANELA.get(conta_id, []) if agora - t < 60]
    janela.append(agora)
    _JANELA[conta_id] = janela
    return len(janela) > LIMITE_POR_MINUTO


def _numero_falado(texto: str) -> Optional[str]:
    """ "dois", "opção 2", "o número três" → "2". Só quando é SÓ isso. """
    t = re.sub(r"[.!?,]", "", (texto or "").strip().lower())
    m = RE_ESCOLHA.match(t)
    if not m:
        return None
    w = m.group(1)
    if w.isdigit():
        return w
    n = NUMEROS.get(w)
    return str(n) if n else None


def _sem_marcacao(t: str) -> str:
    t = re.sub(r"[*_`~]", "", t or "")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


# ── O atalho ─────────────────────────────────────────────────────
class Pedido(BaseModel):
    texto: str = Field(min_length=1, max_length=600)
    voz: bool = False


@router.post("/api/atalho")
def atalho(p: Pedido, x_solo_chave: str = Header(""), db: Session = Depends(get_db)):
    conta = _conta_da_chave(db, x_solo_chave)
    if not conta:
        raise HTTPException(401, "Chave da Siri inválida. Gere outra no painel do Solo Bot.")
    if _freio(conta.id):
        raise HTTPException(429, "Muitos pedidos em sequência. Espere um minuto.")
    conta.atalho_usado_em = datetime.utcnow()
    db.commit()

    origem = _origem(conta)
    texto = p.texto.strip()
    s = roteador.sessao_de(db, "siri", origem)
    if s.escolhas:
        texto = _numero_falado(texto) or texto

    r = roteador.atender_texto(db, "siri", origem, texto, rotulo="Siri")
    mensagens = [m for m in (r.mensagens or []) if m.get("texto") or m.get("opcoes")]

    # Opções viram lista numerada; o próximo "dois" escolhe (validade curta, uso único).
    itens = []
    blocos = []
    for m in mensagens:
        corpo = m.get("texto") or ""
        novos = render.plano(m.get("opcoes"))
        if novos:
            lista = render.lista_whatsapp(novos, inicio=len(itens)).replace("_Responda com o número._", "")
            corpo = f"{corpo}\n\n{lista}".strip()
            itens += novos
        blocos.append(corpo)
    roteador.guardar_escolhas(db, "siri", origem, itens)

    from nucleo import fala
    try:
        falar = fala.o_que_falar(mensagens) if mensagens else None
    except Exception:  # noqa: BLE001
        log.exception("Siri: falha ao montar a fala")
        falar = None
    if not falar:
        falar = (fala.texto_falavel("\n".join(blocos), None) or "Pronto.")[:fala.MAX_CARACTERES]
    if itens:
        falar = f"{falar.rstrip()} Para escolher, diga o número."

    saida = {"falar": falar, "texto": _sem_marcacao("\n\n".join(blocos)) or falar}
    if p.voz and fala.disponivel():
        audio = fala.sintetizar(falar, "whatsapp")          # mp3: o "Reproduzir Som" do iPhone toca
        if audio:
            saida["audio_base64"], saida["mime"] = audio["base64"], audio["mime"]
    return saida


# ── O painel: gerar, ver, revogar ────────────────────────────────
@router.get("/api/conta/atalho")
def estado(conta: Conta = Depends(conta_atual)):
    return {"ativo": bool(conta.atalho_hash),
            "criado_em": conta.atalho_criado_em.isoformat() if conta.atalho_criado_em else None,
            "usado_em": conta.atalho_usado_em.isoformat() if conta.atalho_usado_em else None,
            "url": f"{config.URL_PUBLICA}/api/atalho"}


@router.post("/api/conta/atalho")
def gerar(conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    """Gera (ou troca) a chave. Ela aparece UMA vez: aqui só fica o hash."""
    chave = PREFIXO + secrets.token_urlsafe(32)
    conta.atalho_hash = _hash(chave)
    conta.atalho_criado_em = datetime.utcnow()
    conta.atalho_usado_em = None
    db.commit()
    roteador._registrar(db, conta, None, None, "conta", "Chave da Siri gerada")
    return {"chave": chave, "url": f"{config.URL_PUBLICA}/api/atalho"}


@router.delete("/api/conta/atalho")
def revogar(conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    conta.atalho_hash = conta.atalho_criado_em = conta.atalho_usado_em = None
    db.commit()
    roteador._registrar(db, conta, None, None, "conta", "Chave da Siri revogada")
    return {"ok": True}
