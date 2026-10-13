# -*- coding: utf-8 -*-
"""
A VOZ DO SOLO BOT — ouvir uma vez, para todos os sistemas.

DOIS CAMINHOS PARA UM ÁUDIO

  · Há um único sistema conectado e ele declara que entende áudio (`"audio": {"recebe":
    true}`) — caso do Finances, que interpreta a fala com o contexto das
    contas e pede "sim" antes de transferência. O Solo Bot só entrega os
    bytes; a inteligência é do sistema.
  · Há vários sistemas conectados, ou o único sistema não entende áudio.
    O Solo Bot TRANSCREVE aqui e escolhe o destino pelo texto, permitindo
    trocar de sistema mesmo durante o modo Finances.

Transcrição: Gemini (principal e reserva) e Grok, na ordem em que houver
chave. O áudio não é guardado em lugar nenhum.
"""
import base64
import logging
from typing import Callable, List

import httpx

import config

log = logging.getLogger("solobot.voz")

MAX_SEGUNDOS = 90
MAX_BYTES = 3 * 1024 * 1024

PROMPT = ("Transcreva fielmente esta mensagem de voz em português do Brasil. "
          "Responda SOMENTE com o texto falado, sem aspas, sem comentários. "
          "Valores em dinheiro em algarismos (\"quarenta e cinco\" = 45). "
          "Se não houver fala compreensível, responda vazio.")


class SemVoz(Exception):
    """Nenhuma chave de transcrição configurada."""


class FalhaVoz(Exception):
    """Todos os motores falharam."""


def _motivo(erro: Exception) -> str:
    """Diagnóstico sem corpo da resposta, endereço, chave ou texto pessoal."""
    if isinstance(erro, httpx.HTTPStatusError):
        codigo = erro.response.status_code
        return {429: "limite de uso atingido (HTTP 429)", 401: "chave recusada (HTTP 401)",
                403: "acesso recusado (HTTP 403)", 404: "modelo indisponível (HTTP 404)",
                400: "pedido de áudio recusado (HTTP 400)"}.get(codigo, f"serviço respondeu HTTP {codigo}")
    if isinstance(erro, httpx.TimeoutException):
        return "tempo de resposta esgotado"
    if isinstance(erro, httpx.RequestError):
        return "falha de conexão com o serviço"
    return "resposta de transcrição inválida"


def disponivel() -> bool:
    return bool(config.GEMINI_API_KEY or config.GEMINI_API_KEY_RESERVA or config.GROK_API_KEY)


def _limpo(mime: str) -> str:
    return (mime or "audio/ogg").split(";")[0].strip() or "audio/ogg"


def _gemini(chave: str, rotulo: str) -> Callable:
    def ouvir(conteudo: bytes, mime: str) -> str:
        corpo = {"contents": [{"role": "user", "parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(conteudo).decode("ascii")}}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 1024}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
        with httpx.Client(timeout=40) as c:
            r = c.post(url, json=corpo, headers={"x-goog-api-key": chave})
        r.raise_for_status()
        cand = r.json()["candidates"][0]
        if cand.get("finishReason") not in (None, "STOP"):
            raise ValueError("transcrição incompleta")
        return "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought")).strip()
    ouvir.nome = f"gemini/{rotulo}"
    return ouvir


def _grok(chave: str) -> Callable:
    def ouvir(conteudo: bytes, mime: str) -> str:
        ext = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav",
               "audio/webm": "webm"}.get(mime, "ogg")
        with httpx.Client(timeout=40) as c:
            r = c.post("https://api.x.ai/v1/stt", headers={"Authorization": f"Bearer {chave}"},
                       data={"model": config.GROK_STT_MODEL, "language": "pt", "format": "true"},
                       files={"file": (f"audio.{ext}", conteudo, mime)})
        r.raise_for_status()
        return str(r.json().get("text") or "").strip()
    ouvir.nome = "grok"
    return ouvir


def motores() -> List[Callable]:
    fila = []
    if config.GEMINI_API_KEY:
        fila.append(_gemini(config.GEMINI_API_KEY, "principal"))
    if config.GEMINI_API_KEY_RESERVA:
        fila.append(_gemini(config.GEMINI_API_KEY_RESERVA, "reserva"))
    if config.GROK_API_KEY:
        fila.append(_grok(config.GROK_API_KEY))
    return fila


def transcrever(conteudo: bytes, mime: str) -> str:
    """O texto falado ("" se não houver fala). Levanta SemVoz ou FalhaVoz."""
    fila = motores()
    if not fila:
        raise SemVoz()
    mime = _limpo(mime)
    falhas = []
    for motor in fila:
        try:
            texto = motor(conteudo, mime)
            log.info("Áudio transcrito via %s", motor.nome)
            return texto.strip().strip('"“”').strip()[:1000]
        except Exception as e:  # noqa: BLE001
            motivo = _motivo(e)
            nome = getattr(motor, "nome", "serviço")
            log.warning("Transcrição via %s falhou: %s", nome, motivo)
            falhas.append(f"{nome}: {motivo}")
    raise FalhaVoz("; ".join(falhas))
