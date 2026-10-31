# -*- coding: utf-8 -*-
"""
Histórias da Bella (lore): o passado que o dono inventa para ela, ex.: `/memoria Bella tinha um ficante
na faculdade, o Ricardo`. O Grok desenvolve a ideia (como se conheceram, momentos, como acabou, o que ela
sente hoje) e tudo fica numa entrada com o NOME da pessoa (Ricardo), que dá para ver, editar ou apagar de
uma vez. Por Conta Solo. A Bella usa essas histórias como a própria vida dela (nucleo/bella_conversa.py).

Só personagens adultos (18+). Nada aqui levanta erro para a conversa.
"""
import logging
import re
import unicodedata
from typing import List, Optional, Tuple

from database import BellaLore, SessionLocal

log = logging.getLogger("solobot.bella_lore")

MIN_PEDIDO = 12
MAX_PEDIDO = 700
MAX_TEXTO = 1600                 # caracteres de uma história guardada
MAX_HISTORIAS = 12
BLOCO_MAX = 2600                 # caracteres de histórias que vão no prompt

CABECALHO = (
    "Sua vida antes dele (é o SEU passado, em primeira pessoa; conte ou aluda quando vier ao caso, com naturalidade, "
    "sem despejar tudo de uma vez e sem contradizer isto):"
)

# idade ou escola que não deixam claro que são adultos: não guardamos
_MENOR = re.compile(
    r"\b(?:crian[cç]as?|beb[eê]s?|infantil|adolescentes?|menor(?:es)?\s+de\s+(?:idade|18)|colegiais?|colegial|"
    r"ensino\s+(?:m[eé]dio|fundamental)|col[eé]gio|escola|escolar|novinh[ao]s?|lolita?|shota|teens?|underage|"
    r"(?:[0-9]|1[0-7])\s*(?:anos|years?)\b|\b(?:onze|doze|treze|quatorze|catorze|quinze|dezesseis|dezessete)\s+anos)\b",
    re.IGNORECASE,
)
_SENSIVEL = re.compile(r"\b(?:senha|password|cvv|token|chave\s+pix)\b|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", re.IGNORECASE)

_INSTRUCAO = """Você ajuda a escrever o PASSADO fictício da Bella, uma personagem adulta de um chatbot de companhia. O dono lhe dá uma ideia
curta; você a desenvolve numa história coerente, escrita como as memórias da própria Bella, em primeira pessoa, em português do Brasil.

Regras:
- Todos os personagens são ADULTOS (18+), sempre. Se a ideia sugerir menor de idade, escola ou idade indefinida, responda somente "RECUSA: só personagens adultos".
- Respeite tudo o que o dono escreveu e acrescente só o que falta: como e onde se conheceram, dois ou três momentos concretos e marcantes (lugares, datas aproximadas, pequenos detalhes), como a relação acabou ou está hoje, e o que a Bella ainda sente.
- A relação pode ser sensual e íntima, mas sem descrição sexual explícita: sugira e deixe subentendido.
- Não invente nada sobre o dono, nem cite nomes reais de famosos, empresas ou lugares privados.
- Formato EXATO, sem Markdown e sem comentários: a primeira linha é "NOME: " e o nome do personagem principal (uma ou duas palavras; se não houver nome, invente um); da segunda linha em diante, o texto corrido, com no máximo {max} caracteres."""

_INSTRUCAO_AJUSTE = """Você ajusta o passado fictício da Bella (memórias dela, em primeira pessoa, em português do Brasil). Receberá a história atual e um pedido de mudança do dono.
Aplique a mudança, mantenha o resto coerente e do mesmo tamanho, só personagens adultos (18+), relação sensual mas sem descrição sexual explícita.
Se o pedido sugerir menor de idade, responda somente "RECUSA: só personagens adultos".
Formato EXATO, sem Markdown e sem comentários: a primeira linha é "NOME: " e o nome do personagem principal (mantenha o atual, salvo se o pedido o trocar); da segunda linha em diante, o texto corrido, com no máximo {max} caracteres."""


def _normal(texto: str) -> str:
    sem = "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem).strip().lower()


