# -*- coding: utf-8 -*-
"""
Os contatos de envio de áudio (a lista de "Enviar áudio" da Administração).

As regras ficam aqui, sem HTTP, para a tela do painel e o `/salvarcontato`
do WhatsApp/Telegram gravarem do mesmo jeito: mesmo formato de número,
mesmo limite, sem número repetido.
"""
import re
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import ContatoAudio

LIMITE = 200
MAX_NOME = 80
DDI_PADRAO = "55"          # número de agenda sem DDI (ex.: "(11) 99999-9999") é do Brasil


class NumeroInvalido(ValueError):
    pass


def normalizar(numero: str) -> str:
    """Só os dígitos, com DDI: "+55 (11) 99999-9999" → "5511999999999"."""
    numero = numero or ""
    if not re.fullmatch(r"[+0-9() .-]+", numero):
        raise NumeroInvalido("Informe somente o número com DDI e DDD, sem links ou grupos.")
    numero = re.sub(r"[+() .-]", "", numero)
    if not re.fullmatch(r"[1-9][0-9]{7,14}", numero):
        raise NumeroInvalido("Informe um número internacional com DDI e DDD, por exemplo +55 11 99999-9999.")
    return numero


def numero_de_contato(cru: str) -> str:
    """Como `normalizar`, mas aceita o número como está na agenda: sem DDI, vale o do Brasil."""
    cru = (cru or "").strip()
    if not cru.startswith("+"):
        digitos = re.sub(r"\D", "", cru).lstrip("0")
        if 10 <= len(digitos) <= 11 and re.fullmatch(r"[+0-9() .-]+", cru):
            cru = "+" + DDI_PADRAO + digitos
    return normalizar(cru)


def nome_valido(nome: str) -> Optional[str]:
    nome = re.sub(r"\s+", " ", (nome or "").replace("\r", " ").replace("\n", " ")).strip()[:MAX_NOME].strip()
    if not nome or any(ord(c) < 32 for c in nome):
        return None
    return nome


def _desescapar(valor: str) -> str:
    return re.sub(r"\\([,;:\\])", r"\1", valor).replace("\\n", " ").replace("\\N", " ").strip()


def do_vcard(vcard: str, nome_exibido: str = "") -> Tuple[str, str]:
    """(nome, número) de um cartão de contato do WhatsApp.

    O WhatsApp marca o número que tem conta com `waid=` (já com DDI); sem ele,
    vale o primeiro TEL, do jeito que está na agenda de quem mandou.
    """
    linhas, atual = [], ""
    for linha in (vcard or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if linha[:1] in (" ", "\t") and atual:          # linha dobrada (RFC 6350)
            atual += linha[1:]
            continue
        if atual:
            linhas.append(atual)
        atual = linha
    if atual:
        linhas.append(atual)
    fn = n = ""
    com_whats = tel = ""
    for linha in linhas:
        chave, _, valor = linha.partition(":")
        campo = chave.split(";")[0].split(".")[-1].strip().upper()     # "item1.TEL;waid=…" → TEL
        if campo == "FN" and not fn:
            fn = _desescapar(valor)
        elif campo == "N" and not n:
            partes = [_desescapar(p) for p in re.split(r"(?<!\\);", valor)]
            n = " ".join(p for p in (partes[1:2] + partes[0:1]) if p)
        elif campo == "TEL":
            m = re.search(r"waid=(\d+)", chave, re.IGNORECASE)
            if m and not com_whats:
                com_whats = "+" + m.group(1)
            elif not tel:
                tel = valor.strip()
    nome = (nome_exibido or "").strip() or fn or n
    return nome, com_whats or tel


def salvar(db: Session, conta_id: int, nome: str, numero: str) -> Tuple[str, Optional[ContatoAudio]]:
    """("salvo" | "repetido" | "limite", contato). O número já vem normalizado."""
    existente = db.query(ContatoAudio).filter_by(conta_id=conta_id, numero=numero).first()
    if existente:
        return "repetido", existente
    if db.query(ContatoAudio).filter_by(conta_id=conta_id).count() >= LIMITE:
        return "limite", None
    c = ContatoAudio(conta_id=conta_id, nome=nome, numero=numero)
    db.add(c)
    try:
        db.commit()
    except IntegrityError:          # o mesmo número chegou ao mesmo tempo por outro caminho
        db.rollback()
        return "repetido", db.query(ContatoAudio).filter_by(conta_id=conta_id, numero=numero).first()
    db.refresh(c)
    return "salvo", c
