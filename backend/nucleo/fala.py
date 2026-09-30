# -*- coding: utf-8 -*-
"""
A FALA DO SOLO BOT — responder por voz, uma vez, para todos os sistemas.

O par da `nucleo/voz.py` (que OUVE). Aqui o Solo Bot FALA: pega a resposta
de qualquer sistema e, se a pessoa quiser, manda também em áudio, com a
voz da ElevenLabs. Nenhum sistema precisa saber sintetizar.

QUANDO FALA — preferência da Conta Solo (`contas.voz`, comando `/voz`):
  · "audio"  (padrão) responde falado quando a pessoa MANDOU áudio
  · "sempre" responde falado a tudo
  · "nunca"  só texto

O QUE FALA
  · o `falado` que o sistema mandar, se mandar (o Finances manda a versão
    pensada para ouvido: "quarenta e cinco reais", com direção de atuação);
  · senão, uma versão "falável" do texto: sem emoji, sem marcação, sem a
    lista numerada e sem o eco "🎤 …". Resposta longa demais (uma lista de
    missões, um extrato) NÃO é falada: lista é para ler, e crédito da
    ElevenLabs é por caractere.
"""
import base64
import logging
import re
from typing import Optional

import httpx

import config

log = logging.getLogger("solobot.fala")

API = "https://api.elevenlabs.io/v1"
MAX_CARACTERES = 500
FORMATOS = {"telegram": ("opus_48000_64", "audio/ogg"), "whatsapp": ("mp3_44100_64", "audio/mpeg")}
MODELO_RESERVA = "eleven_flash_v2_5"
PREFERENCIAS = ("audio", "sempre", "nunca")

_estado = {"voz": None, "ultimo_erro": None}


def disponivel() -> bool:
    return bool(config.ELEVENLABS_API_KEY or config.ELEVENLABS_API_KEY_SECONDARY)


def ultimo_erro() -> Optional[str]:
    return _estado["ultimo_erro"]


# ── O que falar ──────────────────────────────────────────────────
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]+")
_TAGS = re.compile(r"\[[^\]\n]{1,40}\]")


def _reais(m: re.Match) -> str:
    inteiro, cent = m.group(1).replace(".", ""), m.group(2)
    base = f"{int(inteiro)} {'real' if inteiro == '1' else 'reais'}"
    return base if not cent or cent == "00" else f"{base} e {int(cent)} centavos"


def texto_falavel(texto: str) -> Optional[str]:
    linhas = []
    for linha in (texto or "").splitlines():
        l = linha.strip()
        if not l:
            continue
        if l.startswith("🎤") or re.match(r"^\*?\d+\.\*?\s", l) or "Responda com o número" in l:
            continue                            # eco do áudio e lista numerada: são para ler
        l = _EMOJI.sub(" ", l)
        l = re.sub(r"[*_`~•▸]", " ", l).replace("→", " para ")
        l = re.sub(r"R\$\s*([\d.]+)(?:,(\d{2}))?", _reais, l)
        l = re.sub(r"\s+", " ", l).strip(" :-–—")
        if l:
            linhas.append(l)
    if not linhas:
        return None
    falado = ". ".join(x.rstrip(".!?") for x in linhas) + "."
    return falado if len(falado) <= MAX_CARACTERES else None


def expressivo(modelo: str) -> bool:
    return modelo.startswith(("eleven_v3", "eleven_v4"))


# ── A voz ────────────────────────────────────────────────────────
def _chaves() -> list:
    return [k for k in (config.ELEVENLABS_API_KEY, config.ELEVENLABS_API_KEY_SECONDARY) if k]


