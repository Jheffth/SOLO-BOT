# -*- coding: utf-8 -*-
"""Uma chamada de texto à Gemini (chave principal, depois a reserva). Nunca levanta."""
import logging
from typing import Optional

import httpx

import config

log = logging.getLogger("solobot.gemini")


def disponivel() -> bool:
    return bool(config.GEMINI_API_KEY or config.GEMINI_API_KEY_RESERVA)


def gerar(instrucao: str, texto: str, json_saida: bool = False, max_tokens: int = 256,
          temperatura: float = 0.0, timeout: float = 12) -> Optional[str]:
    """O texto gerado, ou None se não houver chave ou todas falharem."""
    chaves = [k for k in (config.GEMINI_API_KEY, config.GEMINI_API_KEY_RESERVA) if k]
    if not chaves:
        return None
    geracao = {"temperature": temperatura, "maxOutputTokens": max_tokens}
    if json_saida:
        geracao["responseMimeType"] = "application/json"
    corpo = {"systemInstruction": {"parts": [{"text": instrucao}]},
             "contents": [{"role": "user", "parts": [{"text": texto}]}],
             "generationConfig": geracao}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    for chave in chaves:
        try:
            with httpx.Client(timeout=timeout) as c:
                r = c.post(url, json=corpo, headers={"x-goog-api-key": chave})
            r.raise_for_status()
            partes = r.json()["candidates"][0]["content"]["parts"]
            saida = "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()
            if saida:
                return saida
        except Exception as e:  # noqa: BLE001
            log.warning("Gemini falhou: %s", type(e).__name__)
    return None
