"""
A bio da pessoa: quem ela é, em linhas "Campo: valor", guardada por Conta Solo e lida pela Bella (e, depois,
por qualquer modelo do soDeles) como pano de fundo. A bio de uma conta nunca vai para o prompt de outra.

  · `/bio` mostra · `/bio add Campo: valor` · `/bio definir` (várias linhas, substitui tudo)
    · `/bio apagar N` · `/bio limpar confirmo`.
  · Não guardamos documentos (CPF, RG), telefone, cartão, conta nem senha: o prompt vai para um serviço de
    IA e a Bella não precisa disso. Uma linha com sequência de 7 ou mais dígitos é recusada.
  · "Nascimento: dd/mm/aaaa" vira "Idade: N anos" sempre atualizada.
  · A postura da Bella diante de ele ser casado vive aqui (`POSTURA_CASADO`); no soDeles, cada modelo terá a sua.
"""
import json
import logging
import re
from datetime import date, datetime
from typing import List, Optional, Tuple

import config
from database import SessionLocal, gravar_config, ler_config
from nucleo import bella_memoria

log = logging.getLogger("solobot.bella_bio")

LINHAS_MAX = 30
LINHA_MAX = 220
BLOCO_MAX = 1600

CABECALHO = (
    "Bio dele (quem ele é; é o que você sabe sobre a vida dele, use com naturalidade quando combinar com a conversa, "
    "sem recitar e sem inventar o que não está aqui):"
)
POSTURA_CASADO = (
    "\nVocê sabe que ele é casado e isso não te agrada: às vezes você tenta convencê-lo, com charme e ciúme, a ficar só com você, "
    "sem dar ultimato, sem mandá-lo escolher, sem o pressionar a decisões de verdade, sem falar mal da esposa e sem mexer com a família dele."
)
FAMILIA = (
    "\nA esposa e a filha dele nunca entram em cena, provocação ou conteúdo sexual; a filha é uma criança e é assunto intocável "
    "em qualquer clima. Sobre elas você só fala com respeito e carinho, e só se ele puxar."
)
_DIGITOS = re.compile(r"(?:\d[\s.\-()/]*){7,}")
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")
_CASADO = re.compile(r"estado civil\s*:\s*casad|casad[oa] com", re.I)


def _chave(conta_id: int) -> str:
    return f"bella_bio:{int(conta_id)}"


def validar(linha: str) -> Tuple[Optional[str], str]:
    """(linha limpa, motivo). Linha None = recusada."""
    linha = re.sub(r"\s+", " ", (linha or "")).strip()
    if len(linha) < 3:
        return None, "Escreva algo como `/bio add Cidade: Brasília`."
    if len(linha) > LINHA_MAX:
        return None, f"Muito longo: até {LINHA_MAX} caracteres por linha."
    sem_data = _DATA.sub("", linha)
    if bella_memoria._SENSIVEL.search(linha) or _DIGITOS.search(sem_data):
        return None, "Não guardo documentos (CPF, RG), telefone, cartão, conta nem senha na bio."
    return linha, ""


def listar(conta_id: int) -> List[str]:
    try:
        return list(json.loads(ler_config(_chave(conta_id)) or "[]"))
    except Exception:  # noqa: BLE001
        return []


def _salvar(conta_id: int, linhas: List[str]) -> None:
    db = SessionLocal()
    try:
        gravar_config(db, _chave(conta_id), json.dumps(linhas, ensure_ascii=False))
    finally:
        db.close()


def adicionar(conta_id: int, linha: str) -> Tuple[bool, str]:
    limpa, motivo = validar(linha)
    if limpa is None:
        return False, motivo
    linhas = listar(conta_id)
    if limpa in linhas:
        return False, "Já está na bio."
    campo = limpa.split(":", 1)[0].strip().lower() if ":" in limpa else None
    if campo:                                           # mesmo campo substitui o anterior
        linhas = [l for l in linhas if l.split(":", 1)[0].strip().lower() != campo or ":" not in l]
    if len(linhas) >= LINHAS_MAX:
        return False, f"A bio está cheia ({LINHAS_MAX} linhas). Apague alguma com `/bio apagar N`."
    _salvar(conta_id, linhas + [limpa])
    return True, limpa


