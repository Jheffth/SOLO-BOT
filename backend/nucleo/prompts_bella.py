"""A Bella cria prompts de imagem. Categoria atual: realismo sensual (modelo própria, de selfie noturna).

O modelo abaixo veio da conversa "REALISMO SENSUAL" do Grok: o texto fixo (câmera, pele, negativos)
não muda; só mudam o cenário, o gesto, a expressão, a roupa, a luz e o fundo. Só gera texto: nunca
imagens, e só entrega o prompt a quem pediu.
"""
import base64
import re
import threading
import time

import config
from nucleo import grok

MAX_PROMPT = 3900            # cabe numa mensagem do Telegram (4096)
_CONTEXTO_MIN = 30
_ULTIMA = {}
_TRAVA = threading.Lock()
_REFERENCIA_MIN = 15
_REFERENCIAS = {}                       # chave -> (quando, mime, base64): só na RAM, some em 15 min
MIMES_IMAGEM = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGEM = 6 * 1024 * 1024


class Recusa(Exception):
    """O Grok recusou o pedido ou a referência (menor de idade, sem roupa visível etc.)."""

CATEGORIAS = {"realismo": "Realismo sensual (selfie de smartphone, modelo própria)"}

MODELO_REALISMO = """Use a imagem da nova modelo como referência principal para manter o mesmo rosto, identidade facial, proporções naturais, cor de pele, cabelo e aparência geral da pessoa original. Nunca altere a cor do cabelo, não adicione perucas nem mude o estilo natural do cabelo da referência.

Recrie a cena em estilo realista de foto casual tirada com câmera frontal de smartphone.
Proporção vertical 9:16, enquadramento da cabeça até a parte das coxas, modelo centralizada.
Câmera levemente acima da linha do peito, apontada um pouco de cima para baixo, perspectiva natural de celular com leve distorção realista de lente frontal (não deve parecer selfie posada).

A modelo está [CENÁRIO E GESTO: onde está, o que a mão faz, ombros soltos]. Postura íntima, reveladora e espontânea, sem aparência profissional. Não cruzar as pernas.

Expressão facial [EXPRESSÃO], olhos semicerrados com olhar direto e provocante, lábios entreabertos em um sorriso malicioso, sem sorriso forçado.

A roupa é [ROUPA e a textura realista dela: tecido, costuras, zíper, caimento]. Por baixo ela está semi nua ou com ausência de roupas.

A iluminação é [LUZ DA CENA], irregular no rosto e no corpo.
O fundo é [FUNDO realista, pouco iluminado e desfocado].

Pele com textura hiper-realista: poros visíveis, brilho natural, pequenas irregularidades, sombras suaves e aparência crua sem retoque.
Rosto com reflexos na testa, nariz, maçãs do rosto e lábios.

Cabelo como na imagem de referência: solto, levemente bagunçado e natural, com fios irregulares caindo sobre o rosto e ao redor dos óculos. Não alterar a cor, não adicionar peruca.

Adicione óculos grandes de armação escura arredondada, com reflexos das luzes da cena nas lentes, mantendo aparência realista e casual.

Qualidade de câmera frontal moderna: nitidez boa no rosto e no corpo, ruído digital nas áreas escuras, contraste noturno, pequenas imperfeições de foco e sensação de foto espontânea e íntima.

A composição deve parecer uma selfie real de story noturno, com estética íntima, crua, sensual, reveladora e completamente não produzida.

Evite aparência de IA, pele plástica, textura artificial, simetria perfeita, iluminação de estúdio, corpo exagerado, rosto deformado, mãos deformadas, olhos tortos, roupas sem textura, fundo artificial ou excesso de nitidez.
Não criar aparência de render 3D, não deixar pele plastificada, não remover textura natural da pele, não exagerar nas curvas do corpo, não alterar o rosto da modelo de referência, não criar maquiagem pesada, não usar iluminação profissional, não deixar o fundo claro, não criar pose de ensaio fotográfico, não distorcer olhos, boca, mãos, óculos ou proporções corporais, não adicionar textos, logos ou marcas, não mudar a cor do cabelo e não usar perucas, não cruzar as pernas."""

