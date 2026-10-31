"""
Memória de longo prazo da Bella.

Duas coisas, ambas por Conta Solo (valem para WhatsApp, Telegram e Bella.exe):

  · FATOS — frases curtas que a pessoa pediu para ela guardar (`/lembrar`). Entram no prompt da Bella
    a cada resposta. Quem manda é a pessoa: `/memoria` lista, `/esquecer N` apaga um, `/esquecer tudo` zera.
  · TURNOS — as últimas trocas da conversa, guardadas no banco por poucos dias, só para a conversa
    sobreviver a um reinício do servidor (e, depois, para a Bella aprender fatos sozinha).

Nada aqui levanta erro para a conversa: se o banco falhar, a Bella responde como sempre, sem memória.
"""
import logging
import re
import unicodedata
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import config
from database import BellaMemoria, BellaTurno, SessionLocal, ler_config, gravar_config

log = logging.getLogger("solobot.bella_memoria")

MAX_TEXTO = 300
MIN_TEXTO = 3
BLOCO_MAX = 1000                 # caracteres de memória que vão no prompt

CABECALHO = (
    "Memórias (coisas que ele mesmo te contou; use com naturalidade quando combinar com a conversa, "
    "sem listar nem repetir toda hora; fora delas e das mensagens recentes, não invente lembranças):"
)

_SENSIVEL = re.compile(
    r"(\b(?:\d[ .-]?){13,19}\b"                         # número de cartão/conta
    r"|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"                # CPF
    r"|\b(?:senha|password|cvv|token|chave\s+pix)\b)",  # segredos
    re.IGNORECASE,
)


def _normal(texto: str) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem).strip().lower()


def _chave_off(conta_id: int) -> str:
    return f"bella_memoria_off:{int(conta_id)}"


def ativa(conta_id: Optional[int]) -> bool:
    """Falso se a pessoa desligou a memória (`/memoria desligar`)."""
    if conta_id is None:
        return False
    try:
        return ler_config(_chave_off(conta_id)) != "1"
    except Exception:  # noqa: BLE001
        return False


def definir_ativa(conta_id: int, ligada: bool) -> None:
    db = SessionLocal()
    try:
        gravar_config(db, _chave_off(conta_id), "0" if ligada else "1")
    finally:
        db.close()


# ── Fatos ────────────────────────────────────────────────────────
def adicionar(conta_id: int, texto: str, dia: Optional[str] = None) -> Tuple[bool, str]:
    """(ok, mensagem). Recusa o vazio, o longo demais, segredos e o que já está guardado."""
    texto = re.sub(r"\s+", " ", (texto or "")).strip()
    if len(texto) < MIN_TEXTO:
        return False, "Diga o que devo lembrar: `/lembrar gosto de café sem açúcar`."
    if len(texto) > MAX_TEXTO:
        return False, f"Muito longo: guardo até {MAX_TEXTO} caracteres por lembrança."
    if _SENSIVEL.search(texto):
        return False, "Não guardo senhas, documentos nem números de cartão ou conta."
    db = SessionLocal()
    try:
        existentes = db.query(BellaMemoria).filter(BellaMemoria.conta_id == conta_id).all()
        if any(_normal(m.texto) == _normal(texto) for m in existentes):
            return False, "Já tenho essa lembrança."
        if len(existentes) >= config.BELLA_MEMORIA_FATOS_MAX:
            return False, (f"A memória está cheia ({config.BELLA_MEMORIA_FATOS_MAX} lembranças). "
                           "Apague alguma com `/esquecer N`.")
        db.add(BellaMemoria(conta_id=conta_id, texto=texto, dia=dia))
        db.commit()
        return True, texto
    finally:
        db.close()


def listar(conta_id: int) -> List[str]:
    db = SessionLocal()
    try:
        linhas = (db.query(BellaMemoria).filter(BellaMemoria.conta_id == conta_id)
                  .order_by(BellaMemoria.id).all())
        return [m.texto for m in linhas]
    finally:
        db.close()