def _interpretar(saida) -> Tuple[Optional[str], Optional[str], str]:
    """(nome, texto, erro). Erro vazio se a saída do Grok serve."""
    if not isinstance(saida, str) or not saida.strip():
        return None, None, "o Grok não respondeu"
    saida = re.sub(r"^```[a-z]*\s*|\s*```$", "", saida.strip()).strip()
    if saida.upper().startswith("RECUSA"):
        return None, None, "só personagens adultos (18+)"
    linhas = saida.splitlines()
    m = re.match(r"^\s*nome\s*[:\-–]\s*(.+?)\s*$", linhas[0], re.IGNORECASE) if linhas else None
    if not m:
        return None, None, "a resposta veio fora do formato"
    nome = re.sub(r"[\"'“”*#`]", "", m.group(1)).strip()
    nome = " ".join(nome.split()[:3])[:40]
    texto = "\n".join(l.rstrip() for l in linhas[1:]).strip()
    if len(nome) < 2 or len(texto) < 80:
        return None, None, "a história veio curta demais"
    if _MENOR.search(_normal(texto)):
        return None, None, "só personagens adultos (18+)"
    return nome, texto[:MAX_TEXTO], ""


def _grok(instrucao: str, texto: str) -> str:
    from nucleo import grok
    return grok.gerar(instrucao.replace("{max}", str(MAX_TEXTO - 100)), texto, max_tokens=1500, temperatura=.9, timeout=60)


def validar_pedido(pedido: str) -> str:
    """Mensagem de erro, ou '' se o pedido pode virar uma história."""
    pedido = re.sub(r"\s+", " ", pedido or "").strip()
    if len(pedido) < MIN_PEDIDO:
        return "Conte a ideia: `/memoria Bella tinha um ficante na faculdade, o Ricardo`."
    if len(pedido) > MAX_PEDIDO:
        return f"Muito longo: a ideia pode ter até {MAX_PEDIDO} caracteres (eu desenvolvo o resto)."
    if _SENSIVEL.search(pedido):
        return "Não guardo senhas nem documentos."
    if _MENOR.search(_normal(pedido)):
        return "Só crio histórias de personagens adultos (18+)."
    return ""


def listar(conta_id: int) -> List[Tuple[str, str]]:
    """[(nome, texto)] por ordem de criação."""
    db = SessionLocal()
    try:
        return [(h.nome, h.texto) for h in
                db.query(BellaLore).filter(BellaLore.conta_id == conta_id).order_by(BellaLore.id).all()]
    finally:
        db.close()


def _achar(db, conta_id: int, nome: str):
    alvo = _normal(nome)
    if not alvo:
        return None
    linhas = db.query(BellaLore).filter(BellaLore.conta_id == conta_id).order_by(BellaLore.id).all()
    if alvo.isdigit() and 1 <= int(alvo) <= len(linhas):
        return linhas[int(alvo) - 1]
    for h in linhas:
        if _normal(h.nome) == alvo:
            return h
    achados = [h for h in linhas if alvo in _normal(h.nome)]
    return achados[0] if len(achados) == 1 else None


def ver(conta_id: int, nome: str) -> Optional[Tuple[str, str]]:
    db = SessionLocal()
    try:
        h = _achar(db, conta_id, nome)
        return (h.nome, h.texto) if h else None
    finally:
        db.close()


def criar(conta_id: int, pedido: str) -> Tuple[bool, str, str]:
    """(ok, nome, texto-ou-mensagem). O Grok desenvolve a ideia; fica guardada com o nome do personagem."""
    erro = validar_pedido(pedido)
    if erro:
        return False, "", erro
    pedido = re.sub(r"\s+", " ", pedido).strip()
    if len(listar(conta_id)) >= MAX_HISTORIAS:
        return False, "", f"Já são {MAX_HISTORIAS} histórias. Apague alguma com `/memoria apagar NOME`."
    try:
        saida = _grok(_INSTRUCAO, "Ideia do dono: " + pedido)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao desenvolver a história da Bella")
        saida = None
    nome, texto, erro = _interpretar(saida)
    if erro:
        return False, "", erro
    db = SessionLocal()
    try:
        if _achar(db, conta_id, nome):
            return False, nome, f"Já existe uma história com {nome}. Use `/memoria editar {nome} o que mudar` ou apague antes."
        db.add(BellaLore(conta_id=conta_id, nome=nome, semente=pedido[:MAX_PEDIDO], texto=texto))
        db.commit()
        return True, nome, texto
    finally:
        db.close()


