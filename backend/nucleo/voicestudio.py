"""Motor de reserva, chamado somente depois de falhar a ElevenLabs."""
import base64
import hashlib
import logging
from contextlib import nullcontext
from urllib.parse import urlsplit

import httpx
import config

log = logging.getLogger("solobot.voicestudio")


def disponivel() -> bool:
    return bool(config.VOICESTUDIO_URL and config.VOICESTUDIO_VOICE_ID)


def perfil() -> dict:
    return {"conta": "voicestudio", "voz": config.VOICESTUDIO_VOICE_ID,
            "modelo": config.VOICESTUDIO_MODEL,
            "origem": hashlib.sha256(config.VOICESTUDIO_URL.rstrip("/").encode()).hexdigest()}


def sintetizar(texto: str, canal: str, tom=None, guardar=False):
    if not disponivel() or not texto:
        return None
    from nucleo import audio_cache, fala

    base = config.VOICESTUDIO_URL.rstrip("/")
    try:
        destino = urlsplit(base)
    except ValueError:
        log.warning("Endereco do VoiceStudio invalido.")
        return None
    if (destino.scheme not in ("http", "https") or not destino.hostname
            or destino.username or destino.password or destino.query or destino.fragment
            or destino.path not in ("", "/v1")):
        log.warning("Endereco do VoiceStudio invalido; use a URL base do servico.")
        return None
    endpoint = base + ("/audio/speech" if destino.path == "/v1" else "/v1/audio/speech")
    formato, mime = ("opus", "audio/ogg") if canal == "telegram" else ("mp3", "audio/mpeg")
    corpo = {"model": config.VOICESTUDIO_MODEL, "voice": config.VOICESTUDIO_VOICE_ID,
             "input": fala._TAGS.sub("", texto).strip(), "language": "pt",
             "response_format": formato, "speed": 1.0, "num_step": 32}
    if not corpo["input"] or len(corpo["input"]) > 4096:
        return None
    if tom == "sussurro":
        corpo["instruct"] = "whisper"
    origem = hashlib.sha256(base.encode()).hexdigest()
    identidade = "voicestudio:" + origem + ":" + config.VOICESTUDIO_VOICE_ID
    cache_id = audio_cache.identidade(identidade, formato, corpo) if guardar else None
    perfil_voz = perfil()
    headers = {"Accept": mime}
    if config.VOICESTUDIO_API_KEY:
        headers["Authorization"] = "Bearer " + config.VOICESTUDIO_API_KEY
    try:
        with audio_cache.travar(cache_id) if guardar else nullcontext():
            audio = audio_cache.ler(cache_id, mime) if guardar else None
            if audio:
                return {**audio, "perfil_voz": perfil_voz}
            with httpx.Client(timeout=httpx.Timeout(config.VOICESTUDIO_TIMEOUT, connect=5.0),
                              follow_redirects=False) as cliente:
                resposta = cliente.post(endpoint, json=corpo, headers=headers)
            tipo = resposta.headers.get("content-type", "").split(";", 1)[0].lower()
            tipos = {"audio/ogg", "audio/opus"} if formato == "opus" else {"audio/mpeg", "audio/mp3"}
            if resposta.status_code != 200 or not resposta.content or tipo not in tipos:
                log.warning("VoiceStudio nao retornou audio valido (HTTP %s).", resposta.status_code)
                return None
            if guardar:
                audio_cache.gravar(cache_id, resposta.content)
            audio = {"base64": base64.b64encode(resposta.content).decode("ascii"), "mime": mime}
            if guardar:
                audio.update(cache_id=cache_id, perfil_voz=perfil_voz)
            return audio
    except Exception:
        # Sem URL, chave, texto, corpo de resposta ou excecao bruta nos registros.
        log.warning("VoiceStudio indisponivel; a resposta em texto continua disponivel.")
        return None
