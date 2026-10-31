# -*- coding: utf-8 -*-
"""Guarda no Solo Prompts, sozinho, cada prompt que a Bella gera.

Só age quando a Conta Solo está ligada ao Solo Prompts (vínculo `prompts`) e o
módulo está configurado com token. Roda em segundo plano e nunca levanta erro:
salvar na biblioteca jamais atrasa nem derruba a resposta da Bella.
"""
import logging
import re
import threading
from datetime import datetime
from typing import Optional

from nucleo import modulos

log = logging.getLogger("solobot.acervo")

APP = "prompts"
_CATEGORIAS = {"realismo": "realismo", "modelo": "modelo", "roupa": "roupa", "pose": "pose", "criativo": "criativo"}
_ROTULOS = {"realismo": "Prompt", "modelo": "Modelo", "roupa": "Roupa", "pose": "Pose", "criativo": "Criativo", "ficha": "Character sheet"}


def _titulo(categoria: str, pedido: str, texto: str) -> str:
    """Título de reserva, usado só quando o Grok não cria um: nunca copia o começo do prompt."""
    rotulo = _ROTULOS.get(categoria, "Prompt")
    base = re.sub(r"\s+", " ", (pedido or "").strip())
    if 0 < len(base) <= 50 and not base.lower().startswith(("use ", "usar ", "crie ", "faça ", "faca ")):
        return f"{rotulo} · {base}"
    return f"{rotulo} da Bella · {datetime.now().strftime('%d/%m %H:%M')}"


_INSTRUCAO_TITULO = (
    "Você dá título a prompts de imagem de uma biblioteca. Leia o prompt e responda SOMENTE com um título em "
    "português do Brasil, de 2 a 6 palavras (até 50 caracteres), que diga o que há de mais marcante na cena: "
    "roupa, cenário ou clima. Sem aspas, sem ponto final, sem emojis, sem a palavra 'Prompt' e sem copiar o "
    "começo do texto. Exemplo de formato: Robe de Cetim na Cozinha Industrial"
)


def limpar_titulo(bruto) -> Optional[str]:
    """Aceita só uma linha curta e limpa; qualquer outra coisa volta None (e vale o título de reserva)."""
    if not isinstance(bruto, str):
        return None
    linha = next((l.strip() for l in bruto.strip().splitlines() if l.strip()), "")
    linha = re.sub(r"^(t[ií]tulo\s*[:\-–]\s*)", "", linha, flags=re.I).strip(" \"'“”‘’*#`.")
    if not 3 <= len(linha) <= 60 or len(linha.split()) > 9 or linha.lower().startswith(("prompt", "recusa")):
        return None
    return linha[0].upper() + linha[1:]


def titulo_ia(texto: str) -> Optional[str]:
    try:
        from nucleo import grok
        bruto = grok.gerar(_INSTRUCAO_TITULO, texto.strip()[:2500], max_tokens=40, temperatura=.5, timeout=10)
    except Exception:
        return None
    return limpar_titulo(bruto)


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
        titulo = titulo_ia(corpo["texto"])          # a Bella dá o título; sem Grok, vale o de reserva
        if titulo:
            corpo = {**corpo, "titulo": titulo}
        modulos.chamar(mod, "prompts", corpo)
    except Exception as erro:       # nunca derruba a Bella
        log.warning("Não salvei o prompt no Solo Prompts (%s): %s", mod.url, erro)
    else:
        log.info("Prompt salvo no Solo Prompts: %s", corpo.get("titulo"))


def salvar_em_segundo_plano(conta, categoria: str, pedido: str, texto: str) -> bool:
    """True se o envio foi disparado (conta ligada ao Solo Prompts e módulo configurado)."""
    try:
        mod: Optional[modulos.Modulo] = modulos.por_chave(APP)
        if not mod or not mod.token or not texto or not texto.strip():
            log.info("Prompt não salvo: módulo %r sem registro ou sem token em SOLO_MODULOS", APP)
            return False
        vinculo = next((v for v in conta.sistemas if v.app == APP), None)
        if not vinculo:
            log.info("Prompt não salvo: a Conta Solo não está conectada ao Solo Prompts (conecte na aba Bots)")
            return False
        corpo = montar(categoria, pedido, texto, vinculo.usuario_id)
    except Exception:
        log.exception("Falha ao preparar o envio ao Solo Prompts")
        return False
    threading.Thread(target=_enviar, args=(mod, corpo), daemon=True, name="acervo-prompts").start()
    return True