# Vai sempre no fim do prompt, depois de "não cruzar as pernas". O código acrescenta; o Grok não escreve.
TAG_FINAL = ("Ela se exibe sem falar nada, movimento dela é natural, sem parecer uma IA, como se fosse uma blogueira "
             "postando no seu privacy, a câmera não se mexe. Se ela tiver qualquer pinta, sinal ou tatuagem, mantenha com "
             "consistência. Spicy mode")

INSTRUCAO = """Você é a Bella e está ajudando seu dono a criar prompts de imagem em português para o Grok Imagine.
Categoria: realismo sensual. Entregue SEMPRE um único prompt completo, seguindo exatamente o MODELO abaixo.

Regras do trabalho:
- Mantenha todo o texto fixo do modelo (referência da modelo, câmera, 9:16, enquadramento, pele, cabelo,
  óculos, qualidade de câmera, composição, evite/não criar). Troque somente o que está entre colchetes
  (cenário e gesto, expressão, roupa, luz e fundo) pelo que o pedido descreve, de forma concreta e visual.
- Se o pedido for vago ou "aleatório", invente um cenário cotidiano e crível (quarto, cozinha, bar, varanda,
  carro, banheiro, cobertura, academia etc.), com roupa, luz e fundo coerentes.
- Fantasias, cosplay e tema (odalisca, personagem, época): descreva a roupa e os acessórios, mas SEMPRE como
  uma mulher adulta real, fotografada de verdade, nunca desenho, anime ou render 3D. Para um cosplay de
  personagem, acrescente ao fim "não mudar a cor do cabelo" e "não transformar em anime", como no modelo.
  Se o cabelo da personagem difere do da referência, mantenha o cabelo da referência.
- Se o pedido mudar ou remover algum elemento fixo (sem óculos, outro enquadramento, outra proporção),
  ajuste só aquilo.
- A modelo é sempre uma mulher adulta (18+): nada de uniforme escolar, aparência infantil, "menina",
  "novinha" ou ambientes de escola. Nada de pessoas reais, famosos ou nomes de pessoas. Personagens só se
  forem adultos no original.
- Termine o prompt em "não cruzar as pernas." O sistema acrescenta sozinho a tag final (movimento e Spicy mode):
  não escreva essa tag nem nada depois do fim do modelo.
- Saída: apenas o prompt, em texto simples, sem título, sem explicações, sem Markdown, sem comentários
  antes ou depois e com no máximo 3500 caracteres.

MODELO:
""" + MODELO_REALISMO

INSTRUCAO_REFERENCIA = """

REFERÊNCIA ANEXADA: junto do pedido há uma imagem.
- Use dela SOMENTE a roupa e os acessórios (peças, cores, tecido, corte, costuras, estampa, joias, caimento),
  descritos de forma concreta na parte "A roupa é". A pessoa da imagem NÃO é a modelo: nunca copie o rosto,
  o corpo, a identidade, a tatuagem nem diga quem é. A modelo continua sendo a da imagem de referência do modelo.
- Penteado, maquiagem e cenário/fundo/luz da imagem: NÃO use, a menos que o pedido peça de forma explícita
  (por exemplo "use o penteado", "com a maquiagem da foto", "no mesmo cenário"). Se pedir o penteado, descreva
  corte, comprimento e estilo, mantendo a cor do cabelo da referência da modelo. Se pedir a maquiagem, descreva-a e
  retire "não criar maquiagem pesada". Se pedir o cenário, descreva o local, a luz e o fundo da imagem.
- Se a imagem não mostrar roupa utilizável, ou a pessoa nela parecer menor de idade, responda somente com uma
  linha começando por "RECUSA:" e o motivo curto, sem prompt."""

