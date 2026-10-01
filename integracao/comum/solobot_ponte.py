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
  · publica o MANIFESTO — o `bot_manifesto.json` que diz ao Solo Bot quais
    comandos este sistema tem. O Solo Bot busca de 10 em 10 minutos, e o
    sistema avisa sozinho ao subir (`anunciar_manifesto_em_segundo_plano`),
    então o deploy de um comando novo já chega ao Solo Bot.

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
import threading
import time
import urllib.error
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


def avisar(usuario_id, texto: str, opcoes=None, falado: Optional[str] = None,
           voz: Optional[bool] = None, valido_ate=None, tom: Optional[str] = None,
           formato: Optional[str] = None) -> bool:
    """
    Manda um aviso ao usuário por todos os canais dele no Solo Bot.

    `falado`: o roteiro para ouvido, se o sistema tiver (o Finances tem).
    `voz`:    True pede que o aviso seja falado (a Conta Solo decide se aceita:
              painel → Avisos → Voz nos avisos).
    `formato`: texto, audio ou ambos. Áudio exclusivo tem cópia escrita se
              a voz estiver indisponível. A preferência da Conta prevalece.
    `valido_ate`: até quando o aviso faz sentido (datetime COM fuso, ou texto
              ISO 8601 com fuso, ex. "2026-10-01T14:30:00-03:00"). Se a
              pessoa estiver no horário de silêncio e o aviso vencer na
              fila, o Solo Bot descarta em vez de entregar tarde. Use em
              avisos de prazo ("faltam 15 min", "começou agora"). Sem fuso,
              o Solo Bot lê como hora de Brasília (FUSO dele).
    `tom`:    o jeito de falar. "sussurro" = a voz do Sistema cobrando (os
              Ecos): voz própria (admin → Voz do Sistema), atuação sussurrada,
              texto em itálico e a frase falada EXATAMENTE como veio.
              Tom que o Solo Bot não conhece é ignorado.

    Devolve True se o Solo Bot aceitou — entregou agora, guardou para depois
    do horário de silêncio ou descartou por já estar vencido. Em todos esses
    casos o sistema NÃO deve tentar outro canal. Nunca levanta exceção: aviso que falha
    não pode derrubar o job que o disparou.
    """
    if not token():
        return False
    corpo = {"usuario_id": str(usuario_id), "texto": texto[:3800], "opcoes": opcoes or None}
    if falado:
        corpo["falado"] = falado[:1200]
    if voz is not None:
        corpo["voz"] = bool(voz)
    if tom:
        corpo["tom"] = str(tom)[:20]
    if formato in ("texto", "audio", "ambos"):
        corpo["formato"] = formato
    if valido_ate is not None:
        corpo["valido_ate"] = valido_ate.isoformat() if hasattr(valido_ate, "isoformat") else str(valido_ate)
    r = _post("/interno/enviar", corpo)
    return bool(r and (r.get("entregues") or r.get("adiados") or r.get("descartados")))


def situacao(usuario_id) -> dict:
    """Para a aba Bots: este usuário está conectado ao Solo Bot?"""
    if not token():
        return {"disponivel": False, "conectado": False}
    base = _cfg("SOLO_BOT_INTERNO", "http://solo_bot:8000").rstrip("/")
    req = urllib.request.Request(f"{base}/interno/vinculo/{int(usuario_id)}",
                                 headers={"X-Solo-Token": token()})
    # O MOTIVO VAI JUNTO. "Fora do ar" para tudo escondia o que importa:
    # contêiner parado, token trocado e versão antiga pedem consertos
    # diferentes, em lugares diferentes.
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"disponivel": True, **json.loads(r.read() or b"{}")}
    except urllib.error.HTTPError as e:
        if e.code == 403:
            erro = "O Solo Bot recusou o token: o BOT_SERVICE_TOKEN daqui não é o mesmo do SOLO_MODULOS de lá."
        elif e.code == 404:
            erro = "O Solo Bot respondeu, mas não tem a rota de vínculo: atualize o Solo Bot."
        else:
            erro = f"O Solo Bot respondeu com erro {e.code}. Veja: docker logs solo_bot"
        return {"disponivel": True, "conectado": None, "erro": erro}
    except Exception:  # noqa: BLE001
        return {"disponivel": True, "conectado": None,
                "erro": f"Não alcancei o Solo Bot em {base}. O contêiner solo_bot está rodando e na rede solo-network?"}


# ── Manifesto: os comandos que este sistema oferece pelo Solo Bot ─
#
# O arquivo mora ao lado desta ponte (`bot_manifesto.json`). Comando novo
# no bot = uma linha nele + `versao` nova. O teste de coerência de cada
# sistema garante que o manifesto e o bot não se desencontrem.
MANIFESTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_manifesto.json")


def ler_manifesto() -> dict:
    with open(MANIFESTO, encoding="utf-8") as f:
        dados = json.load(f)
    dados.pop("_leia", None)
    dados["app"] = _cfg("SOLO_BOT_APP") or dados.get("app")
    return dados


def anunciar_manifesto() -> bool:
    """Empurra o manifesto para o Solo Bot. True se ele aceitou."""
    if not token():
        return False
    try:
        dados = ler_manifesto()
    except Exception:  # noqa: BLE001
        log.exception("bot_manifesto.json ilegível — o Solo Bot não será avisado")
        return False
    r = _post("/interno/manifesto", dados)
    return bool(r and r.get("ok"))


def anunciar_manifesto_em_segundo_plano(tentativas=(5, 30, 120, 600)):
    """
    Para o startup do sistema. Nunca bloqueia a subida e nunca levanta:
    o Solo Bot pode estar reiniciando junto (mesmo deploy), então tenta
    algumas vezes com espera crescente. Se todas falharem, a busca
    periódica do próprio Solo Bot resolve em até 10 minutos.
    """
    if not token():
        return None

    def _tentar():
        for espera in tentativas:
            time.sleep(espera)
            if anunciar_manifesto():
                log.info("Manifesto anunciado ao Solo Bot")
                return

    t = threading.Thread(target=_tentar, name="solobot-manifesto", daemon=True)
    t.start()
    return t
