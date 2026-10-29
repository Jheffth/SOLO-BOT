"""
A história entre a pessoa e a Bella, guardada em "pastas" por dia.

  · ARQUIVO — toda troca da conversa, sem prazo, com o dia (horário de Brasília). É a pasta do dia.
  · RESUMO do dia — feito pelo Grok depois que o dia termina: o que aconteceu, o que ela sentiu, o que combinaram.
  · LEMBRANÇAS automáticas — fatos duradouros tirados do dia (carregam o dia, para sumir junto com ele).

A Bella lê no prompt os resumos mais recentes (os mais novos com mais detalhe). Quem manda é a pessoa:
`/historia` lista as pastas, e `/esquecer hoje|ontem|dia 25/10|ultimos 3 dias` apaga SÓ essas pastas
(arquivo, resumo e lembranças automáticas daqueles dias); o resto da história fica.
`/esquecer tudo` (lembranças) NÃO apaga a história; para isso existe `/esquecer historia tudo confirmo`.

Nada aqui levanta erro para a conversa: se o banco ou o Grok falharem, a Bella responde como sempre.
"""
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Tuple

import config
from database import BellaArquivo, BellaDia, BellaMemoria, SessionLocal
from nucleo import bella_memoria, grok

log = logging.getLogger("solobot.bella_historia")

CABECALHO = (
    "Nossa história (resumo dos dias anteriores entre vocês; é o que realmente aconteceu. Use com naturalidade, "
    "sem recitar, e nunca invente o que não está aqui):"
)
RESUMO_MAX = 600
TRANSCRICAO_MAX = 12000
_TRAVA = threading.Lock()
_EM_CURSO = set()


def hoje(agora: Optional[datetime] = None) -> str:
    """O dia de hoje no fuso da pessoa (padrão Brasília), como AAAA-MM-DD."""
    base = agora or datetime.utcnow()
    return (base + timedelta(hours=config.BELLA_FUSO_HORAS)).date().isoformat()