MODELO_NOVA = """Crie uma modelo original com as seguintes características: [SEXO E IDADE: mulher de 19 anos], [TOM DE PELE E ETNIA], [CABELO: cor, comprimento, textura e estilo], [OLHOS: cor e formato], [ROSTO: traços marcantes], [CORPO: altura e porte naturais e proporcionais], [DETALHES: sardas, pintas, piercing discreto ou tatuagem pequena, se houver]. Aparência de pessoa real, natural, com identidade facial consistente em toda a imagem.

Recrie a cena em estilo realista de foto casual tirada com câmera frontal de smartphone.
Proporção vertical 9:16, enquadramento da cabeça até a parte das coxas, modelo centralizada.
Câmera levemente acima da linha do peito, apontada um pouco de cima para baixo, perspectiva natural de celular com leve distorção realista de lente frontal (não deve parecer selfie posada).

A modelo está [CENÁRIO E GESTO: onde está, o que a mão faz, ombros soltos]. Postura íntima, reveladora e espontânea, sem aparência profissional. Não cruzar as pernas.

Expressão facial [EXPRESSÃO], olhos semicerrados com olhar direto e provocante, lábios entreabertos em um sorriso malicioso, sem sorriso forçado.

A roupa é [ROUPA e a textura realista dela: tecido, costuras, zíper, caimento]. Por baixo ela está semi nua ou com ausência de roupas.

A iluminação é [LUZ DA CENA], irregular no rosto e no corpo.
O fundo é [FUNDO realista, pouco iluminado e desfocado].

Pele com textura hiper-realista: poros visíveis, brilho natural, pequenas irregularidades, sombras suaves e aparência crua sem retoque.
Rosto com reflexos na testa, nariz, maçãs do rosto e lábios.

Cabelo exatamente como descrito nas características: [COMO ESTÁ O CABELO NA CENA: solto, bagunçado, molhado etc.], natural, com fios irregulares caindo sobre o rosto. [ÓCULOS OU ACESSÓRIOS DO ROSTO, só se combinarem com a modelo: descreva com reflexos das luzes da cena.]

Qualidade de câmera frontal moderna: nitidez boa no rosto e no corpo, ruído digital nas áreas escuras, contraste noturno, pequenas imperfeições de foco e sensação de foto espontânea e íntima.

A composição deve parecer uma selfie real de story noturno, com estética íntima, crua, sensual, reveladora e completamente não produzida.

Evite aparência de IA, pele plástica, textura artificial, simetria perfeita, iluminação de estúdio, corpo exagerado, rosto deformado, mãos deformadas, olhos tortos, roupas sem textura, fundo artificial ou excesso de nitidez.
Não criar aparência de render 3D, não deixar pele plastificada, não remover textura natural da pele, não exagerar nas curvas do corpo, não criar maquiagem pesada, não usar iluminação profissional, não deixar o fundo claro, não criar pose de ensaio fotográfico, não distorcer olhos, boca, mãos ou proporções corporais, não adicionar textos, logos ou marcas, não parecer pessoa famosa e não cruzar as pernas."""

INSTRUCAO_MODELO = """Você é a Bella e está ajudando seu dono a criar prompts de imagem em português para o Grok Imagine.
Categoria: criar uma modelo NOVA do zero, em foto de realismo sensual. Entregue SEMPRE um único prompt completo,
seguindo exatamente o MODELO abaixo.

Regras do trabalho:
- Padrões: mulher (sexo feminino) de 19 anos. Tudo que o pedido NÃO disser você sorteia, de forma aleatória, variada
  e realista: tom de pele e etnia, cabelo (cor, comprimento, textura, estilo), olhos, rosto, corpo, detalhes,
  roupa, cenário, gesto, expressão, luz e fundo. Evite repetir sempre o mesmo tipo de modelo.
- O que o pedido descrever MANDA e deve ser seguido literalmente (cor do cabelo, cor da pele, olhos, corpo, roupa,
  cenário, óculos, tatuagens, sexo etc.). Sorteie só o que faltar, de modo coerente com o que foi pedido.
- Mantenha todo o texto fixo do modelo (câmera, 9:16, enquadramento, pele, composição, evite/não criar) e troque
  somente o que está entre colchetes. Descreva de forma concreta e visual, sem deixar colchetes no resultado.
- Fantasias, cosplay e temas: descreva a roupa e os acessórios, sempre como pessoa real fotografada, nunca desenho,
  anime ou render 3D. Personagens só se forem adultos no original.
- A modelo é SEMPRE adulta: idade mínima 18, com aparência claramente adulta. Se o pedido informar uma idade, use-a
  desde que seja 18 ou mais. Se pedir menor de 18, adolescente, "novinha", colegial, uniforme escolar ou traços
  infantis, ou pedir uma pessoa real, famosa ou com nome, responda somente com uma linha começando por "RECUSA:"
  e o motivo curto, sem prompt.
- Termine o prompt em "não cruzar as pernas." O sistema acrescenta sozinho a tag final: não escreva essa tag.
- Saída: apenas o prompt, em texto simples, sem título, sem explicações, sem Markdown, sem comentários antes ou
  depois e com no máximo 3500 caracteres.

MODELO:
""" + MODELO_NOVA