def apagar(conta_id: int, numero: int) -> Optional[str]:
    """Apaga a lembrança de número `numero` (1, 2, 3… como em `/memoria`); devolve o texto apagado."""
    db = SessionLocal()
    try:
        linhas = (db.query(BellaMemoria).filter(BellaMemoria.conta_id == conta_id)
                  .order_by(BellaMemoria.id).all())
        if not 1 <= numero <= len(linhas):
            return None
        alvo = linhas[numero - 1]
        texto = alvo.texto
        db.delete(alvo)
        db.commit()
        return texto
    finally:
        db.close()


def editar(conta_id: int, numero: int, texto: str) -> Tuple[bool, str]:
    """Troca o texto da lembrança de número `numero` (como em `/memoria`). (ok, texto novo ou motivo)."""
    texto = re.sub(r"\s+", " ", (texto or "")).strip()
    if len(texto) < MIN_TEXTO:
        return False, "Diga o novo texto: `/memoria editar 3 gosto de café com açúcar`."
    if len(texto) > MAX_TEXTO:
        return False, f"Muito longo: guardo até {MAX_TEXTO} caracteres por lembrança."
    if _SENSIVEL.search(texto):
        return False, "Não guardo senhas, documentos nem números de cartão ou conta."
    db = SessionLocal()
    try:
        linhas = (db.query(BellaMemoria).filter(BellaMemoria.conta_id == conta_id)
                  .order_by(BellaMemoria.id).all())
        if not 1 <= numero <= len(linhas):
            return False, "Não achei essa lembrança. Veja os números em `/memoria`."
        linhas[numero - 1].texto = texto
        db.commit()
        return True, texto
    finally:
        db.close()


def apagar_tudo(conta_id: int) -> int:
    db = SessionLocal()
    try:
        n = db.query(BellaMemoria).filter(BellaMemoria.conta_id == conta_id).delete()
        db.commit()
        return n
    finally:
        db.close()


def bloco_prompt(conta_id: Optional[int]) -> str:
    """O trecho de memória do prompt da Bella ('' se não houver, se estiver desligada ou se o banco falhar)."""
    if conta_id is None or not ativa(conta_id):
        return ""
    try:
        fatos = listar(int(conta_id))
    except Exception:  # noqa: BLE001
        return ""
    if not fatos:
        return ""
    escolhidos, total = [], len(CABECALHO)
    for f in reversed(fatos):                              # as mais recentes primeiro, se não couber tudo
        if total + len(f) + 3 > BLOCO_MAX:
            break
        escolhidos.append(f)
        total += len(f) + 3
    if not escolhidos:
        return ""
    return "\n\n" + CABECALHO + "\n" + "\n".join(f"- {f}" for f in reversed(escolhidos))


# ── Turnos (histórico que sobrevive ao reinício) ─────────────────
def _chave(chave) -> str:
    return str(chave)[:40]


def gravar_turno(chave, usuario: str, bella: str) -> None:
    if not config.BELLA_HISTORICO_PERSISTENTE or chave is None:
        return
    db = SessionLocal()
    try:
        db.add(BellaTurno(chave=_chave(chave), usuario=usuario, bella=bella))
        corte = datetime.utcnow() - timedelta(days=config.BELLA_HISTORICO_DIAS)
        db.query(BellaTurno).filter(BellaTurno.criado_em < corte).delete()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.debug("Não guardei o turno da Bella", exc_info=True)
    finally:
        db.close()


def turnos_recentes(chave, quantos: int, minutos: int) -> List[Tuple[str, str]]:
    """[(o que ele disse, o que ela respondeu)] dos últimos `minutos`, do mais antigo ao mais novo."""
    if not config.BELLA_HISTORICO_PERSISTENTE or chave is None or quantos <= 0:
        return []
    db = SessionLocal()
    try:
        desde = datetime.utcnow() - timedelta(minutes=minutos)
        linhas = (db.query(BellaTurno)
                  .filter(BellaTurno.chave == _chave(chave), BellaTurno.criado_em >= desde)
                  .order_by(BellaTurno.id.desc()).limit(quantos).all())
        return [(t.usuario, t.bella) for t in reversed(linhas)]
    except Exception:  # noqa: BLE001
        return []
    finally:
        db.close()


def apagar_turnos(chave) -> None:
    if chave is None:
        return
    db = SessionLocal()
    try:
        db.query(BellaTurno).filter(BellaTurno.chave == _chave(chave)).delete()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