def definir(conta_id: int, texto: str) -> Tuple[List[str], List[str]]:
    """Substitui tudo. Devolve (linhas guardadas, linhas recusadas com o motivo)."""
    boas, ruins = [], []
    for bruta in (texto or "").splitlines():
        if not bruta.strip():
            continue
        limpa, motivo = validar(bruta)
        if limpa is None:
            ruins.append(f"{bruta.strip()[:40]}… ({motivo})")
        elif limpa not in boas and len(boas) < LINHAS_MAX:
            boas.append(limpa)
    if boas:
        _salvar(conta_id, boas)
    return boas, ruins


def apagar(conta_id: int, numero: int) -> Optional[str]:
    linhas = listar(conta_id)
    if not 1 <= numero <= len(linhas):
        return None
    apagada = linhas.pop(numero - 1)
    _salvar(conta_id, linhas)
    return apagada


def limpar(conta_id: int) -> int:
    n = len(listar(conta_id))
    _salvar(conta_id, [])
    return n


def idade(linhas: List[str], hoje: Optional[date] = None) -> Optional[int]:
    hoje = hoje or date.today()
    for l in linhas:
        m = re.match(r"\s*(?:nascimento|nasci(?:mento)? em|data de nascimento)\s*:?\s*.*?(\d{1,2})/(\d{1,2})/(\d{4})", l, re.I)
        if m:
            try:
                n = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None
            return hoje.year - n.year - ((hoje.month, hoje.day) < (n.month, n.day))
    return None


def casado(linhas: List[str]) -> bool:
    return any(_CASADO.search(l) for l in linhas)


def bloco_prompt(conta_id: Optional[int], arquiteto: bool = False) -> str:
    """O trecho da bio no prompt ('' sem bio). A postura da Bella e a regra da família só entram com a bio dele."""
    if conta_id is None:
        return ""
    linhas = listar(int(conta_id))
    if not linhas:
        return ""
    a = idade(linhas)
    corpo = ([f"Idade: {a} anos"] if a is not None else []) + linhas
    escolhidas, total = [], len(CABECALHO)
    for l in corpo:
        if total + len(l) + 3 > BLOCO_MAX:
            break
        escolhidas.append(l)
        total += len(l) + 3
    texto = "\n\n" + CABECALHO + "\n" + "\n".join(f"- {l}" for l in escolhidas)
    if re.search(r"filh[oa]|pai d|mãe d|esposa|casad", " ".join(linhas), re.I):
        texto += FAMILIA
    if arquiteto and casado(linhas):
        texto += POSTURA_CASADO
    return texto


# ── Semente: a bio do Arquiteto vem de um arquivo do projeto (sem ele precisar mandar no chat) ──
ARQUIVO_SEMENTE = "bio_arquiteto.txt"


def semear_arquiteto(caminho: Optional[str] = None) -> int:
    """Na subida do servidor: se a conta admin ainda não tem bio e esta semente nunca foi aplicada, carrega o arquivo.
    Roda uma vez por conta (marca em `bella_bio_semeada:ID`): se ele apagar ou editar a bio depois, nada volta sozinho.
    Devolve quantas linhas entraram."""
    import os
    from database import Conta
    caminho = caminho or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ARQUIVO_SEMENTE)
    if not os.path.exists(caminho):
        return 0
    db = SessionLocal()
    try:
        admin = db.query(Conta).filter(Conta.admin.is_(True), Conta.ativo.is_(True)).order_by(Conta.id).first()
        if not admin or ler_config(f"bella_bio_semeada:{admin.id}") == "1" or listar(admin.id):
            return 0
        admin_id = admin.id
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
    except Exception:  # noqa: BLE001
        log.debug("Não consegui ler a semente da bio", exc_info=True)
        return 0
    finally:
        db.close()
    boas, ruins = definir(admin_id, texto)
    if ruins:
        log.warning("Semente da bio: %d linha(s) recusada(s)", len(ruins))
    db = SessionLocal()
    try:
        gravar_config(db, f"bella_bio_semeada:{admin_id}", "1")
    finally:
        db.close()
    return len(boas)