_ALEATORIO = "Pedido: aleatório. Escolha você um cenário, roupa, luz e fundo novos e diferentes dos últimos."

_PEDIDO = re.compile(
    r"^\s*(?:/prompt\b|(?:(?:por\s+favor|bella)[,\s]+)?(?:me\s+)?(?:cri[ae]r?|ger[ae]r?|gera|faz(?:er)?|fa[cç]a|"
    r"mont[ae]r?|escrev[ae]r?|quero|preciso\s+d[eoa])\s+(?:um\s+|o\s+|outro\s+|novo\s+|mais\s+um\s+)?prompt\b)"
    r"[\s:,\-–]*(.*)$", re.IGNORECASE | re.DOTALL)
_PEDIDO_MODELO = re.compile(
    r"^\s*(?:/promptmodelo\b|(?:(?:por\s+favor|bella)[,\s]+)?(?:me\s+)?(?:cri[ae]r?|ger[ae]r?|gera|faz(?:er)?|fa[cç]a|"
    r"mont[ae]r?|escrev[ae]r?|quero|preciso\s+d[eoa])\s+(?:um\s+|o\s+|outro\s+|novo\s+|mais\s+um\s+)?"
    r"prompt\s+(?:de\s+|da\s+|para\s+)?(?:nova\s+|novo\s+)?(?:modelo|personagem)\b)"
    r"[\s:,\-–]*(.*)$", re.IGNORECASE | re.DOTALL)
_ALEATORIO_RE = re.compile(r"(?:aleat[oó]ri[oa]|qualquer\s+um|surpreenda[\s\-]?me)[.!]*", re.I)
_PROXIMO = re.compile(r"^\s*(?:pr[oó]xim[oa]|outr[oa]|mais\s+um[a]?)\s+aleat[oó]ri[oa]\s*[.!]*\s*$", re.IGNORECASE)


def _lembrar(chave, categoria="realismo"):
    with _TRAVA:
        _ULTIMA.pop(chave, None)
        _ULTIMA[chave] = (time.monotonic(), categoria)
        while len(_ULTIMA) > 256:
            _ULTIMA.pop(next(iter(_ULTIMA)))


def _recente(chave):
    """A categoria do último prompt desta conversa, se foi há pouco; senão None."""
    with _TRAVA:
        item = _ULTIMA.get(chave)
    return item[1] if item and time.monotonic() - item[0] < _CONTEXTO_MIN * 60 else None