def voz() -> Optional[str]:
    """ELEVENLABS_VOICE_ID se houver; senão a primeira voz da conta (própria antes de premade)."""
    if config.ELEVENLABS_VOICE_ID:
        return config.ELEVENLABS_VOICE_ID
    if _estado["voz"]:
        return _estado["voz"]
    for chave in _chaves():
        try:
            with httpx.Client(timeout=15) as c:
                r = c.get(f"{API}/voices", headers={"xi-api-key": chave})
            if r.status_code != 200:
                continue
            vozes = r.json().get("voices") or []
            ordem = {"cloned": 0, "generated": 0, "premade": 1}
            vozes.sort(key=lambda v: ordem.get(v.get("category"), 2))
            if vozes:
                _estado["voz"] = vozes[0]["voice_id"]
                return _estado["voz"]
        except Exception:  # noqa: BLE001
            log.exception("ElevenLabs: não consegui listar as vozes")
    return None


def sintetizar(texto: str, canal: str) -> Optional[dict]:
    """{base64, mime} pronto para a entrega, ou None (sem chave, sem crédito, fora do ar)."""
    if not disponivel() or not texto:
        return None
    id_voz = voz()
    if not id_voz:
        _estado["ultimo_erro"] = "nenhuma voz disponível na conta da ElevenLabs"
        return None
    formato, mime = FORMATOS.get(canal, FORMATOS["whatsapp"])
    modelo = config.ELEVENLABS_MODEL or MODELO_RESERVA

    def corpo(m: str) -> dict:
        return {"text": texto if expressivo(m) else _TAGS.sub("", texto).strip(),
                "model_id": m, "language_code": "pt",
                "voice_settings": {"stability": 0.4 if expressivo(m) else 0.5, "similarity_boost": 0.8}}

    for chave in _chaves():
        c_atual = corpo(modelo)
        for _ in range(3):
            try:
                with httpx.Client(timeout=40) as c:
                    r = c.post(f"{API}/text-to-speech/{id_voz}?output_format={formato}",
                               json=c_atual, headers={"xi-api-key": chave})
            except Exception:  # noqa: BLE001
                _estado["ultimo_erro"] = "ElevenLabs fora do alcance"
                break
            if r.status_code == 200 and r.content:
                _estado["ultimo_erro"] = None
                return {"base64": base64.b64encode(r.content).decode("ascii"), "mime": mime}
            if r.status_code == 422 and "language_code" in c_atual:
                c_atual.pop("language_code")          # modelo que não aceita o parâmetro
                continue
            if r.status_code in (400, 402, 403, 404) and c_atual["model_id"] != MODELO_RESERVA:
                c_atual = corpo(MODELO_RESERVA)       # modelo recusado pelo plano: cai no Flash
                continue
            _estado["ultimo_erro"] = f"ElevenLabs respondeu HTTP {r.status_code}"
            break                                      # 401/429/402 no Flash: tenta a outra chave
    log.warning("Fala falhou: %s", _estado["ultimo_erro"])
    return None


# ── Decidir e anexar ─────────────────────────────────────────────
def quer_falar(preferencia: Optional[str], entrada_audio: bool) -> bool:
    p = preferencia if preferencia in PREFERENCIAS else "audio"
    return p == "sempre" or (p == "audio" and entrada_audio)


def falar_resposta(conta, canal: str, resposta, entrada_audio: bool) -> None:
    """
    Anexa a voz à ÚLTIMA mensagem da resposta, se a pessoa quiser. Nunca
    levanta: a voz é um a mais, e a resposta escrita sai de qualquer jeito.
    """
    if conta is None or not resposta.mensagens or not disponivel():
        return
    if not quer_falar(getattr(conta, "voz", None), entrada_audio):
        for m in resposta.mensagens:         # quem pediu "nunca" não recebe nem a voz de um sistema
            if getattr(conta, "voz", None) == "nunca":
                m.pop("audio", None)
        return
    if any(m.get("audio") for m in resposta.mensagens):
        return                                # o sistema já mandou a própria voz
    partes = [m.get("falado") or texto_falavel(m.get("texto") or "") for m in resposta.mensagens]
    falado = " ".join(p for p in partes if p)
    if not falado or len(falado) > MAX_CARACTERES * 2:
        return
    try:
        audio = sintetizar(falado, canal)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao sintetizar")
        audio = None
    if audio:
        resposta.mensagens[-1]["audio"] = audio
