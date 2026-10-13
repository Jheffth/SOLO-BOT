"""Áudios fixos reutilizáveis; arquivos privados e gravação atômica."""
import base64
import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import config

_TRAVAS = [threading.Lock() for _ in range(64)]


def identidade(voz: str, formato: str, corpo: dict) -> str:
    # A retirada de language_code é só compatibilidade com modelos antigos.
    dados = {"voz": voz, "formato": formato,
             "corpo": {k: v for k, v in corpo.items() if k != "language_code"}}
    return hashlib.sha256(json.dumps(dados, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _arquivo(id_: str) -> Path:
    return Path(config.BELLA_AUDIO_DIR) / id_[:2] / (id_ + ".mp3")


@contextmanager
def travar(id_: str):
    with _TRAVAS[int(id_[:8], 16) % len(_TRAVAS)]:
        _arquivo(id_).parent.mkdir(parents=True, exist_ok=True)
        yield


def ler(id_: str, mime: str):
    try:
        dados = _arquivo(id_).read_bytes()
    except FileNotFoundError:
        return None
    return {"base64": base64.b64encode(dados).decode("ascii"), "mime": mime,
            "cache_id": id_} if dados else None


def gravar(id_: str, dados: bytes):
    destino = _arquivo(id_)
    fd, temporario = tempfile.mkstemp(dir=destino.parent, prefix=".audio-")
    try:
        with os.fdopen(fd, "wb") as arquivo:
            arquivo.write(dados)
        os.replace(temporario, destino)
    finally:
        if os.path.exists(temporario):
            os.unlink(temporario)
