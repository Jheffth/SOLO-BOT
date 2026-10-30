"""
A galeria de fotos e vídeos da Bella (primeira versão, em pastas), que o soDeles herda depois.

Layout (no servidor, `BELLA_GALERIA_DIR`, padrão `dados/galeria`):

    galeria/bella/bom_dia/*.jpg      foto do "bom dia" das 08:00
    galeria/bella/normal/*.jpg|mp4   fotos e vídeos do dia a dia
    galeria/bella/sensual/*.jpg|mp4  sensuais (só para o Arquiteto)

Só os níveis de `BELLA_GALERIA_NIVEIS` (padrão `bom_dia,normal,sensual`) são servidos. Pastas de nível mais
íntimo (lingerie, topless, nu) são IGNORADAS aqui de propósito: elas dependem do jogo do agrado e das travas da
seção 5 de SODELES_ESPECIFICACAO_GALERIA.md, que ainda não existem no código.

Quem escolhe é o código (sorteio sem repetir as últimas), nunca o modelo de linguagem.
"""
import base64
import json
import logging
import random
from pathlib import Path
from typing import List, Optional, Sequence

import config
from canais import midia as canal_midia
from database import SessionLocal, gravar_config, ler_config

log = logging.getLogger("solobot.bella_galeria")

EXTENSOES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".mp4": "video/mp4"}
LEMBRAR_ULTIMAS = 30


def niveis_ativos() -> List[str]:
    return [n.strip() for n in config.BELLA_GALERIA_NIVEIS.split(",") if n.strip()]


def _pasta(modelo: str, nivel: str) -> Path:
    return Path(config.BELLA_GALERIA_DIR) / modelo / nivel


def arquivos(modelo: str, nivel: str, so_imagem: bool = False, tipo: Optional[str] = None) -> List[Path]:
    if nivel not in niveis_ativos():
        return []
    pasta = _pasta(modelo, nivel)
    if not pasta.is_dir():
        return []
    achados = [p for p in sorted(pasta.iterdir())
               if p.is_file() and EXTENSOES.get(p.suffix.lower())
               and (not so_imagem or EXTENSOES[p.suffix.lower()].startswith("image/"))
               and (tipo is None or EXTENSOES[p.suffix.lower()].startswith("video/" if tipo == "video" else "image/"))]
    return achados


def contar(modelo: str = "bella") -> dict:
    return {n: len(arquivos(modelo, n)) for n in niveis_ativos()}


def _usadas(chave: str) -> List[str]:
    try:
        return list(json.loads(ler_config(chave) or "[]"))
    except Exception:  # noqa: BLE001
        return []


def escolher(modelo: str, niveis: Sequence[str], legenda: str = "", so_imagem: bool = False,
             spoiler: bool = False, rng=random, tipo: Optional[str] = None) -> Optional[dict]:
    """Uma mídia {base64, mime, tipo, legenda, spoiler} já validada, do primeiro nível que tiver arquivo. None se não houver."""
    chave = f"bella_galeria_usadas:{modelo}"
    usadas = _usadas(chave)
    for nivel in niveis:
        todos = arquivos(modelo, nivel, so_imagem, tipo)
        if not todos:
            continue
        novos = [p for p in todos if f"{nivel}/{p.name}" not in usadas] or todos      # esgotou: recomeça
        for _ in range(min(5, len(novos))):                                           # arquivo ruim não trava o sorteio
            p = rng.choice(novos)
            try:
                conteudo = p.read_bytes()
            except OSError:
                novos = [x for x in novos if x != p]
                continue
            v = canal_midia.validar({"base64": base64.b64encode(conteudo).decode(), "mime": EXTENSOES[p.suffix.lower()],
                                     "legenda": legenda, "spoiler": spoiler})
            if v:
                db = SessionLocal()
                try:
                    gravar_config(db, chave, json.dumps((usadas + [f"{nivel}/{p.name}"])[-LEMBRAR_ULTIMAS:]))
                finally:
                    db.close()
                return v
            novos = [x for x in novos if x != p]
            log.warning("Arquivo da galeria recusado (tipo ou tamanho): %s", p.name)
    return None


def provedor_iniciativa(conta) -> Optional[dict]:
    """Para `bella_iniciativa.PROVEDORES_MIDIA`: um vídeo ou foto normal/sensual para o Arquiteto."""
    if not getattr(conta, "admin", False):
        return None
    return escolher("bella", ("sensual", "normal") if random.random() < .5 else ("normal", "sensual"))


provedor_iniciativa.disponivel = lambda: any(contar("bella").get(n) for n in ("normal", "sensual"))   # type: ignore[attr-defined]


# ── Quando ele PEDE uma foto ou um vídeo ─────────────────────────
# Cada nível pede um agrado mínimo (0-100) e um grau mínimo do termômetro (0 Normal … 3 Explícita), como na seção 2
# de SODELES_ESPECIFICACAO_GALERIA.md. Ordem firme do Arquiteto ("eu mando", "é uma ordem") dispensa os dois.
REGRAS = {"bom_dia": (0, 0), "normal": (5, 0), "sensual": (25, 0), "lingerie": (30, 1), "topless": (60, 2), "nu": (85, 3)}
SPOILER = ("topless", "nu")
CUSTO = {"video": 20, "foto": 10}
_VERBO = None
_VIDEO = None
_FOTO = None


def _rx():
    import re
    global _VERBO, _VIDEO, _FOTO
    if _VERBO is None:
        _VERBO = re.compile(r"\b(?:manda|mande|mandar|envia|envie|enviar|mostra|mostre|mostrar|quero ver|me da|cade|tem (?:algum|alguma|um|uma))\b")
        _VIDEO = re.compile(r"\bvideo(?:s|zinho|zinhos)?\b|\bclipe\b")
        _FOTO = re.compile(r"\bfot(?:o|inha|ozinha)s?\b|\bselfie\b|\bimagem\b|\bprint\b")
    return _VERBO, _VIDEO, _FOTO


def detectar_pedido(texto: str) -> Optional[str]:
    """'video', 'foto' ou None. Precisa de um verbo de pedir e de foto/vídeo na mesma mensagem."""
    from nucleo import bella_emocoes
    verbo, video, foto = _rx()
    t = bella_emocoes._norm(texto)
    if not verbo.search(t):
        return None
    if video.search(t):
        return "video"
    if foto.search(t):
        return "foto"
    return None


def decidir(estado: dict, pedido: str, firme: bool, rng=random) -> tuple:
    """('enviar', midia, nivel) | ('negar', motivo, None) | ('vazio', '', None). Quem decide é o código."""
    tipo = "video" if pedido == "video" else "imagem"
    chateada = estado.get("emocao") not in ("alegre", "reencontro")
    if chateada and not firme:
        return "negar", "chateada", None
    agrado, grau = estado.get("agrado", 0), estado.get("nivel", 0)
    existem = [n for n in niveis_ativos() if arquivos("bella", n, tipo=tipo)]
    if not existem:
        return "vazio", "", None
    liberados = [n for n in existem if firme or (agrado >= REGRAS.get(n, (999, 9))[0] and grau >= REGRAS.get(n, (999, 9))[1])]
    if not liberados:
        return "negar", "agrado", None
    nivel = rng.choice(liberados)
    m = escolher("bella", (nivel,), tipo=tipo, spoiler=nivel in SPOILER, rng=rng)
    if not m:
        return "vazio", "", None
    return "enviar", m, nivel
