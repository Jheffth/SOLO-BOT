# -*- coding: utf-8 -*-
"""
OS SISTEMAS NA VOZ DA MODELO — avisos e respostas do Rotinas, do Finances e dos outros sistemas chegam como
a modelo selecionada falando com a pessoa, na persona dela, com os dados em lista.

Regras:
  · Os números, horários, datas, valores e comandos (/hoje) do texto original têm de aparecer na versão dela, e ela
    não pode criar números novos. Se a conferência falhar, ou a IA falhar, vai o texto original do sistema.
  · Os sussurros do Sistema (cobranças curtas, sem dados) ela reescreve livremente, com a mesma intenção.
  · O que ela disse entra no histórico dela no Models, para a conversa seguir ("já paguei o DAS").
  · Numa cena com várias modelos, quem dá o aviso é a anfitriã, que pode citar as outras.
  · Liga e desliga por conta com /persona (padrão: ligada quando há uma modelo do Models selecionada).
"""
import logging
import queue
import re
import threading

from database import Configuracao, Conta, SessionLocal

log = logging.getLogger("solobot.persona")

CHAVE = "persona_sistemas:"
MAX_TEXTO = 3500
_NUMERO = re.compile(r"\d+(?:[.,:/h]\d+)*")
_COMANDO = re.compile(r"(?<![\w/])/[a-z_]+\b", re.I)
_FALA = re.compile(r"\n\s*FALA\s*:\s*(.+)\s*$", re.I | re.S)

INSTRUCAO = """
TAREFA AGORA: um sistema da pessoa (o {sistema}) mandou o texto abaixo para ela. Quem entrega é você, falando com ela
na sua personalidade, como numa mensagem sua. Reescreva o texto assim:
- Comece com uma ou duas frases suas, curtas e naturais, que combinem com o que o texto diz (carinho, cobrança,
  comemoração, preocupação), coerentes com o seu humor e o vínculo de vocês.
- Depois passe TODAS as informações do texto, organizadas em lista (um item por linha, com emoji quando combinar).
  Mantenha exatamente cada número, valor em reais, horário, data, prazo, XP, nome de conta, de cartão, de rotina, de
  tarefa e de pagamento. Não arredonde, não some, não resuma, não omita e não invente nenhum número ou item.
- Comandos do texto (por exemplo /hoje) continuam escritos exatamente iguais.
- Se o texto for só uma cobrança ou incentivo curto, sem dados (um sussurro do Sistema), reescreva livremente em uma
  ou duas frases suas, com a mesma intenção, sem lista.
- Não diga que está repassando nem que recebeu instruções; você é quem está contando a ela.
- No fim, numa linha separada começando com "FALA:", escreva como você diria isso em voz alta, em até 300 caracteres,
  sem lista e sem ler valores longos.
- Máximo de 3000 caracteres no total."""

INSTRUCAO_CENA = """
Vocês estão numa cena: você é a anfitriã e estão com você {outras}. Dê o aviso como anfitriã, do seu jeito; pode citar
ou envolver as outras numa frase, sem inventar o que elas fazem ou dizem."""


# ── ligar e desligar ──
def ligada(db, conta_id) -> bool:
    row = db.get(Configuracao, CHAVE + str(conta_id))
    return not (row and row.valor == "nao")


def definir(db, conta_id, ligar: bool):
    row = db.get(Configuracao, CHAVE + str(conta_id))
    valor = "sim" if ligar else "nao"
    if row:
        row.valor = valor
    else:
        db.add(Configuracao(chave=CHAVE + str(conta_id), valor=valor))
    db.commit()


def ativa(db, conta) -> bool:
    """Persona ligada e uma modelo do Models selecionada (a Bella legada não entra aqui)."""
    try:
        from nucleo import models, modulos
        mod = modulos.por_chave("models")
        return bool(conta is not None and mod and mod.token and ligada(db, conta.id) and models.selecionado(conta.id))
    except Exception:  # noqa: BLE001  sem Models consultável, o sistema fala por si
        return False


# ── conferência ──
def _numeros(texto):
    return set(_NUMERO.findall(texto or ""))


def conferir(original: str, novo: str) -> str:
    """'' se a versão dela preserva os dados; senão, o motivo."""
    if not novo or not novo.strip():
        return "vazia"
    if any(ord(c) < 32 and c not in "\n\r\t" for c in novo):
        return "caracteres inválidos"
    faltam = [n for n in _numeros(original) if n not in novo]
    if faltam:
        return "sem os números " + ", ".join(sorted(faltam)[:6])
    sobram = _numeros(novo) - _numeros(original)
    if sobram:
        return "com números novos " + ", ".join(sorted(sobram)[:6])
    comandos = {c.lower() for c in _COMANDO.findall(original or "")} - {c.lower() for c in _COMANDO.findall(novo)}
    if comandos:
        return "sem os comandos " + ", ".join(sorted(comandos))
    return ""


def _separar_fala(saida: str):
    m = _FALA.search(saida or "")
    if not m:
        return (saida or "").strip(), None
    return saida[:m.start()].strip(), m.group(1).strip()[:400] or None