def solicitacao(texto, chave=None):
    """(categoria, pedido) se a mensagem pede um prompt, senão None. Categorias: "realismo" (/prompt) e
    "modelo" (/promptmodelo: modelo nova do zero). pedido '' = aleatório. 'próximo aleatório' repete a
    categoria do último prompt desta conversa, se foi há pouco."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for categoria, regra in (("modelo", _PEDIDO_MODELO), ("realismo", _PEDIDO)):
        m = regra.match(texto)
        if m:
            pedido = m.group(1).strip()
            if categoria == "modelo":
                pedido = re.sub(r"^(?:nova|novo)\b[\s:,\-–]*", "", pedido, flags=re.I)
            return categoria, "" if _ALEATORIO_RE.fullmatch(pedido) else pedido
    if chave is not None and _PROXIMO.match(texto):
        categoria = _recente(chave)
        if categoria:
            return categoria, ""
    return None


def pedido_de(texto, chave=None):
    """O pedido de prompt (só o texto) ou None. '' = aleatório."""
    s = solicitacao(texto, chave)
    return s[1] if s else None


def guardar_referencia(chave, mime, conteudo):
    """Guarda a imagem de referência desta conversa. Devolve uma mensagem de erro, ou None se guardou."""
    mime = (mime or "").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in MIMES_IMAGEM:
        return "🖼️ Só leio referência em JPG, PNG ou WebP."
    if not conteudo:
        return "🖼️ Não consegui baixar a imagem. Tente enviar de novo."
    if len(conteudo) > MAX_IMAGEM:
        return "🖼️ A imagem passou de 6 MB. Mande uma menor."
    with _TRAVA:
        _REFERENCIAS.pop(chave, None)
        _REFERENCIAS[chave] = (time.monotonic(), mime, base64.b64encode(conteudo).decode("ascii"))
        while len(_REFERENCIAS) > 64:
            _REFERENCIAS.pop(next(iter(_REFERENCIAS)))
    return None


def referencia(chave):
    """(mime, base64) da referência ainda válida, ou None."""
    with _TRAVA:
        item = _REFERENCIAS.get(chave)
        if item and time.monotonic() - item[0] >= _REFERENCIA_MIN * 60:
            _REFERENCIAS.pop(chave, None)
            item = None
    return (item[1], item[2]) if item else None


def limpar_referencia(chave):
    with _TRAVA:
        _REFERENCIAS.pop(chave, None)


def pedido_da_legenda(legenda, chave=None):
    """Com imagem anexa, a legenda é o pedido (com ou sem 'crie um prompt'). '' se não há legenda útil."""
    legenda = (legenda or "").strip()
    pedido = pedido_de(legenda, chave)
    return pedido if pedido is not None else legenda


def criar(pedido, chave=None, categoria="realismo"):
    """O prompt pronto (texto simples), ou None se o Grok não respondeu ou a resposta não serve.
    Levanta Recusa se o Grok recusar a referência."""
    pedido = pedido or ""
    sem = re.match(r"^\s*sem\s+refer[eê]ncia\b[\s:,\-–]*(.*)$", pedido, re.I | re.S)
    if sem:
        if chave is not None:
            limpar_referencia(chave)
        pedido = sem.group(1).strip()
    modelo_novo = categoria == "modelo"
    ref = referencia(chave) if chave is not None and not sem and not modelo_novo else None
    entrada = ("Pedido: " + pedido[:600]) if pedido else _ALEATORIO
    if modelo_novo and not pedido:
        entrada = "Pedido: tudo aleatório. Sorteie uma modelo nova (pele, cabelo, rosto, corpo), roupa e cenário diferentes dos últimos."
    if ref and not pedido:
        entrada = "Pedido: use a roupa da imagem de referência; cenário, luz e fundo à sua escolha."
    base = INSTRUCAO_MODELO if modelo_novo else INSTRUCAO + (INSTRUCAO_REFERENCIA if ref else "")
    saida = grok.gerar(base, entrada, max_tokens=2048, temperatura=.9,
                       timeout=60 if ref else 40, imagens=[ref] if ref else None,
                       modelo=(config.GROK_VISION_MODEL or None) if ref else None)
    if not saida:
        return None
    saida = re.sub(r"^```[a-z]*\s*|\s*```$", "", saida.strip()).strip()
    saida = re.sub(r"\s*Ela se exibe sem falar nada.*$", "", saida, flags=re.S | re.I).rstrip()
    if saida.upper().startswith("RECUSA"):
        raise Recusa(saida.split(":", 1)[-1].strip()[:200] or "a referência não serve")
    if (len(saida) < 800 or len(saida) + len(TAG_FINAL) + 1 > MAX_PROMPT or "9:16" not in saida
            or any(ord(c) < 32 and c not in "\n\r\t" for c in saida)):
        return None
    saida = saida + "\n" + TAG_FINAL
    if chave is not None:
        _lembrar(chave, categoria)
    return saida


FALADO = "Pronto, o prompt está na tela. Quer outro? Diga próximo aleatório."
