# -*- coding: utf-8 -*-
"""
Foto e vídeo nas respostas.

Um sistema (Solo Prompts, e depois o soDeles) devolve, ao lado de `texto` e `audio`, um campo opcional:

    "midia": {"base64": "...", "mime": "image/jpeg", "legenda": "texto curto", "spoiler": false}

O hub valida, entrega no Telegram e no WhatsApp e NUNCA deixa uma mídia ruim derrubar o texto.
Nada aqui é específico de uma personagem ou de um sistema: quem decide SE e O QUE enviar é o sistema dono
(e, para conteúdo íntimo, o código dele, nunca um modelo de linguagem).
"""
import base64
import binascii
import os
from typing import Optional

IMAGEM_MAX = int(os.getenv("MIDIA_IMAGEM_MAX", 20 * 1024 * 1024))        # até 20 MB por imagem
VIDEO_MAX = int(os.getenv("MIDIA_VIDEO_MAX", 50 * 1024 * 1024))          # até 50 MB por vídeo (limite bot Telegram e WhatsApp)
LEGENDA_MAX = 1000                   # legenda do Telegram: 1024
MIMES_IMAGEM = ("image/jpeg", "image/png", "image/webp")
MIMES_VIDEO = ("video/mp4",)


def _confere(conteudo: bytes, mime: str) -> bool:
    """O conteúdo é do tipo que diz ser (um módulo não faz um .exe passar por foto)."""
    if mime == "image/jpeg":
        return conteudo[:3] == b"\xff\xd8\xff"
    if mime == "image/png":
        return conteudo[:8] == b"\x89PNG\r\n\x1a\n"
    if mime == "image/webp":
        return conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP"
    if mime == "video/mp4":
        return conteudo[4:8] == b"ftyp"
    return False


def validar(midia) -> Optional[dict]:
    """A mídia normalizada ({base64, mime, tipo, legenda, spoiler}) ou None se algo não bate."""
    if not isinstance(midia, dict):
        return None
    mime = str(midia.get("mime") or "").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    tipo = "imagem" if mime in MIMES_IMAGEM else "video" if mime in MIMES_VIDEO else None
    b64 = midia.get("base64")
    if not tipo or not isinstance(b64, str) or not b64:
        return None
    try:
        conteudo = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not conteudo or len(conteudo) > (IMAGEM_MAX if tipo == "imagem" else VIDEO_MAX):
        return None
    if not _confere(conteudo, mime):
        return None
    legenda = midia.get("legenda")
    legenda = legenda.strip()[:LEGENDA_MAX] if isinstance(legenda, str) else ""
    return {"base64": b64, "mime": mime, "tipo": tipo, "legenda": legenda, "spoiler": bool(midia.get("spoiler"))}
