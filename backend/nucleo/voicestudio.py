"""Motor de reserva, chamado somente depois de falhar a ElevenLabs."""
import base64
import hashlib
import logging
import time
from contextlib import nullcontext
from urllib.parse import urlsplit

import httpx
import config

log = logging.getLogger("solobot.voicestudio")


CHAVE_VOZ = "voz_voicestudio"


def voz_id() -> str:
    """A voz escolhida no painel; sem escolha, a do .env."""
    from database import ler_config
    return ler_config(CHAVE_VOZ) or config.VOICESTUDIO_VOICE_ID


def disponivel() -> bool:
    return bool(config.VOICESTUDIO_URL and voz_id())


def disponivel_servidor() -> bool:
    return bool(config.VOICESTUDIO_URL)


_VOZES = {"quando": 0.0, "origem": None, "itens": []}


def _endereco_vozes():
    base = config.VOICESTUDIO_URL.rstrip("/")
    destino = urlsplit(base)
    if (destino.scheme not in ("http", "https") or not destino.hostname
            or destino.username or destino.password or destino.query or destino.fragment
            or destino.path not in ("", "/v1")):
        return None
    return base + ("/audio/voices" if destino.path == "/v1" else "/v1/audio/voices")


def listar_vozes(forcar=False) -> list:
    """Os perfis de voz do VoiceStudio (inclui os clones): [{voice_id, nome}]. Vazio se não responder."""
    import time
    if not config.VOICESTUDIO_URL:
        return []
    origem = config.VOICESTUDIO_URL
    if (not forcar and _VOZES["origem"] == origem and time.monotonic() - _VOZES["quando"] < 30):
        return _VOZES["itens"]
    endpoint = _endereco_vozes()
    if not endpoint:
        return []
    headers = {"Authorization": "Bearer " + config.VOICESTUDIO_API_KEY} if config.VOICESTUDIO_API_KEY else {}
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False) as cliente:
            r = cliente.get(endpoint, headers=headers)
        r.raise_for_status()
        bruto = r.json()
        if isinstance(bruto, dict):
            bruto = bruto.get("voices") or bruto.get("data") or bruto.get("profiles") or []
        itens, vistos = [], set()
        for v in bruto if isinstance(bruto, list) else []:
            if isinstance(v, str):
                v = {"id": v}
            ident = str(v.get("voice_id") or v.get("id") or v.get("name") or "").strip()
            if not ident or ident in vistos:
                continue
            vistos.add(ident)
            itens.append({"voice_id": ident, "nome": str(v.get("name") or v.get("nome") or ident)[:80]})
    except Exception:
        log.warning("Nao consegui listar as vozes do VoiceStudio.")
        return []
    _VOZES.update(quando=time.monotonic(), origem=origem, itens=itens)
    return itens


def perfil() -> dict:
    return {"conta": "voicestudio", "voz": voz_id(),
            "modelo": config.VOICESTUDIO_MODEL,
            "origem": hashlib.sha256(config.VOICESTUDIO_URL.rstrip("/").encode()).hexdigest()}


def sintetizar(texto: str, canal: str, tom=None, guardar=False, id_voz=None):
    if not disponivel() or not texto:
        return None
    voz = id_voz or voz_id()
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
    corpo = {"model": config.VOICESTUDIO_MODEL, "voice": voz,
             "input": fala._TAGS.sub("", texto).strip(), "language": "pt",
             "response_format": formato, "speed": 1.0, "num_step": config.VOICESTUDIO_STEPS}
    if not corpo["input"] or len(corpo["input"]) > 4096:
        return None
    if tom == "sussurro":
        corpo["instruct"] = "whisper"
    origem = hashlib.sha256(base.encode()).hexdigest()
    identidade = "voicestudio:" + origem + ":" + voz
    cache_id = audio_cache.identidade(identidade, formato, corpo) if guardar else None
    perfil_voz = {**perfil(), "voz": voz}
    headers = {"Accept": mime}
    if config.VOICESTUDIO_API_KEY:
        headers["Authorization"] = "Bearer " + config.VOICESTUDIO_API_KEY
    try:
        with audio_cache.travar(cache_id) if guardar else nullcontext():
            audio = audio_cache.ler(cache_id, mime) if guardar else None
            if audio:
                return {**audio, "perfil_voz": perfil_voz}
            inicio = time.monotonic()
            try:
                with httpx.Client(timeout=httpx.Timeout(config.VOICESTUDIO_TIMEOUT, connect=5.0),
                                  follow_redirects=False) as cliente:
                    resposta = cliente.post(endpoint, json=corpo, headers=headers)
            finally:
                log.info("Sintese VoiceStudio: %.3fs; passos=%d",
                         time.monotonic() - inicio, config.VOICESTUDIO_STEPS)
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