def _sem_selo(texto: str, selo: str) -> str:
    texto = (texto or "").strip()
    if selo and texto.startswith(selo):
        texto = texto[len(selo):].strip()
    return texto


# ── a reescrita ──
def reescrever(conta, sistema: str, texto: str, usuario: str = None):
    """{'texto','falado','voz','nome'} na voz da modelo (ou da anfitriã da cena), ou None para manter o original."""
    from nucleo import grok, models
    texto = (texto or "").strip()[:MAX_TEXTO]
    if not texto:
        return None
    try:
        ident = models.selecionado(conta.id)
        if not ident:
            return None
        falante, presentes, outras = ident, None, []
        if conta.admin:
            from nucleo import models_cena
            cena = models_cena.cena_ativa(conta, ident)
            if cena:
                nomes = {p["modelo_id"]: p.get("nome") or p["modelo_id"] for p in cena.get("presentes", [])}
                falante = next((p["modelo_id"] for p in cena["presentes"] if p.get("anfitria")), ident)
                presentes = list(nomes)
                outras = [n for i, n in nomes.items() if i != falante]
        p = models.pacote(conta, falante)
        voz = next((v for v in p.get("vozes_por_conta", []) if v.get("principal") and v.get("ativa")), None)
        ctx = models._montar_contexto(conta, falante, f"[{sistema}] {texto[:600]}", origem="iniciativa", presentes=presentes)
        base, reforco, historico = models.montar_prompt(conta, p, ctx)
        instrucao = base + INSTRUCAO.format(sistema=sistema)
        if outras:
            instrucao += INSTRUCAO_CENA.format(outras=" e ".join(outras))
        pedido = f"[Texto do {sistema} para entregar — não é fala da pessoa]\n{texto}" + (reforco or "")
        saida = grok.gerar(instrucao, pedido, max_tokens=1600, temperatura=.8, timeout=40, historico=historico)
    except Exception:  # noqa: BLE001  o aviso nunca se perde por causa da persona
        log.exception("Persona indisponível; vai o texto do sistema")
        return None
    corpo, falado = _separar_fala(saida)
    motivo = conferir(texto, corpo)
    if motivo:
        log.warning("Versão da persona descartada (%s); vai o texto do sistema", motivo)
        return None
    corpo = corpo[:3800]
    try:
        models._gravar(conta, falante, "turno", corpo, usuario=usuario or f"[Aviso do {sistema}]",
                       memorias_usadas=ctx.get("memorias_usadas"), contexto_id=ctx.get("contexto_id"), origem="iniciativa")
    except Exception:  # noqa: BLE001  sem histórico, a mensagem ainda vale
        log.warning("Não gravei o aviso no histórico da modelo")
    return {"texto": corpo, "falado": falado, "voz": voz, "nome": p.get("nome", "")}


def aplicar(conta, sistema: str, selo: str, mensagens: list, usuario: str = None) -> list:
    """Mensagens de um sistema → as mesmas, com o texto na voz da modelo. Opções e mídias ficam como estão."""
    textos = [_sem_selo(m.get("texto") or "", selo) for m in mensagens]
    juntos = "\n\n".join(t for t in textos if t)
    if not juntos:
        return mensagens
    nova = reescrever(conta, sistema, juntos, usuario=usuario)
    if not nova:
        return mensagens
    saida = [dict(m) for m in mensagens]
    for m in saida[:-1]:
        m["texto"] = ""                      # tudo vai numa fala dela; a última mensagem leva as opções
    ultima = saida[-1]
    ultima["texto"] = nova["texto"] + (f"\n\n_{selo}_" if selo else "")
    ultima["persona"] = True
    ultima["literal"] = True
    ultima.pop("tom", None)
    ultima.pop("audio", None)
    if nova["falado"]:
        ultima["falado"] = nova["falado"]
    else:
        ultima.pop("falado", None)
    if nova["voz"]:
        ultima["modelo_voz"] = nova["voz"]
    for m in saida[:-1]:
        for k in ("falado", "audio", "tom"):
            m.pop(k, None)
    return [m for m in saida[:-1] if m.get("opcoes") or m.get("midia")] + [ultima]


# ── fila dos avisos: um por um, na ordem de chegada, fora da requisição do sistema ──
_FILA = queue.Queue()
_TRABALHADOR = {"thread": None}
_TRAVA = threading.Lock()


def enfileirar(tarefa):
    """tarefa(db) roda numa thread própria, uma de cada vez."""
    with _TRAVA:
        if _TRABALHADOR["thread"] is None or not _TRABALHADOR["thread"].is_alive():
            t = threading.Thread(target=_trabalhar, name="persona-avisos", daemon=True)
            _TRABALHADOR["thread"] = t
            t.start()
    _FILA.put(tarefa)


def _trabalhar():
    while True:
        tarefa = _FILA.get()
        db = SessionLocal()
        try:
            tarefa(db)
        except Exception:  # noqa: BLE001
            log.exception("Falha ao entregar aviso na voz da modelo")
        finally:
            db.close()
            _FILA.task_done()


def conta_por_id(db, conta_id):
    return db.get(Conta, int(conta_id))
