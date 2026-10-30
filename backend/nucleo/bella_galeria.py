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


def arquivos(modelo: str, nivel: str, so_imagem: bool = False) -> List[Path]:
    if nivel not in niveis_ativos():
        return []
    pasta = _pasta(modelo, nivel)
    if not pasta.is_dir():
        return []
    achados = [p for p in sorted(pasta.iterdir())
               if p.is_file() and EXTENSOES.get(p.suffix.lower())
               and (not so_imagem or EXTENSOES[p.suffix.lower()].startswith("image/"))]
    return achados


def contar(modelo: str = "bella") -> dict:
    return {n: len(arquivos(modelo, n)) for n in niveis_ativos()}


def _usadas(chave: str) -> List[str]:
    try:
        return list(json.loads(ler_config(chave) or "[]"))
    except Exception:  # noqa: BLE001
        return []


def escolher(modelo: str, niveis: Sequence[str], legenda: str = "", so_imagem: bool = False,
             spoiler: bool = False, rng=random) -> Optional[dict]:
    """Uma mídia {base64, mime, tipo, legenda, spoiler} já validada, do primeiro nível que tiver arquivo. None se não houver."""
    chave = f"bella_galeria_usadas:{modelo}"
    usadas = _usadas(chave)
    for nivel in niveis:
        todos = arquivos(modelo, nivel, so_imagem)
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