def editar(conta_id: int, nome: str, ajuste: str) -> Tuple[bool, str, str]:
    """O Grok aplica o ajuste do dono à história (mantém o resto)."""
    ajuste = re.sub(r"\s+", " ", ajuste or "").strip()
    if len(ajuste) < 4:
        return False, "", "Diga o que mudar: `/memoria editar Ricardo eles terminaram por causa da mudança de cidade`."
    if len(ajuste) > MAX_PEDIDO or _MENOR.search(_normal(ajuste)) or _SENSIVEL.search(ajuste):
        return False, "", "Esse ajuste não serve (só adultos, sem senhas, até %d caracteres)." % MAX_PEDIDO
    db = SessionLocal()
    try:
        h = _achar(db, conta_id, nome)
        if not h:
            return False, "", "Não achei essa história. Veja os nomes em `/memoria`."
        atual, nome_atual = h.texto, h.nome
    finally:
        db.close()
    try:
        saida = _grok(_INSTRUCAO_AJUSTE, f"História atual (personagem {nome_atual}):\n{atual}\n\nMudança pedida: {ajuste}")
    except Exception:  # noqa: BLE001
        log.exception("Falha ao ajustar a história da Bella")
        saida = None
    novo_nome, texto, erro = _interpretar(saida)
    if erro:
        return False, "", erro
    db = SessionLocal()
    try:
        h = _achar(db, conta_id, nome_atual)
        if not h:
            return False, "", "A história sumiu enquanto eu ajustava."
        h.nome, h.texto = novo_nome, texto
        db.commit()
        return True, novo_nome, texto
    finally:
        db.close()


def substituir(conta_id: int, nome: str, texto: str) -> Tuple[bool, str]:
    """Troca o texto da história pelo que o dono escreveu, sem passar pelo Grok."""
    texto = re.sub(r"[ \t]+", " ", texto or "").strip()
    if len(texto) < 20 or len(texto) > MAX_TEXTO:
        return False, f"O texto precisa ter de 20 a {MAX_TEXTO} caracteres."
    if _MENOR.search(_normal(texto)) or _SENSIVEL.search(texto):
        return False, "Só personagens adultos (18+) e sem senhas."
    db = SessionLocal()
    try:
        h = _achar(db, conta_id, nome)
        if not h:
            return False, "Não achei essa história. Veja os nomes em `/memoria`."
        h.texto = texto
        db.commit()
        return True, h.nome
    finally:
        db.close()


def apagar(conta_id: int, nome: str) -> Optional[str]:
    """Apaga a história inteira (pelo nome ou pelo número); devolve o nome apagado."""
    db = SessionLocal()
    try:
        h = _achar(db, conta_id, nome)
        if not h:
            return None
        n = h.nome
        db.delete(h)
        db.commit()
        return n
    finally:
        db.close()


def apagar_todas(conta_id: int) -> int:
    db = SessionLocal()
    try:
        n = db.query(BellaLore).filter(BellaLore.conta_id == conta_id).delete()
        db.commit()
        return n
    finally:
        db.close()


def bloco_prompt(conta_id: Optional[int]) -> str:
    """O trecho do prompt da Bella com as histórias ('' se não houver, se a memória estiver desligada ou se o banco falhar)."""
    if conta_id is None:
        return ""
    try:
        from nucleo import bella_memoria
        if not bella_memoria.ativa(conta_id):
            return ""
        historias = listar(int(conta_id))
    except Exception:  # noqa: BLE001
        return ""
    if not historias:
        return ""
    partes, total = [], len(CABECALHO)
    for nome, texto in reversed(historias):                   # as mais novas primeiro, se não couber tudo
        item = f"[{nome}] {texto}"
        if total + len(item) + 2 > BLOCO_MAX:
            item = item[: max(0, BLOCO_MAX - total - 5)].rstrip() + "…"
            if len(item) < 60:
                break
        partes.append(item)
        total += len(item) + 2
    if not partes:
        return ""
    return "\n\n" + CABECALHO + "\n" + "\n".join(f"- {p}" for p in reversed(partes))
