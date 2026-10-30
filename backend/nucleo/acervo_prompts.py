# -*- coding: utf-8 -*-
"""Guarda no Solo Prompts, sozinho, cada prompt que a Bella gera.

Só age quando a Conta Solo está ligada ao Solo Prompts (vínculo `prompts`) e o
módulo está configurado com token. Roda em segundo plano e nunca levanta erro:
salvar na biblioteca jamais atrasa nem derruba a resposta da Bella.
"""
import logging
import re
import threading
from typing import Optional

from nucleo import modulos

log = logging.getLogger("solobot.acervo")

APP = "prompts"
_CATEGORIAS = {"realismo": "realismo", "modelo": "modelo", "roupa": "roupa", "pose": "pose", "criativo": "criativo"}
_ROTULOS = {"realismo": "Prompt", "modelo": "Modelo", "roupa": "Roupa", "pose": "Pose", "criativo": "Criativo", "ficha": "Character sheet"}


def _titulo(categoria: str, pedido: str, texto: str) -> str:
    base = re.sub(r"\s+", " ", (pedido or "").strip())
    if not base:
        primeira = next((l.strip() for l in texto.splitlines() if l.strip()), "")
        base = re.sub(r"\s+", " ", primeira)
    rotulo = _ROTULOS.get(categoria, "Prompt")
    base = base[:90].rstrip(" ,.;:-")
    return f"{rotulo} · {base}" if base else f"{rotulo} da Bella"


def montar(categoria: str, pedido: str, texto: str, usuario_id: str) -> dict:
    return {
        "usuario_id": str(usuario_id),
        "origem": "bella",
        "titulo": _titulo(categoria, pedido, texto)[:120],
        "texto": texto.strip()[:8000],
        "categoria": _CATEGORIAS.get(categoria, "outro"),
        "tags": ["bella", categoria][:15],
    }


def _enviar(mod, corpo: dict):
    try:
        modulos.chamar(mod, "prompts", corpo)
    except Exception as erro:       # nunca derruba a Bella
        log.warning("Não salvei o prompt no Solo Prompts: %s", erro)


def salvar_em_segundo_plano(conta, categoria: str, pedido: str, texto: str) -> bool:
    """True se o envio foi disparado (conta ligada ao Solo Prompts e módulo configurado)."""
    try:
        mod: Optional[modulos.Modulo] = modulos.por_chave(APP)
        if not mod or not mod.token or not texto or not texto.strip():
            return False
        vinculo = next((v for v in conta.sistemas if v.app == APP), None)
        if not vinculo:
            return False
        corpo = montar(categoria, pedido, texto, vinculo.usuario_id)
    except Exception:
        log.exception("Falha ao preparar o envio ao Solo Prompts")
        return False
    threading.Thread(target=_enviar, args=(mod, corpo), daemon=True, name="acervo-prompts").start()
    return True
