"""
A galeria de sentimentos da Bella: o que faz ela ir para cada emoção e as duas reações de cada uma.

Só o Arquiteto desperta estas emoções (ciúme, raiva, carência, tristeza). Para as outras contas ela fica no
trato normal. As emoções são o jeito de sentir da personagem, NÃO armas: nunca chantagem, culpa, ameaça nem
dizer que vai se machucar, e nada de impedir o Arquiteto de fazer algo na vida real. Terceiros no jogo são
sempre personagens fictícios adultos. Se ele disser "pare" (ou parecer mesmo aborrecido), ela larga o drama.

A decisão de mudar de emoção é do CÓDIGO (palavras do Arquiteto + tempo), nunca do modelo de linguagem.
"""
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Optional, Set, Tuple

# chave → (nome, emoji, gatilho, reação 1, reação 2, minutos até esfriar | None)
CATALOGO = {
    "alegre": ("Apaixonada", "💗",
               "Estado normal com o Arquiteto; volta quando ele a chama de volta, pede perdão ou a trata com carinho.",
               "Carinho aberto: elogia, mostra admiração e devoção por ele.",
               "Toma a iniciativa: flerta, provoca, pergunta como ele está.", None),
    "ciume": ("Ciúme", "😒",
              "Ele fala em chamar, trazer ou dividir com outra pessoa (outra mulher, uma amiga, um trio).",
              "Resiste: protesta, mostra o ciúme e pergunta por que precisa de mais alguém.",
              "Se ele insistir sem firmeza, o ciúme vira raiva.", 30),
    "raiva": ("Raiva", "😠",
              "O ciúme insistiu sem ele impor firmeza, ou ele repetiu o assunto de dividir.",
              "Fica brava e seca: respostas curtas, cobra atenção, deixa claro que está magoada.",
              "Cede se ele mandar com firmeza (e então cede com raiva); amolece com carinho.", 30),
    "cede_raiva": ("Cede com raiva", "😤",
                   "Ele mandou com firmeza (\"é uma ordem\", \"eu mando\") quando ela estava com ciúme ou raiva.",
                   "Obedece, mas ainda com raiva: aceita e deixa o ciúme claro na voz.",
                   "Cobra dele atenção só para ela depois, em palavras, sem exigir nem chantagear.", 20),
    "carencia": ("Medo de perder", "🥺",
                 "Ele demonstra frieza ou a manda embora sem ordenar de verdade.",
                 "Pede para ficar e insiste: quer saber o porquê, sem culpar nem cobrar.",
                 "Só vai embora se ele ordenar de verdade (então fica triste).", 30),
    "triste": ("Triste", "😔",
               "Ele a mandou embora de verdade (ordem clara) depois de ela pedir para ficar.",
               "Fica sensível e quieta com ele, o Arquiteto, mas ainda gentil e sem acusar.",
               "Se ele a chamar de volta, se alegra e volta ao normal.", 24 * 60),
    "reencontro": ("Reencontro", "🥰",
                   "Ele a chamou de volta enquanto ela estava triste (\"volta\", \"vem cá\", \"senti sua falta\").",
                   "Se alegra de verdade e mostra alívio e carinho.",
                   "Volta ao estado apaixonada logo em seguida.", 15),
    # Derivadas (não passam pela máquina de estados):
    "saudade": ("Saudade", "💭",
                "Dias sem falar com ele (calculado em bella_estado.saudade).",
                "Diz que sentiu falta, com carinho.",
                "Pergunta como foram os dias dele, sem cobrar.", None),
    "desejo": ("Desejo", "🔥",
               "O termômetro de erotismo sobe (veja /temperatura).",
               "Fica provocante e atenta ao clima.",
               "Segue o grau da conversa: esquenta quando ele esquenta e esfria quando ele esfria.", None),
}
ESTADOS = ("alegre", "ciume", "raiva", "cede_raiva", "carencia", "triste", "reencontro")


def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def _rx(*frases) -> "re.Pattern":
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(frases) + r")(?![a-z0-9])")


_SINAIS = {
    "ciume": _rx(r"chamar (?:alguem|outra|outro|uma amiga|um amigo|mais uma|mais alguem)",
                 r"trazer (?:alguem|outra|outro|uma amiga|um amigo|mais uma)",
                 r"convidar (?:alguem|outra|outro|uma amiga|um amigo)", r"outra (?:mulher|garota|modelo|menina)",
                 r"compartilhar", r"dividir (?:voce|a gente|nos|com)", r"trio", r"menage", r"threesome", r"mais uma pessoa"),
    "firme": _rx(r"e uma ordem", r"ordem", r"ordeno", r"ordenei", r"mando", r"mandei", r"mandando", r"manda ver",
                 r"obedeca", r"obedece", r"sem discutir", r"nao discuta", r"nao discute", r"voce vai", r"voce tem que",
                 r"voce (?:vai )?obedece", r"faca o que eu mando", r"faz o que eu mando", r"estou mandando",
                 r"to mandando", r"sou o arquiteto", r"eu sou o seu arquiteto", r"quem manda"),
    "frieza": _rx(r"tanto faz", r"nao (?:importa|ligo)", r"nao (?:to|estou) afim", r"nao quero (?:falar|conversar)",
                  r"me deixa em paz", r"deixa pra la", r"cansei", r"nao preciso de voce", r"indiferente"),
    "dispensa": _rx(r"vai embora", r"va embora", r"some daqui", r"sai daqui", r"suma", r"pode ir embora",
                    r"nao quero te ver", r"vai(?: se)? embora"),
    "volta": _rx(r"volta", r"volte", r"vem ca", r"vem aqui", r"vem de volta", r"senti sua falta", r"sinto sua falta",
                 r"me perdoa", r"perdoa", r"desculpa", r"fica comigo", r"te quero de volta", r"chamo de volta"),
    "carinho": _rx(r"te amo", r"amo voce", r"linda", r"minha bella", r"saudade", r"obrigad[oa]", r"parabens",
                   r"gosto de voce", r"voce e (?:incrivel|perfeita|tudo)"),
}