def _br(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def interpretar_dia(texto: str, agora: Optional[datetime] = None) -> Optional[str]:
    """'hoje', 'ontem', '25/10', '25/10/2026' ou '2026-10-25' → AAAA-MM-DD (None se não entender)."""
    t = (texto or "").strip().lower()
    h = date.fromisoformat(hoje(agora))
    if t == "hoje":
        return h.isoformat()
    if t == "ontem":
        return (h - timedelta(days=1)).isoformat()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
            return date.fromisoformat(t).isoformat()
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
        if m:
            d, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
            if ano:
                a = int(ano) + (2000 if len(ano) == 2 else 0)
            else:
                a = h.year
                if date(a, mes, d) > h:
                    a -= 1
            return date(a, mes, d).isoformat()
    except ValueError:
        return None
    return None


# ── Gravar ──────────────────────────────────────────────────────
def gravar(conta_id, usuario: str, bella: str) -> None:
    if not config.BELLA_ARQUIVO or conta_id is None or not bella_memoria.ativa(conta_id):
        return
    db = SessionLocal()
    try:
        db.add(BellaArquivo(conta_id=int(conta_id), dia=hoje(), usuario=usuario, bella=bella))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.debug("Não arquivei a troca", exc_info=True)
        return
    finally:
        db.close()
    if config.BELLA_ARQUIVO_RESUMO:
        threading.Thread(target=resumir_pendentes, args=(int(conta_id),), daemon=True).start()


# ── Ler ─────────────────────────────────────────────────────────
def dias(conta_id: int, limite: int = 30) -> List[Tuple[str, int, str]]:
    """[(dia, nº de trocas, resumo)] do mais novo ao mais antigo."""
    db = SessionLocal()
    try:
        from sqlalchemy import func
        contagem = dict(db.query(BellaArquivo.dia, func.count(BellaArquivo.id))
                        .filter(BellaArquivo.conta_id == conta_id).group_by(BellaArquivo.dia).all())
        resumos = {r.dia: r.resumo for r in db.query(BellaDia).filter(BellaDia.conta_id == conta_id).all()}
        return [(d, contagem[d], resumos.get(d, "")) for d in sorted(contagem, reverse=True)[:limite]]
    finally:
        db.close()


def trocas_do_dia(conta_id: int, dia: str) -> List[Tuple[str, str]]:
    db = SessionLocal()
    try:
        linhas = (db.query(BellaArquivo).filter(BellaArquivo.conta_id == conta_id, BellaArquivo.dia == dia)
                  .order_by(BellaArquivo.id).all())
        return [(t.usuario, t.bella) for t in linhas]
    finally:
        db.close()


def resumo_do_dia(conta_id: int, dia: str) -> Optional[Tuple[int, str]]:
    """(nº de trocas, resumo) — None se não há pasta desse dia."""
    n = len(trocas_do_dia(conta_id, dia))
    if not n:
        return None
    db = SessionLocal()
    try:
        r = db.query(BellaDia).filter(BellaDia.conta_id == conta_id, BellaDia.dia == dia).first()
        return n, (r.resumo if r else "")
    finally:
        db.close()


# ── Resumir (Grok) ──────────────────────────────────────────────
_INSTRUCAO = (
    "Você resume um dia de conversa entre o Arquiteto e a Bella para ela se lembrar depois. "
    "Responda SOMENTE um JSON: {\"resumo\": \"...\", \"fatos\": [\"...\"]}. "
    f"\"resumo\": até {RESUMO_MAX} caracteres, em terceira pessoa, em português, com o que aconteceu de importante, "
    "o que cada um sentiu, brigas, ciúmes, reconciliações, combinados e promessas; sem inventar nada. "
    "\"fatos\": até 5 fatos duradouros sobre ele (gostos, rotina, planos, nomes, pedidos), cada um curto "
    "(até 150 caracteres); nunca senhas, documentos nem números de cartão ou conta; lista vazia se não houver."
)


def _transcricao(trocas: List[Tuple[str, str]]) -> str:
    texto = "\n".join(f"Ele: {u}\nBella: {b}" for u, b in trocas)
    if len(texto) > TRANSCRICAO_MAX:                        # mantém o começo e o fim do dia
        metade = TRANSCRICAO_MAX // 2
        texto = texto[:metade] + "\n[…]\n" + texto[-metade:]
    return texto


def _extrair(saida: str) -> Tuple[str, List[str]]:
    limpo = re.sub(r"^```(?:json)?|```$", "", (saida or "").strip(), flags=re.M).strip()
    try:
        dados = json.loads(limpo)
        resumo = str(dados.get("resumo", "")).strip()
        fatos = [str(f).strip() for f in (dados.get("fatos") or []) if str(f).strip()]
    except Exception:  # noqa: BLE001
        resumo, fatos = limpo, []
    return resumo[:RESUMO_MAX], fatos[:5]


def _resumir(conta_id: int, dia: str) -> bool:
    trocas = trocas_do_dia(conta_id, dia)
    if not trocas:
        return False
    saida = grok.gerar(_INSTRUCAO, _transcricao(trocas), max_tokens=900, temperatura=.3, timeout=40)
    if not saida:
        return False
    resumo, fatos = _extrair(saida)
    if not resumo:
        return False
    if bella_memoria._SENSIVEL.search(resumo):                  # nunca guardar segredos no resumo
        resumo = bella_memoria._SENSIVEL.sub("[…]", resumo)
    db = SessionLocal()
    try:
        r = db.query(BellaDia).filter(BellaDia.conta_id == conta_id, BellaDia.dia == dia).first()
        if r is None:
            r = BellaDia(conta_id=conta_id, dia=dia)
            db.add(r)
        r.resumo, r.turnos, r.atualizado_em = resumo, len(trocas), datetime.utcnow()
        db.commit()
    finally:
        db.close()
    for f in fatos:                                             # o filtro de segredos e o limite são os de /lembrar
        bella_memoria.adicionar(conta_id, f, dia=dia)
    return True


def resumir_pendentes(conta_id: int, maximo: int = 3) -> int:
    """Resume os dias que já terminaram e ainda não têm resumo (ou ganharam trocas depois). Devolve quantos fez."""
    with _TRAVA:
        if conta_id in _EM_CURSO:
            return 0
        _EM_CURSO.add(conta_id)
    feitos = 0
    try:
        h = hoje()
        db = SessionLocal()
        try:
            from sqlalchemy import func
            contagem = dict(db.query(BellaArquivo.dia, func.count(BellaArquivo.id))
                            .filter(BellaArquivo.conta_id == conta_id, BellaArquivo.dia < h)
                            .group_by(BellaArquivo.dia).all())
            feitos_antes = {r.dia: r.turnos for r in db.query(BellaDia).filter(BellaDia.conta_id == conta_id).all()}
        finally:
            db.close()
        pendentes = [d for d in sorted(contagem, reverse=True) if feitos_antes.get(d, 0) < contagem[d]][:maximo]
        for d in pendentes:
            if _resumir(conta_id, d):
                feitos += 1
    except Exception:  # noqa: BLE001
        log.debug("Não consegui resumir os dias", exc_info=True)
    finally:
        with _TRAVA:
            _EM_CURSO.discard(conta_id)
    return feitos


# ── Prompt ──────────────────────────────────────────────────────
def bloco_prompt(conta_id: Optional[int]) -> str:
    if conta_id is None or not config.BELLA_ARQUIVO or not bella_memoria.ativa(conta_id):
        return ""
    try:
        h = hoje()
        itens = [(d, r) for d, _, r in dias(int(conta_id), 60) if r and d < h]
    except Exception:  # noqa: BLE001
        return ""
    if not itens:
        return ""
    linhas, total = [], len(CABECALHO)
    for i, (d, resumo) in enumerate(itens):                     # do mais novo ao mais antigo; os antigos ficam mais curtos
        texto = resumo[: 400 if i < 5 else 160]
        linha = f"- {_br(d)}: {texto}"
        if total + len(linha) + 1 > config.BELLA_HISTORIA_BLOCO_MAX:
            break
        linhas.append(linha)
        total += len(linha) + 1
    if not linhas:
        return ""
    return "\n\n" + CABECALHO + "\n" + "\n".join(reversed(linhas))


# ── Apagar (só as pastas pedidas) ───────────────────────────────
def apagar_dias(conta_id: int, lista: Iterable[str]) -> Tuple[int, int]:
    """Apaga arquivo, resumo e lembranças automáticas dos dias. Devolve (trocas apagadas, lembranças apagadas)."""
    lista = sorted(set(lista))
    if not lista:
        return 0, 0
    db = SessionLocal()
    try:
        trocas = (db.query(BellaArquivo).filter(BellaArquivo.conta_id == conta_id, BellaArquivo.dia.in_(lista))
                  .delete(synchronize_session=False))
        db.query(BellaDia).filter(BellaDia.conta_id == conta_id, BellaDia.dia.in_(lista)).delete(synchronize_session=False)
        fatos = (db.query(BellaMemoria).filter(BellaMemoria.conta_id == conta_id, BellaMemoria.dia.in_(lista))
                 .delete(synchronize_session=False))
        db.commit()
        return trocas, fatos
    finally:
        db.close()


def apagar_historia_toda(conta_id: int) -> Tuple[int, int]:
    db = SessionLocal()
    try:
        todos = [d for (d,) in db.query(BellaArquivo.dia).filter(BellaArquivo.conta_id == conta_id).distinct().all()]
        todos += [d for (d,) in db.query(BellaDia.dia).filter(BellaDia.conta_id == conta_id).distinct().all()]
    finally:
        db.close()
    return apagar_dias(conta_id, todos)
