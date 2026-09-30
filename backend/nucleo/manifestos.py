# -*- coding: utf-8 -*-
"""
OS MANIFESTOS — como o Solo Bot descobre o que cada sistema sabe fazer.

A lógica dos comandos mora nos sistemas (o `/saldo` é do Finances, o `/ok`
é do Rotinas). O Solo Bot não precisa saber COMO eles funcionam, mas
precisa saber QUE existem: para a ajuda, o painel e o anúncio de
novidades. Cada sistema declara isso no `bot_manifesto.json` dele.

DOIS CAMINHOS, e por que os dois

  · EMPURRADO — o sistema, ao subir, manda o manifesto (POST
    /interno/manifesto). É o que faz um deploy chegar aqui na hora.
  · BUSCADO — de 10 em 10 minutos o Solo Bot pede (GET
    /interno/bot/manifesto). Cobre o caso de o Solo Bot estar fora do
    ar justamente quando o sistema subiu.

NOVIDADES

Versão nova de um manifesto que já conhecíamos = anúncio para quem tem
aquele sistema conectado: as `novidades` e os comandos que não existiam.
O PRIMEIRO manifesto de um sistema não é anunciado — seria anunciar o
sistema inteiro como "novidade" no dia da instalação.
"""
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from database import ManifestoModulo, VinculoSistema
from nucleo import modulos, roteador

log = logging.getLogger("solobot.manifestos")

RE_COMANDO = re.compile(r"^/[a-z0-9_]{1,30}$")


class Comando(BaseModel):
    comando: str
    descricao: str = Field(max_length=140)
    exemplo: Optional[str] = Field(default=None, max_length=140)
    oculto: bool = False            # existe no sistema, mas não faz sentido pelo Solo Bot

    @field_validator("comando")
    @classmethod
    def _formato(cls, v):
        v = (v or "").strip().lower()
        if not RE_COMANDO.match(v):
            raise ValueError("comando deve ser /minusculas_sem_espaco")
        return v


class Audio(BaseModel):
    recebe: bool = False            # entende o áudio bruto (senão o Solo Bot transcreve)


class Manifesto(BaseModel):
    versao: str = Field(min_length=1, max_length=40)
    audio: Audio = Field(default_factory=Audio)
    comandos: List[Comando] = Field(default_factory=list, max_length=80)
    exemplos: List[str] = Field(default_factory=list, max_length=12)
    novidades: List[str] = Field(default_factory=list, max_length=10)

    @field_validator("exemplos", "novidades")
    @classmethod
    def _curtos(cls, v):
        return [str(x)[:300] for x in v if str(x).strip()]


class ManifestoInvalido(Exception):
    pass


def validar(bruto: dict) -> Manifesto:
    try:
        return Manifesto.model_validate(bruto or {})
    except ValidationError as e:
        raise ManifestoInvalido(str(e.errors()[0].get("msg", "manifesto inválido")))


# ── Leitura ───────────────────────────────────────────────────────
def de(db: Session, app: str) -> Optional[dict]:
    m = db.get(ManifestoModulo, app)
    if not m:
        return None
    dados = json.loads(m.dados)
    dados["recebido_em"] = m.recebido_em.isoformat() if m.recebido_em else None
    dados["origem"] = m.origem
    return dados


def comandos_visiveis(db: Session, app: str) -> list:
    d = de(db, app)
    return [c for c in (d or {}).get("comandos", []) if not c.get("oculto")]


def recebe_audio(db: Session, app: str) -> bool:
    return bool(((de(db, app) or {}).get("audio") or {}).get("recebe"))


# ── Gravação ──────────────────────────────────────────────────────
def guardar(db: Session, mod: modulos.Modulo, bruto: dict, origem: str) -> dict:
    """
    Valida e grava. Devolve {mudou, anunciado} — `anunciado` é quantos
    canais receberam as novidades (0 se nada mudou ou se é o primeiro).
    """
    novo = validar(bruto)
    atual = db.get(ManifestoModulo, mod.chave)
    anterior = json.loads(atual.dados) if atual else None

    if atual and atual.versao == novo.versao:
        atual.recebido_em = datetime.utcnow()
        atual.origem = origem
        db.commit()
        return {"mudou": False, "anunciado": 0}

    dados = novo.model_dump()
    if not atual:
        atual = ManifestoModulo(app=mod.chave)
        db.add(atual)
    atual.versao = novo.versao
    atual.dados = json.dumps(dados, ensure_ascii=False)
    atual.recebido_em = datetime.utcnow()
    atual.origem = origem
    db.commit()
    log.info("Manifesto de %s: versão %s (%s)", mod.chave, novo.versao, origem)

    if anterior is None:
        return {"mudou": True, "anunciado": 0}
    return {"mudou": True, "anunciado": _anunciar(db, mod, anterior, dados)}


def _texto_novidades(mod: modulos.Modulo, anterior: dict, novo: dict) -> Optional[str]:
    antes = {c["comando"] for c in anterior.get("comandos", [])}
    novos = [c for c in novo.get("comandos", []) if c["comando"] not in antes and not c.get("oculto")]
    notas = novo.get("novidades") or []
    if not novos and not notas:
        return None
    linhas = [f"✨ *Novidades no {mod.emoji} {mod.nome}*", ""]
    linhas += [f"• {n}" for n in notas]
    if novos:
        if notas:
            linhas.append("")
        linhas.append("*Comandos novos*")
        for c in novos:
            linhas.append(f"▸ `/{mod.chave} {c['comando'].lstrip('/')}` — {c['descricao']}")
    return "\n".join(linhas)


def _anunciar(db: Session, mod: modulos.Modulo, anterior: dict, novo: dict) -> int:
    from canais import entrega
    texto = _texto_novidades(mod, anterior, novo)
    if not texto:
        return 0
    n = 0
    for v in db.query(VinculoSistema).filter(VinculoSistema.app == mod.chave).all():
        for c in v.conta.canais:
            if not c.avisos:
                continue
            try:
                entrega.entregar(db, c.canal, c.origem, roteador.Resposta().diz(texto), falar=False)
                n += 1
            except Exception:  # noqa: BLE001
                log.exception("Falha ao anunciar novidades de %s", mod.chave)
    return n


# ── Busca periódica ───────────────────────────────────────────────
def buscar_todos(db: Session) -> dict:
    """Pede o manifesto a cada sistema configurado. {app: 'ok' | motivo}."""
    resultado = {}
    for mod in modulos.todos():
        if not mod.token:
            resultado[mod.chave] = "sem token"
            continue
        try:
            r = guardar(db, mod, modulos.buscar(mod, "manifesto"), "buscado")
            resultado[mod.chave] = "ok" + (" (nova versão)" if r["mudou"] else "")
        except (modulos.ErroModulo, ManifestoInvalido) as e:
            resultado[mod.chave] = str(e)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.exception("Busca do manifesto de %s falhou", mod.chave)
            resultado[mod.chave] = f"erro: {e}"[:200]
    return resultado
