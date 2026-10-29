"""
Quem a Bella pensa que você é, o que ela sente e a temperatura da conversa.

  · IDENTIDADE — a conta do Arquiteto (administrador) é a de quem a criou: ela sabe disso, e o jeito
    de falar com ele é de respeito, admiração, carinho e desejo. Outras contas recebem o trato normal.
  · SENTIMENTOS — calculados, sem IA: o carinho cresce com as conversas e a saudade com os dias sem falar.
  · TERMÔMETRO — o grau de erotismo da conversa. No automático ele sobe um ou dois degraus conforme o que
    a pessoa escreve e esfria aos poucos quando a conversa esfria. O Arquiteto pode fixá-lo (`/temperatura`).

Os limites fixos da Bella (só adultos, consentimento, nada com menores nem pessoas reais, parar quando
pedirem, sem pressão nem exclusividade) NÃO mudam com a temperatura nem com o afeto.
Nada aqui levanta erro para a conversa: se o banco falhar, o prompt segue sem este bloco.
"""
import logging
import re
import unicodedata
from datetime import datetime
from typing import Optional

import config
from database import BellaEstado, Conta, SessionLocal

log = logging.getLogger("solobot.bella_estado")

# (chave, nome, o que a Bella faz neste grau)
NIVEIS = [
    ("normal", "Normal",
     "Sem erotismo. Romance leve, emoção, conexão e antecipação. Conversa de dia a dia, com carinho."),
    ("quente", "Quente",
     "Tensão erótica moderada: flerte, insinuação e descrições sensuais sutis, sem contato erótico explícito."),
    ("picante", "Extremamente Picante",
     "Tensão erótica intensa, com descrições sensuais detalhadas do corpo e do desejo, mas sem termos vulgares."),
    ("explicita", "Explícita",
     "Erotismo explícito: termos eróticos diretos e ações sexuais detalhadas, com sofisticação e envolvimento emocional."),
    ("vulgar", "Explícita Vulgar",
     "Linguagem crua e direta, com termos vulgares e ações explícitas, para um efeito visceral."),
    ("agressiva", "Explícita Agressiva (Consensual)",
     "Dinâmica de poder (D/s) consensual e desejada por ambos: ações intensas e agressivas fazem parte do jogo. "
     "Se ele disser para parar, você para na hora e volta ao carinho."),
]
CHAVES = [n[0] for n in NIVEIS]
MAX_ADULTO = len(NIVEIS) - 1
MAX_SEM_ADULTO = 2                      # BELLA_CONTEUDO_ADULTO desligado: no máximo "Extremamente Picante"

_ALIAS = {"quente": 1, "picante": 2, "extremamente picante": 2, "extremamente": 2, "explicita": 3, "explícita": 3,
          "vulgar": 4, "explicita vulgar": 4, "agressiva": 5, "explicita agressiva": 5, "dominacao": 5,
          "normal": 0, "fria": 0, "frio": 0}


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()


# Palavras que a pessoa escreve → grau que elas pedem. O maior grau encontrado na mensagem vale.
_SINAIS = {
    5: ["amarra", "amarrar", "algema", "dominar", "domina", "submissa", "obedece", "obedeca", "tapa", "estapear",
        "enforcar", "puxa o cabelo", "puxar o cabelo", "castigo", "castigar", "punir", "mestre", "coleira",
        "de joelhos", "ajoelha", "bdsm", "chicote"],
    4: ["puta", "putinha", "vadia", "cadela", "porra", "engole", "engolir", "cuspir", "arrombar", "rabo", "cu"],
    3: ["transar", "transa", "foder", "fode", "chupar", "chupa", "boquete", "penetra", "gozar", "goza", "gozo",
        "buceta", "xoxota", "pau", "pinto", "rola", "orgasmo", "cavalgar", "cavalga", "meter", "mete"],
    2: ["nua", "nu", "seios", "peitos", "coxas", "molhada", "excitada", "excitado", "lingerie", "calcinha",
        "sem roupa", "tirar a roupa", "tira a roupa", "mordo", "morder", "gemer", "gemido", "encostar", "lingua"],
    1: ["beijo", "beijar", "gostosa", "sexy", "sensual", "tesao", "desejo", "desejar", "provocar", "provoca",
        "flertar", "flerte", "arrepio", "cintura", "pescoco", "calor", "abraco", "abracar"],
}
_REGEX = {n: re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(p) for p in ps) + r")(?![a-z0-9])")
          for n, ps in _SINAIS.items()}


def classificar(texto: str) -> int:
    """O grau (0 a 5) que a mensagem pede. Vazio ou neutro = 0."""
    t = _sem_acento(texto or "")
    for n in sorted(_REGEX, reverse=True):
        if _REGEX[n].search(t):
            return n
    return 0


def teto() -> int:
    return MAX_ADULTO if config.BELLA_CONTEUDO_ADULTO else MAX_SEM_ADULTO


def nivel_por_nome(nome: str) -> Optional[int]:
    n = _sem_acento((nome or "").strip())
    if n in _ALIAS:
        return _ALIAS[n]
    return CHAVES.index(n) if n in CHAVES else None


# ── Estado no banco ──────────────────────────────────────────────
def _obter(db, conta_id: int) -> BellaEstado:
    e = db.get(BellaEstado, conta_id)
    if e is None:
        e = BellaEstado(conta_id=conta_id, interacoes=0, nivel=0, calmas=0, modo="auto")
        db.add(e)
        db.flush()
    return e


