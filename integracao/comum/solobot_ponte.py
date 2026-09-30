# -*- coding: utf-8 -*-
"""
A PONTE PARA O SOLO BOT — o mesmo arquivo nos dois sistemas.

Copie para a raiz do backend (ao lado de main.py). Zero dependências novas:
só biblioteca padrão.

O QUE ELA FAZ

  · gera o código de conexão (o "de dentro para fora"): nasce aqui, com o
    usuário logado, e só o Solo Bot consegue trocá-lo — servidor a servidor,
    com o token de serviço.
  · confere o token de serviço nas rotas /interno/bot/*.
  · manda avisos para o Solo Bot (`avisar`).

POR QUE O CÓDIGO É ASSINADO E NÃO GUARDADO

Não precisa de tabela nem de migração. O código carrega o usuário e a
validade, assinados com o BOT_SERVICE_TOKEN. Quem não tem o token não
forja um, e quem o intercepta não o troca: o resgate exige o token também.
O uso único é garantido por uma lista de "já usados" em memória — um
reinício no meio dos 10 minutos reabre só uma janela que, de novo, exige o
token de serviço para ser explorada.

VARIÁVEIS (no .env do sistema e repassadas no docker-compose)

  BOT_SERVICE_TOKEN   o mesmo valor do bloco deste sistema em SOLO_MODULOS
  SOLO_BOT_URL        endereço público do painel  (https://solobot.duckdns.org)
  SOLO_BOT_INTERNO    endereço na rede interna    (http://solo_bot:8000)
  SOLO_BOT_APP        a chave deste sistema       (fin | rot)
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.request
from typing import Optional
from urllib.parse import quote

from fastapi import Header, HTTPException

log = logging.getLogger("solobot.ponte")

VALIDADE = 600           # segundos
_USADOS = {}             # nonce → expira em


def _cfg(nome: str, padrao: str = "") -> str:
    return (os.getenv(nome) or padrao).strip()


def token() -> str:
    return _cfg("BOT_SERVICE_TOKEN")


def disponivel() -> bool:
    return bool(token() and _cfg("SOLO_BOT_URL"))


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _assinar(corpo: str) -> str:
    return _b64(hmac.new(token().encode(), corpo.encode(), hashlib.sha256).digest()[:18])


# ── Código de conexão ────────────────────────────────────────────
def gerar_codigo(usuario_id) -> str:
    if not token():
        raise RuntimeError("BOT_SERVICE_TOKEN ausente")
    corpo = f"{int(usuario_id)}.{int(time.time()) + VALIDADE}.{_b64(secrets.token_bytes(8))}"
    return f"{corpo}.{_assinar(corpo)}"


def url_conectar(usuario_id) -> str:
    base = _cfg("SOLO_BOT_URL").rstrip("/")
    app = _cfg("SOLO_BOT_APP")
    return f"{base}/conectar?app={quote(app)}&codigo={quote(gerar_codigo(usuario_id))}"


def resgatar(codigo: str) -> Optional[int]:
    """O usuario_id, se o código for legítimo, válido e inédito. Senão None."""
    try:
        uid, exp, nonce, assinatura = (codigo or "").split(".")
        corpo = f"{uid}.{exp}.{nonce}"
        if not hmac.compare_digest(assinatura, _assinar(corpo)):
            return None
        agora = time.time()
        if int(exp) < agora:
            return None
        for n, e in list(_USADOS.items()):
            if e < agora:
                _USADOS.pop(n, None)
        if nonce in _USADOS:
            return None
        _USADOS[nonce] = int(exp)
        return int(uid)
    except (ValueError, TypeError):
        return None


# ── Guarda das rotas /interno/bot/* ──────────────────────────────
def exigir_token(x_solo_token: str = Header("")):
    esperado = token()
    if not esperado or not hmac.compare_digest(x_solo_token.encode(), esperado.encode()):
        raise HTTPException(403, "token de serviço inválido")


# ── Sistema → Solo Bot ───────────────────────────────────────────
def _post(caminho: str, corpo: dict, timeout: float = 8.0) -> Optional[dict]:
    base = _cfg("SOLO_BOT_INTERNO", "http://solo_bot:8000").rstrip("/")
    req = urllib.request.Request(f"{base}{caminho}", data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "X-Solo-Token": token()},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:  # noqa: BLE001
        log.exception("Solo Bot não respondeu em %s", caminho)
        return None


def avisar(usuario_id, texto: str, opcoes=None) -> bool:
    """
    Manda um aviso ao usuário por todos os canais dele no Solo Bot.
    Devolve True se chegou a pelo menos um canal. Nunca levanta exceção:
    aviso que falha não pode derrubar o job que o disparou.
    """
    if not token():
        return False
    r = _post("/interno/enviar", {"usuario_id": str(usuario_id), "texto": texto[:3800],
                                  "opcoes": opcoes or None})
    return bool(r and r.get("entregues"))


def situacao(usuario_id) -> dict:
    """Para a aba Bots: este usuário está conectado ao Solo Bot?"""
    if not token():
        return {"disponivel": False, "conectado": False}
    base = _cfg("SOLO_BOT_INTERNO", "http://solo_bot:8000").rstrip("/")
    req = urllib.request.Request(f"{base}/interno/vinculo/{int(usuario_id)}",
                                 headers={"X-Solo-Token": token()})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"disponivel": True, **json.loads(r.read() or b"{}")}
    except Exception:  # noqa: BLE001
        return {"disponivel": True, "conectado": None, "erro": "Solo Bot fora do ar"}
