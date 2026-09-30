# -*- coding: utf-8 -*-
"""
O registro dos sistemas e o único cliente HTTP que fala com eles.

Um sistema é um dicionário em config.MODULOS. O Solo Bot não sabe o que é
um lançamento nem uma missão: manda o texto, recebe `{mensagens: [...]}`.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

import config
from seguranca import iguais

log = logging.getLogger("solobot.modulos")

TIMEOUT = httpx.Timeout(12.0, connect=3.0)


@dataclass(frozen=True)
class Modulo:
    chave: str
    nome: str
    emoji: str
    cor: str
    descricao: str
    url: str
    token: str
    painel: str

    @property
    def selo(self) -> str:
        return f"{self.emoji} *{self.nome.replace('Solo ', '')}*"

    def publico(self) -> dict:
        return {"chave": self.chave, "nome": self.nome, "emoji": self.emoji,
                "cor": self.cor, "descricao": self.descricao, "painel": self.painel,
                "configurado": bool(self.token)}


class ErroModulo(Exception):
    """O sistema não respondeu, ou respondeu errado. A mensagem é para humanos."""


def _carregar() -> dict:
    saida = {}
    for m in config.MODULOS:
        mod = Modulo(chave=m["chave"], nome=m["nome"], emoji=m.get("emoji", "•"),
                     cor=m.get("cor", "#8b5cf6"), descricao=m.get("descricao", ""),
                     url=(m.get("url") or "").rstrip("/"), token=m.get("token", ""),
                     painel=m.get("painel", ""))
        saida[mod.chave] = mod
    return saida


_REGISTRO = _carregar()


def todos() -> list:
    return list(_REGISTRO.values())


def por_chave(chave: str) -> Optional[Modulo]:
    return _REGISTRO.get((chave or "").lower())


def por_token(token: str) -> Optional[Modulo]:
    for m in _REGISTRO.values():
        if iguais(token or "", m.token):
            return m
    return None


def recarregar(modulos: list):
    """Para os testes (e para quem quiser trocar a config sem reiniciar)."""
    global _REGISTRO
    config.MODULOS = modulos
    _REGISTRO = _carregar()


# O ponto que os testes trocam por uma caixa de mentira.
def _post(url: str, token: str, corpo: dict) -> httpx.Response:
    with httpx.Client(timeout=TIMEOUT) as c:
        return c.post(url, json=corpo, headers={"X-Solo-Token": token})


def _get(url: str, token: str) -> httpx.Response:
    with httpx.Client(timeout=TIMEOUT) as c:
        return c.get(url, headers={"X-Solo-Token": token})


def buscar(mod: Modulo, rota: str) -> dict:
    """GET em /interno/bot/<rota>. Mesmas regras de erro do `chamar`."""
    if not mod.token:
        raise ErroModulo(f"{mod.nome} ainda não foi configurado no Solo Bot.")
    try:
        r = _get(f"{mod.url}/interno/bot/{rota}", mod.token)
    except httpx.HTTPError:
        raise ErroModulo(f"{mod.nome} não respondeu.")
    if r.status_code >= 400:
        raise ErroModulo(f"{mod.nome} recusou o pedido ({r.status_code}).")
    try:
        return r.json()
    except ValueError:
        raise ErroModulo(f"{mod.nome} respondeu algo que não entendi.")


def chamar(mod: Modulo, rota: str, corpo: dict) -> dict:
    if not mod.token:
        raise ErroModulo(f"{mod.nome} ainda não foi configurado no Solo Bot.")
    try:
        r = _post(f"{mod.url}/interno/bot/{rota}", mod.token, corpo)
    except httpx.HTTPError:
        log.exception("Falha de rede com %s (%s)", mod.chave, rota)
        raise ErroModulo(f"{mod.nome} não respondeu. Tente de novo em instantes.")
    if r.status_code == 404 and rota == "resgatar":
        raise ErroModulo("Código inválido ou expirado. Gere outro no sistema.")
    if r.status_code >= 400:
        log.error("%s respondeu %s em %s: %s", mod.chave, r.status_code, rota, r.text[:200])
        raise ErroModulo(f"{mod.nome} recusou o pedido ({r.status_code}).")
    try:
        return r.json()
    except ValueError:
        raise ErroModulo(f"{mod.nome} respondeu algo que não entendi.")