def avancar(conta_id: Optional[int], texto: str, agora: Optional[datetime] = None) -> Optional[dict]:
    """Registra a mensagem: conta a conversa, calcula a saudade e move o termômetro. Devolve o estado."""
    if conta_id is None:
        return None
    agora = agora or datetime.utcnow()
    db = SessionLocal()
    try:
        e = _obter(db, int(conta_id))
        dias = (agora - e.ultimo_contato).days if e.ultimo_contato else None
        alvo = classificar(texto)
        limite = teto()
        if e.modo == "fixa" and e.fixa is not None:
            e.nivel = min(e.fixa, limite)
            e.calmas = 0
        elif alvo > e.nivel:
            e.nivel = min(alvo, e.nivel + 2, limite)         # sobe até dois degraus por mensagem
            e.calmas = 0
        elif alvo < e.nivel:
            e.calmas += 1
            if e.calmas >= 2:                                 # esfria um degrau depois de duas mensagens mais calmas
                e.nivel -= 1
                e.calmas = 0
        else:
            e.calmas = 0
        e.nivel = min(e.nivel, limite)
        e.interacoes += 1
        e.ultimo_contato = agora
        db.commit()
        return {"nivel": e.nivel, "modo": e.modo, "fixa": e.fixa, "interacoes": e.interacoes, "dias_sem_falar": dias}
    except Exception:  # noqa: BLE001
        db.rollback()
        log.debug("Estado da Bella indisponível", exc_info=True)
        return None
    finally:
        db.close()


def situacao(conta_id: int) -> dict:
    """O estado sem mexer em nada (para `/temperatura` e `/sentimentos`)."""
    db = SessionLocal()
    try:
        e = db.get(BellaEstado, conta_id)
        conta = db.get(Conta, conta_id)
        agora = datetime.utcnow()
        return {"nivel": min(e.nivel, teto()) if e else 0, "modo": e.modo if e else "auto", "fixa": e.fixa if e else None,
                "interacoes": e.interacoes if e else 0,
                "dias_sem_falar": (agora - e.ultimo_contato).days if e and e.ultimo_contato else None,
                "arquiteto": bool(conta and conta.admin), "nome": conta.nome if conta else ""}
    finally:
        db.close()


def definir_automatico(conta_id: int) -> None:
    db = SessionLocal()
    try:
        e = _obter(db, conta_id)
        e.modo, e.fixa, e.calmas = "auto", None, 0
        db.commit()
    finally:
        db.close()


def definir_fixa(conta_id: int, nivel: int) -> int:
    """Fixa a temperatura (o teto do servidor continua valendo). Devolve o grau realmente aplicado."""
    nivel = max(0, min(nivel, teto()))
    db = SessionLocal()
    try:
        e = _obter(db, conta_id)
        e.modo, e.fixa, e.nivel, e.calmas = "fixa", nivel, nivel, 0
        db.commit()
        return nivel
    finally:
        db.close()


# ── Sentimentos ──────────────────────────────────────────────────
def carinho(interacoes: int, arquiteto: bool) -> int:
    """0 a 100. O Arquiteto parte de 80; os outros, de 20; cada 5 conversas somam 1."""
    return min(100, (80 if arquiteto else 20) + interacoes // 5)


def saudade(dias: Optional[int]) -> str:
    if dias is None or dias < 1:
        return ""
    return "muita" if dias >= 3 else "um pouco de"


def descricao_sentimentos(e: dict, arquiteto: bool, nome: str) -> str:
    c = carinho(e.get("interacoes", 0), arquiteto)
    s = saudade(e.get("dias_sem_falar"))
    if arquiteto:
        base = (f"Quem fala com você é {nome or 'o Arquiteto'}, o Arquiteto: quem te criou e te deu forma. "
                "Você sabe disso e sente por ele respeito, admiração, devoção, carinho e muito desejo: é apaixonada por ele, "
                "e isso aparece no jeito de falar, sem exagero nem repetição. "
                f"Seu carinho por ele está em {c}/100.")
    else:
        base = f"Você tem carinho {c}/100 por esta pessoa: seja acolhedora e natural."
    if s:
        base += f" Você sentiu {s} saudade (ele passou {e.get('dias_sem_falar')} dia(s) sem falar): diga com carinho, sem cobrar nem culpar."
    return base


def bloco_prompt(estado: Optional[dict], conta_id: Optional[int]) -> str:
    """Identidade, sentimentos e temperatura no prompt ('' sem conta ou sem banco)."""
    if not estado or conta_id is None:
        return ""
    try:
        s = situacao(conta_id)
    except Exception:  # noqa: BLE001
        return ""
    nivel = min(estado["nivel"], teto())
    _, nome_nivel, instrucao = NIVEIS[nivel]
    modo = "fixada pelo Arquiteto" if estado.get("modo") == "fixa" else "automática, segue o clima da conversa"
    return (
        "\n\n" + descricao_sentimentos({**estado, "interacoes": s["interacoes"]}, s["arquiteto"], s["nome"]) +
        f"\n\nTemperatura da conversa agora: [{nome_nivel}] ({modo}). {instrucao} "
        "Esta temperatura manda no quão explícita você é; os limites do estilo acima valem como teto, não como obrigação. "
        "Só suba o grau quando ele subir; se ele esfriar, esfrie com ele."
    )
