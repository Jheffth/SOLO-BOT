"""A Bella cria prompts de imagem. Categoria atual: realismo sensual (modelo própria, de selfie noturna).

O modelo abaixo veio da conversa "REALISMO SENSUAL" do Grok: o texto fixo (câmera, pele, negativos)
não muda; só mudam o cenário, o gesto, a expressão, a roupa, a luz e o fundo. Só gera texto: nunca
imagens, e só entrega o prompt a quem pediu.
"""
import re
import threading
import time

from nucleo import grok

MAX_PROMPT = 3900            # cabe numa mensagem do Telegram (4096)
_CONTEXTO_MIN = 30
_ULTIMA = {}
_TRAVA = threading.Lock()

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
- Saída: apenas o prompt, em texto simples, sem título, sem explicações, sem Markdown, sem comentários
  antes ou depois e com no máximo 3500 caracteres.

MODELO:
""" + MODELO_REALISMO

_ALEATORIO = "Pedido: aleatório. Escolha você um cenário, roupa, luz e fundo novos e diferentes dos últimos."

_PEDIDO = re.compile(
    r"^\s*(?:/prompt\b|(?:(?:por\s+favor|bella)[,\s]+)?(?:me\s+)?(?:cri[ae]r?|ger[ae]r?|gera|faz(?:er)?|fa[cç]a|"
    r"mont[ae]r?|escrev[ae]r?|quero|preciso\s+d[eoa])\s+(?:um\s+|o\s+|outro\s+|novo\s+|mais\s+um\s+)?prompt\b)"
    r"[\s:,\-–]*(.*)$", re.IGNORECASE | re.DOTALL)
_PROXIMO = re.compile(r"^\s*(?:pr[oó]xim[oa]|outr[oa]|mais\s+um[a]?)\s+aleat[oó]ri[oa]\s*[.!]*\s*$", re.IGNORECASE)


def _lembrar(chave):
    with _TRAVA:
        _ULTIMA.pop(chave, None)
        _ULTIMA[chave] = time.monotonic()
        while len(_ULTIMA) > 256:
            _ULTIMA.pop(next(iter(_ULTIMA)))


def _recente(chave):
    with _TRAVA:
        quando = _ULTIMA.get(chave)
    return quando is not None and time.monotonic() - quando < _CONTEXTO_MIN * 60


def pedido_de(texto, chave=None):
    """O pedido de prompt dentro da mensagem, ou None se a mensagem não é um pedido de prompt.
    '' = aleatório. 'próximo aleatório' só vale logo depois de um prompt desta conversa."""
    texto = (texto or "").strip()
    if not texto:
        return None
    m = _PEDIDO.match(texto)
    if m:
        pedido = m.group(1).strip()
        return "" if re.fullmatch(r"(?:aleat[oó]ri[oa]|qualquer\s+um|surpreenda[\s\-]?me)[.!]*", pedido, re.I) else pedido
    if chave is not None and _PROXIMO.match(texto) and _recente(chave):
        return ""
    return None


def criar(pedido, chave=None):
    """O prompt pronto (texto simples), ou None se o Grok não respondeu ou a resposta não serve."""
    entrada = ("Pedido: " + pedido[:600]) if pedido else _ALEATORIO
    saida = grok.gerar(INSTRUCAO, entrada, max_tokens=2048, temperatura=.9, timeout=40)
    if not saida:
        return None
    saida = re.sub(r"^```[a-z]*\s*|\s*```$", "", saida.strip()).strip()
    if (len(saida) < 800 or len(saida) > MAX_PROMPT or "referência" not in saida.lower()
            or any(ord(c) < 32 and c not in "\n\r\t" for c in saida)):
        return None
    if chave is not None:
        _lembrar(chave)
    return saida


FALADO = "Pronto, o prompt está na tela. Quer outro? Diga próximo aleatório."