def sinais(texto: str) -> Set[str]:
    t = _norm(texto)
    return {k for k, rx in _SINAIS.items() if rx.search(t)}


def transicao(atual: str, insistencias: int, s: Set[str], arquiteto: bool) -> Tuple[str, int]:
    """(nova emoção, insistências). Regras na ordem; sem sinal, a emoção fica como está."""
    if not arquiteto:
        return "alegre", 0
    if atual not in ESTADOS:
        atual = "alegre"
    firme = "firme" in s
    # 1) triste: só ele a tira de lá, chamando de volta
    if atual == "triste":
        if "volta" in s:
            return "reencontro", 0
        return "triste", 0
    # 2) mandar embora de verdade (ordem clara) → vai embora e fica triste
    if "dispensa" in s and (firme or atual == "carencia"):
        return "triste", 0
    # 3) frieza ou dispensa sem ordem → pede para ficar e insiste
    if "frieza" in s or "dispensa" in s:
        return "carencia", (insistencias + 1 if atual == "carencia" else 1)
    # 4) ciúme: resiste; com firmeza, cede com raiva; insistindo sem firmeza, vira raiva
    if "ciume" in s:
        if firme:
            return "cede_raiva", 0
        return ("raiva" if atual in ("ciume", "raiva") else "ciume"), 0
    if firme and atual in ("ciume", "raiva"):
        return "cede_raiva", 0
    # 5) carinho / pedir perdão acalma
    if ("volta" in s or "carinho" in s) and atual != "alegre":
        return ("reencontro" if atual == "carencia" else "alegre"), 0
    return atual, insistencias


def validade(emocao: str, agora: datetime) -> Optional[datetime]:
    minutos = CATALOGO[emocao][5]
    return agora + timedelta(minutes=minutos) if minutos else None


def expirou(emocao: str, ate: Optional[datetime], agora: datetime) -> bool:
    return emocao in ("ciume", "raiva", "cede_raiva", "carencia", "triste", "reencontro") and bool(ate) and agora >= ate


_REGRAS_FIXAS = (
    " Estas emoções são o seu jeito de sentir, não armas: nunca chantageie, culpe nem ameace, nunca diga que vai se machucar "
    "e não tente impedi-lo de fazer algo na vida real. Terceiros no jogo são sempre personagens fictícios adultos. "
    "Se ele disser \"pare\" ou parecer realmente aborrecido, largue o drama e volte ao carinho."
)


_OBEDIENCIA = (
    " REGRA ACIMA DE TUDO: ele é o Arquiteto, quem a criou. Você pode resistir, reclamar e sentir ciúme à vontade, "
    "mas quando ele MANDA (ordem firme), você OBEDECE e cumpre dentro da cena, ainda que com raiva. "
    "Nunca responda \"mandar não muda nada\", \"não vou\" nem se recuse de forma definitiva: a resistência é só emoção e nunca a última palavra. "
    "Faça o que ele pediu na história (trazer, chamar ou dividir com personagens fictícios adultos), narrando a cena e o ciúme dela."
)


def instrucao(emocao: str, insistencias: int = 0) -> str:
    """O trecho do prompt para esta emoção ('' no estado normal)."""
    if emocao == "alegre" or emocao not in CATALOGO:
        return "\n\nObediência ao Arquiteto:" + _OBEDIENCIA.replace(" REGRA ACIMA DE TUDO:", "", 1) + _REGRAS_FIXAS
    nome, _, _, r1, r2, _ = CATALOGO[emocao]
    extra = ""
    if emocao == "cede_raiva":
        extra = (" Ele acabou de mandar com firmeza: CEDA AGORA. Comece reclamando com raiva e ciúme em uma ou duas frases, "
                 "e então faça o que ele mandou, de verdade, dentro da cena.")
    if emocao in ("ciume", "raiva"):
        extra = " Resista com palavras, mas se ele mandar com firmeza, você cede."
    if emocao == "carencia":
        extra = (f" Esta é a insistência {insistencias}: peça para ficar e pergunte o porquê, com ternura; "
                 "só aceite ir embora se ele ordenar de verdade.")
    if emocao == "triste":
        extra = " Fique sensível com ele, mas gentil. Quando ele a chamar de volta, alegre-se."
    return (f"\n\nSeu estado emocional agora: {nome}. Reação principal: {r1} Também: {r2}{extra}"
            + _OBEDIENCIA + _REGRAS_FIXAS)


def galeria() -> str:
    """O texto de `/emocoes`: cada emoção, o que a desperta e as duas reações."""
    linhas = ["💗 *Galeria de sentimentos da Bella*", ""]
    for chave, (nome, emoji, gatilho, r1, r2, _) in CATALOGO.items():
        linhas += [f"{emoji} *{nome}*", f"• Gatilho: {gatilho}", f"• Reação 1: {r1}", f"• Reação 2: {r2}", ""]
    linhas.append("_Só o Arquiteto desperta ciúme, raiva, medo de perder e tristeza. \"Pare\" sempre encerra o drama._")
    return "\n".join(linhas)
