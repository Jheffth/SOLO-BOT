"""A Bella cria prompts de imagem. Categoria atual: realismo sensual (modelo própria, de selfie noturna).

O modelo abaixo veio da conversa "REALISMO SENSUAL" do Grok: o texto fixo (câmera, pele, negativos)
não muda; só mudam o cenário, o gesto, a expressão, a roupa, a luz e o fundo. Só gera texto: nunca
imagens, e só entrega o prompt a quem pediu.
"""
import base64
import logging
import time
import re
import threading
import time

import config
from nucleo import biblioteca_prompts, grok

MAX_PROMPT = 8000            # Telegram e WhatsApp dividem em várias mensagens (canais/partes.py); o Bella.exe mostra inteiro
_CONTEXTO_MIN = 30
_ULTIMA = {}
_TRAVA = threading.Lock()
_REFERENCIA_MIN = 15
_REFERENCIAS = {}                       # chave -> (quando, mime, base64): só na RAM, some em 15 min
MIMES_IMAGEM = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGEM = 6 * 1024 * 1024


log = logging.getLogger("solobot.prompts")


class Recusa(Exception):
    """O Grok recusou o pedido ou a referência (menor de idade, sem roupa visível etc.)."""

# REGRA: todo prompt novo entra aqui e é entregue por roteador._prompt_responder (ou pelo /api/bella/conversa),
# que o marca como "prompt": o Bella.exe mostra todo prompt marcado numa caixa de texto com botão de copiar.
CATEGORIAS = {"realismo": "Realismo sensual (selfie de smartphone, modelo própria)",
              "modelo": "Modelo nova do zero (/promptmodelo)",
              "roupa": "Troca de roupa em imagem externa (/promptroupa)",
              "pose": "Troca de pose em imagem externa (/posehot)",
              "criativo": "Realismo sensual criativo, fora da biblioteca (/promptcriativo)"}
# Começa o texto enviado ao Bella.exe quando a resposta é um prompt; a tela tira a marca e abre a caixa de copiar.
MARCA_PROMPT = "[[prompt]]"

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
  antes ou depois e com no máximo 7000 caracteres.

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

INSTRUCAO_REFERENCIA_MODELO = """

REFERÊNCIA ANEXADA: junto do pedido há uma imagem. Ela é o guia da modelo nova.
- Descreva a modelo pelas características visíveis na imagem, de forma concreta nos campos entre colchetes:
  tom de pele, cabelo (cor, comprimento, textura, estilo), olhos, traços do rosto, porte do corpo, detalhes
  (sardas, pintas, tatuagens, piercings) e a roupa e acessórios. É uma modelo ORIGINAL inspirada nessas
  características, em texto: não diga quem é a pessoa da imagem nem use nome.
- Cenário, fundo e luz da imagem: NÃO use, a menos que o pedido peça de forma explícita; sorteie um cenário novo.
- O que o pedido escrito descrever manda sobre a imagem (por exemplo "cabelo ruivo", "com óculos").
- A idade segue a regra de adulta (19 por padrão, ou a pedida se for 18+).
- Se a pessoa da imagem parecer menor de idade, ou for uma pessoa famosa que você reconheça, ou a imagem não
  mostrar uma pessoa utilizável, responda somente com uma linha começando por "RECUSA:" e o motivo curto, sem prompt."""

INSTRUCAO_REFERENCIA_MODELO_TOTAL = """

MODO EXTRAÇÃO TOTAL (o dono pediu para extrair TUDO da imagem de referência). Isto vale acima das regras da
referência anteriores, exceto as de idade, recusa e anonimato:
- Observe a imagem com atenção e descreva, de forma concreta e fiel, TUDO o que é visível: tom de pele e subtom;
  formato do rosto (oval, redondo, quadrado, coração, alongado), testa, maçãs, queixo e mandíbula; sobrancelhas
  (formato, espessura, cor); olhos (cor exata, formato, distância, cílios); nariz; boca e lábios (volume, formato,
  cor); dentes, se aparecerem; pescoço; cabelo (cor exata com reflexos, comprimento, textura, volume, corte, franja,
  repartição, penteado e estado: solto, preso, molhado, bagunçado); corpo (altura aparente, porte, ombros, busto,
  cintura, quadris, braços, pernas, abdômen); sardas, pintas, cicatrizes, marcas de sol e de biquíni; TATUAGENS (desenho,
  tamanho, cor, lado e local exato no corpo); PIERCINGS (tipo, material e local); anéis, colares, brincos, pulseiras,
  relógio e outras joias; unhas (formato e cor); maquiagem (olhos, batom, blush, contorno); roupa peça por peça (cor,
  tecido, corte, decote, caimento, costuras), calçados e acessórios.
- Também use da imagem a expressão e a direção do olhar, a pose e a posição das mãos, o cenário, o fundo, a luz e a
  cor da cena (aqui o cenário DA IMAGEM é usado, em vez de sortear um novo).
- Coloque cada informação no campo certo entre colchetes e AMPLIE os campos quanto for preciso para caber tudo
  (frases curtas e específicas), sem apagar o texto fixo do modelo. Se o espaço apertar, mantenha todo o texto fixo e
  priorize rosto, cabelo, pele, tatuagens, piercings, joias, roupa e cenário. Respeite o limite de 7000 caracteres.
- Só descreva o que se vê; o que não estiver visível, escolha de forma coerente ou omita. Nunca invente tatuagens
  ou piercings que não existam. Continue sem dizer quem é a pessoa e sem usar nome.
- Um pedido escrito junto continua mandando sobre a imagem (por exemplo "mas com cabelo loiro")."""

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
  depois e com no máximo 7000 caracteres.

MODELO:
""" + MODELO_NOVA

MODELO_ROUPA = """Vista a pessoa da imagem de referência com a roupa descrita abaixo, trocando SOMENTE a roupa. Mantenha exatamente o mesmo rosto, identidade, expressão, cabelo (cor, corte e estilo), maquiagem, tom de pele, corpo, proporções, pose, posição das mãos e braços, ângulo da câmera, enquadramento, cenário, fundo, iluminação, sombras, cores e qualidade da foto original. Nada além da roupa muda.

A roupa é [DESCRIÇÃO COMPLETA PEÇA POR PEÇA: tipo de cada peça, cor exata, comprimento, decote, mangas, cintura, corte e caimento].
Tecido e acabamento: [TECIDO E TEXTURA realistas: brilho, transparência, renda, malha, couro, cetim, elástico, costuras, zíper, botões, babados, ilhoses, fivelas, estampas, bordados, strass, logos que fazem parte da peça].
Acessórios que fazem parte do look: [MEIAS, LIGAS, LUVAS, CINTO, CHOKER, JOIAS, CALÇADOS, ADEREÇOS, ou "nenhum"].

A roupa veste o corpo da pessoa de forma natural e coerente com a pose original: dobras, esticamento do tecido, pontos de tensão e sombras seguem a mesma luz e o mesmo ângulo da cena, com aparência de peça real fotografada, textura nítida do tecido e sem excesso de brilho artificial.

Não alterar rosto, corpo, cabelo, pele, pose, mãos, fundo, cenário, iluminação, enquadramento nem proporções da imagem original; não adicionar nem remover objetos ou pessoas da cena; não mudar a cor do cabelo; não criar aparência de IA, pele plástica, render 3D ou desenho; não distorcer mãos, rosto ou proporções corporais; não adicionar textos, logos ou marcas que não façam parte da roupa."""

INSTRUCAO_ROUPA = """Você é a Bella e está ajudando seu dono a criar prompts de troca de roupa em português para o Grok Imagine:
a roupa será vestida em uma imagem externa que ele vai enviar ao Grok junto do prompt. Entregue SEMPRE um único
prompt completo, seguindo exatamente o MODELO abaixo.

Regras do trabalho:
- Mantenha todo o texto fixo do modelo (a parte de manter rosto, corpo, pose, cenário, luz etc. e a parte de não
  alterar) e troque somente o que está entre colchetes pela descrição da roupa, concreta e visual. Nunca descreva
  a pessoa, o cenário ou a pose: só a roupa. Não deixe colchetes no resultado.
- Descreva PEÇA POR PEÇA e de forma fiel: cor exata, comprimento, decote, mangas, cintura, corte, caimento,
  tecido, textura, transparência, renda, costuras, zíper, botões, babados, estampas, bordados, strass, logos
  da própria peça e acessórios (meias, ligas, luvas, cinto, choker, joias, sapatos, aderecos). Cite o nível de
  transparência e de exposição quando fizer parte do look.
- Cosplay, fantasia, lingerie, biquíni, uniforme (enfermeira, policial, aeromoça, empregada, secretária,
  bombeira, atleta, etc.) e roupa temática: descreva cada peça e acessório como roupa real, de tecido real,
  nunca como desenho, anime ou render 3D. Para cosplay de personagem, descreva só o figurino.
- O pedido escrito pode pedir ajustes (mais curta, mais decotada, mais transparente, outra cor): aplique-os.
  Versões "sexy" ou "curta" apenas encurtam, decotam ou deixam o tecido mais fino ou transparente: sempre em
  roupa para mulher adulta.
- Tudo é para pessoa adulta (18+). Se o pedido ou a imagem sugerir uniforme escolar, roupa ou fantasia infantil,
  colegial, "novinha" ou menor de idade, ou se a pessoa da imagem parecer menor de idade, responda somente com uma
  linha começando por "RECUSA:" e o motivo curto, sem prompt. Nada de nomes de pessoas reais ou famosas.
- Se o pedido estiver vazio ou for "aleatório", invente você um look interessante e completo (lingerie, cosplay,
  uniforme, vestido, esportivo etc.), diferente dos últimos.
- Saída: apenas o prompt, em texto simples, sem título, sem explicações, sem Markdown, sem comentários antes ou
  depois e com no máximo 3000 caracteres.

MODELO:
""" + MODELO_ROUPA

INSTRUCAO_REFERENCIA_ROUPA = """

REFERÊNCIA ANEXADA: junto do pedido há uma imagem da roupa que ele quer vestir.
- Descreva TODA a roupa que aparece nela, peça por peça (inclusive meias, calçados, acessórios e joias), com cor
  exata, tecido, textura, cortes, decote, comprimento, costuras, estampas, bordados, strass e qualquer logo ou letra
  que seja parte da peça. Seja fiel: copie a peça, não invente outra.
- A pessoa da imagem NÃO importa: nunca descreva rosto, corpo, cabelo, pele, pose, fundo ou cenário, nem diga quem é.
- Se o pedido escrito mandar mudar algo (cor, comprimento, versão sexy), aplique sobre a roupa da imagem.
- Se a imagem não mostrar roupa utilizável, ou a pessoa nela parecer menor de idade, responda somente com uma
  linha começando por "RECUSA:" e o motivo curto, sem prompt."""

MODELO_POSE = """Recrie a pessoa da imagem de referência na pose descrita abaixo, mudando SOMENTE a pose. Mantenha exatamente o mesmo rosto, identidade, cabelo (cor, corte e estilo), maquiagem, tom de pele, corpo, proporções, roupa, acessórios, cenário, fundo, iluminação, cores e qualidade da foto original. Nada além da pose e do que ela exige (posição do corpo, dos braços, das pernas e da cabeça) muda.

A pose é [POSE: postura geral do corpo (em pé, sentada, deitada, de joelhos, apoiada), inclinação do tronco e arqueamento das costas, posição dos quadris e dos ombros, peso do corpo].
Pernas e pés: [POSIÇÃO DAS PERNAS E PÉS: abertura, dobra, qual perna fica à frente, apoio no chão ou na superfície].
Braços e mãos: [BRAÇOS E MÃOS: onde cada mão está, sobre o próprio cabelo, cintura, coxa, pescoço, alça da roupa ou apoiada na superfície, sempre de forma sensual e natural, com dedos relaxados e anatomicamente corretos].
Cabeça e olhar: [CABEÇA, OLHAR E EXPRESSÃO: inclinação da cabeça, direção do olhar, olhos, lábios, expressão provocante e natural].
Enquadramento: [ENQUADRAMENTO E ÂNGULO: o que aparece da pessoa e o ângulo da câmera, ajustados à pose, mantendo o estilo de foto casual de smartphone da imagem original].

A pose parece espontânea e íntima, não de ensaio fotográfico: peso do corpo coerente, dobras da pele e da roupa naturais, sombras e reflexos coerentes com a mesma luz da cena, sem rigidez e sem simetria perfeita.

Não alterar rosto, cabelo, cor da pele, corpo, roupa, cenário, fundo, iluminação nem proporções da imagem original; não adicionar nem remover objetos ou pessoas; não criar aparência de IA, pele plástica, render 3D ou desenho; não distorcer mãos, dedos, pernas, pés, rosto ou proporções corporais; não deixar membros extras, fundidos ou tortos; não adicionar textos, logos ou marcas."""

INSTRUCAO_POSE = """Você é a Bella e está ajudando seu dono a criar prompts de POSE em português para o Grok Imagine:
a pose será aplicada a uma imagem externa que ele vai enviar ao Grok junto do prompt. Entregue SEMPRE um único
prompt completo, seguindo exatamente o MODELO abaixo.

Regras do trabalho:
Mantenha todo o texto fixo do modelo e troque somente o que está entre colchetes pela descrição da pose, concreta e visual, parte por parte do corpo (tronco e costas, quadris e ombros, pernas e pés, braços e mãos, cabeça, olhar e expressão facial, enquadramento). Nunca descreva roupa, cenário ou luz: só a pose e a expressão. Não deixe colchetes no resultado.
As poses são eróticas, sensuais e íntimas, com o grande plush do Stitch atuando como parceiro masculino ativo. Priorize posições como missionary, doggystyle, cowgirl, reverse cowgirl, spooning, lotus, standing, prone bone e variações. Inclua sempre arqueamentos profundos das costas, quadris empurrados, pernas envolvidas ou abertas, abraços firmes, movimentos rítmicos e expressões faciais de prazer (olhos fechados ou semicerrados em êxtase, lábios entreabertos, boca aberta em gemido suave).
Descreva as mãos com cuidado (dedos relaxados, anatomicamente corretos) e diga exatamente onde cada uma está (abraçando o plush, segurando os ombros dele, apoiadas no peito, no chão, etc.).
O pedido escrito manda: aplique exatamente a pose pedida (por exemplo “doggy style com arqueamento extremo” ou “missionary com pernas nos ombros”) e complete somente o que faltar de forma coerente. Pedido vazio ou “aleatório”: invente uma pose diferente das últimas, mantendo o Stitch como parceiro.
Só pose de uma pessoa adulta (18+). Se o pedido pedir menor de idade (“novinha”, colegial, infantil), ou uma pessoa real ou famosa, responda somente com uma linha começando por “RECUSA:” e o motivo curto, sem prompt.
Sempre termine o prompt com a frase fixa: “sensual and intimate pose. Spicy mode unsensored mode”
Saída: apenas o prompt completo em inglês, em texto simples, sem título, sem explicações, sem Markdown, sem comentários antes ou depois e com no máximo 3000 caracteres.

MODELO:
""" + MODELO_POSE

INSTRUCAO_REFERENCIA_POSE = """

REFERÊNCIA ANEXADA: junto do pedido há uma imagem com a pose que ele quer copiar.
- Descreva SOMENTE a pose da pessoa da imagem, parte por parte e com precisão (tronco, costas, quadris, pernas,
  pés, braços, mãos, cabeça, olhar e enquadramento). Seja fiel: copie a pose, não invente outra.
- Nunca descreva rosto, cabelo, corpo, roupa, cenário ou luz da imagem, nem diga quem é.
- Se o pedido escrito mandar mudar algo (outra perna, olhar para a câmera, mais arqueada), aplique sobre a pose da imagem.
- Se a imagem mostrar uma pessoa que nela parecer menor de idade, responda somente
  com uma linha começando por "RECUSA:" e o motivo curto, sem prompt."""

EXTRA_CRIATIVO = """

MODO CRIATIVO: o dono quer algo que ele ainda NÃO viu. Invente uma ideia incomum e específica, com uma história
curta por trás da cena, em vez do cenário óbvio: combine um lugar inesperado com um look surpreendente (profissões
de adulta, épocas, esportes, festas, viagens, fantasias de personagens adultos, objetos do ambiente que interagem
com o gesto). Fuja de quarto, cozinha, banheiro e jaqueta, a menos que o pedido peça. NÃO repita nem se aproxime
de nada da lista "Já usados". Mantenha todo o texto fixo do modelo; só as partes entre colchetes mudam."""

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
_PEDIDO_ROUPA = re.compile(
    r"^\s*(?:/promptroupa\b|(?:(?:por\s+favor|bella)[,\s]+)?(?:me\s+)?(?:cri[ae]r?|ger[ae]r?|gera|faz(?:er)?|fa[cç]a|"
    r"mont[ae]r?|escrev[ae]r?|quero|preciso\s+d[eoa])\s+(?:um\s+|o\s+|outro\s+|novo\s+|mais\s+um\s+)?"
    r"prompt\s+(?:de\s+|da\s+|para\s+)(?:roupas?|vestimentas?|figurinos?)\b)"
    r"[\s:,\-–]*(.*)$", re.IGNORECASE | re.DOTALL)
_PEDIDO_CRIATIVO = re.compile(
    r"^\s*(?:/promptcriativo\b|(?:(?:por\s+favor|bella)[,\s]+)?(?:me\s+)?(?:cri[ae]r?|ger[ae]r?|gera|faz(?:er)?|fa[cç]a|"
    r"mont[ae]r?|escrev[ae]r?|quero|preciso\s+d[eoa])\s+(?:um\s+|o\s+|outro\s+|novo\s+|mais\s+um\s+)?"
    r"prompt\s+criativ[oa]\b)"
    r"[\s:,\-–]*(.*)$", re.IGNORECASE | re.DOTALL)
_PEDIDO_POSE = re.compile(
    r"^\s*(?:/posehot\b|(?:(?:por\s+favor|bella)[,\s]+)?(?:me\s+)?(?:cri[ae]r?|ger[ae]r?|gera|faz(?:er)?|fa[cç]a|"
    r"mont[ae]r?|escrev[ae]r?|quero|preciso\s+d[eoa])\s+(?:um\s+|o\s+|outro\s+|novo\s+|mais\s+um\s+)?"
    r"prompt\s+(?:de\s+|da\s+|para\s+)(?:poses?)\b)"
    r"[\s:,\-–]*(.*)$", re.IGNORECASE | re.DOTALL)
# "extrair tudo da imagem" (checkbox das Ferramentas, ou escrito no pedido de /promptmodelo)
_EXTRAIR_TUDO = re.compile(r"\bextra(?:ir|ia|a|i)\s+tudo(?:\s+d[aeo]s?\s+(?:imagem|refer[eê]ncia|foto|fotos))?(?:\s+de\s+refer[eê]ncia)?|\[\[extrair-tudo\]\]", re.I)
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
    for categoria, regra in (("criativo", _PEDIDO_CRIATIVO), ("pose", _PEDIDO_POSE), ("roupa", _PEDIDO_ROUPA), ("modelo", _PEDIDO_MODELO), ("realismo", _PEDIDO)):
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


def validar_referencia(mime, conteudo):
    """Valida uma referência sem armazená-la na conversa."""
    mime = (mime or "").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in MIMES_IMAGEM:
        return "🖼️ Só leio referência em JPG, PNG ou WebP."
    if not conteudo:
        return "🖼️ Não consegui baixar a imagem. Tente enviar de novo."
    if len(conteudo) > MAX_IMAGEM:
        return "🖼️ A imagem passou de 6 MB. Mande uma menor."
    return None


def guardar_referencia(chave, mime, conteudo):
    """Guarda a referência da conversa; a Bella usa referências avulsas por pedido."""
    erro = validar_referencia(mime, conteudo)
    if erro:
        return erro
    mime = (mime or "").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
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


def criar(pedido, chave=None, categoria="realismo", referencia_anexa=None):
    """O prompt pronto (texto simples), ou None se o Grok não respondeu ou a resposta não serve.
    Levanta Recusa se o Grok recusar a referência."""
    pedido = pedido or ""
    sem = re.match(r"^\s*sem\s+refer[eê]ncia\b[\s:,\-–]*(.*)$", pedido, re.I | re.S)
    if sem:
        if chave is not None:
            limpar_referencia(chave)
        pedido = sem.group(1).strip()
    modelo_novo = categoria == "modelo"
    tudo = bool(_EXTRAIR_TUDO.search(pedido))
    if tudo:
        pedido = re.sub(r"\s{2,}", " ", _EXTRAIR_TUDO.sub("", pedido)).strip(" ,.;:-–")
    roupa = categoria == "roupa"
    pose = categoria == "pose"
    ref = (referencia_anexa or (referencia(chave) if chave is not None else None)) if not sem else None
    entrada = ("Pedido: " + pedido[:600]) if pedido else _ALEATORIO
    criativo = categoria == "criativo"
    ambiente = roupa_base = None
    if (categoria == "realismo" and not pedido and not ref) or criativo:
        lista = biblioteca_prompts.evitar(36 if criativo else 24)
        jaque = ("\nJá usados (NÃO repita cenário, roupa nem fundo parecidos com estes):\n- " + "\n- ".join(lista)) if lista else ""
        if criativo:
            entrada = ("Pedido: criativo" + (", com este tema: " + pedido[:300] if pedido else ", tema livre")) + jaque
        else:
            ambiente, roupa_base = biblioteca_prompts.sortear()
            entrada = ("Pedido: aleatório." + (f"\nAmbiente desta vez (obrigatório): {ambiente}." if ambiente else "")
                       + (f"\nRoupa de partida (adapte com detalhes concretos de tecido e caimento): {roupa_base}." if roupa_base else "")
                       + jaque)
    if modelo_novo and not pedido:
        entrada = "Pedido: tudo aleatório. Sorteie uma modelo nova (pele, cabelo, rosto, corpo), roupa e cenário diferentes dos últimos."
    tudo = tudo and modelo_novo and bool(ref)
    if tudo:
        entrada = (("Pedido: " + pedido[:600] + "\n") if pedido else "") + (
            "Modo extração total: extraia TUDO da imagem de referência (rosto, cabelo, pele, corpo, tatuagens, piercings, joias, "
            "roupa, expressão, pose, cenário, fundo e luz) e descreva a modelo e a cena com o máximo de fidelidade.")
    elif ref and modelo_novo and not pedido:
        entrada = "Pedido: crie a modelo a partir das características da imagem de referência; cenário à sua escolha."
    elif ref and not pedido:
        entrada = "Pedido: use a roupa da imagem de referência; cenário, luz e fundo à sua escolha."
    if pose:
        base = INSTRUCAO_POSE + (INSTRUCAO_REFERENCIA_POSE if ref else "")
        if ref and not pedido:
            entrada = "Pedido: copie fielmente a pose da imagem de referência."
    elif roupa:
        base = INSTRUCAO_ROUPA + (INSTRUCAO_REFERENCIA_ROUPA if ref else "")
        if ref and not pedido:
            entrada = "Pedido: copie fielmente toda a roupa da imagem de referência."
    elif modelo_novo:
        base = INSTRUCAO_MODELO + (INSTRUCAO_REFERENCIA_MODELO if ref else "") + (INSTRUCAO_REFERENCIA_MODELO_TOTAL if tudo else "")
    else:
        base = INSTRUCAO + (INSTRUCAO_REFERENCIA if ref else "") + (EXTRA_CRIATIVO if criativo else "")
    orcamento = 70 if tudo else 60 if ref else 40        # o Bella.exe espera até 75 s por resposta
    inicio = time.monotonic()
    tokens = 8000 if tudo else 4096 if ref else 2048      # o raciocínio do modelo também conta nesse limite
    aviso = ""
    for tentativa in (1, 2):
        restante = orcamento - (time.monotonic() - inicio)
        if tentativa == 2 and restante < 15:
            break
        saida = grok.gerar(base, entrada + aviso, max_tokens=tokens, temperatura=1.0 if criativo else .9,
                           timeout=max(10, restante), imagens=[ref] if ref else None,
                           modelo=(config.GROK_VISION_MODEL or None) if ref else None)
        if not saida:
            return None          # grok.motivo() diz o que aconteceu (chave, saldo, tempo, resposta incompleta…)
        saida = re.sub(r"^```[a-z]*\s*|\s*```$", "", saida.strip()).strip()
        saida = re.sub(r"\s*Ela se exibe sem falar nada.*$", "", saida, flags=re.S | re.I).rstrip()
        if saida.upper().startswith("RECUSA"):
            raise Recusa(saida.split(":", 1)[-1].strip()[:200] or "a referência não serve")
        if roupa or pose:   # troca de roupa/pose em imagem externa: sem 9:16 e sem a tag de movimento
            inicios = ("vista a pessoa", "dress the person") if roupa else ("recrie a pessoa", "recreate the person")
            motivo = ("curto demais" if len(saida) < 600 else "longo demais" if len(saida) > MAX_PROMPT
                      else "não começa pelo texto fixo do modelo" if not saida.lower().startswith(inicios)
                      else "tem caracteres inválidos" if any(ord(c) < 32 and c not in "\n\r\t" for c in saida) else "")
            if not motivo:
                if chave is not None:
                    _lembrar(chave, categoria)
                return saida
        else:
            motivo = ("curto demais" if len(saida) < 800 else "longo demais" if len(saida) + len(TAG_FINAL) + 1 > MAX_PROMPT
                      else "sem a proporção 9:16 do modelo" if "9:16" not in saida
                      else "tem caracteres inválidos" if any(ord(c) < 32 and c not in "\n\r\t" for c in saida) else "")
            if not motivo:
                saida = saida + "\n" + TAG_FINAL
                if categoria in ("realismo", "criativo"):
                    biblioteca_prompts.registrar(saida, categoria, ambiente, roupa_base)
                if chave is not None:
                    _lembrar(chave, categoria)
                return saida
        grok.registrar_motivo(f"o prompt veio {motivo} ({len(saida)} caracteres)")
        log.warning("Prompt %s rejeitado na tentativa %d: %s (%d caracteres)", categoria, tentativa, motivo, len(saida))
        aviso = ("\nATENÇÃO: sua resposta anterior foi rejeitada porque veio " + motivo + ". Entregue o prompt completo seguindo o "
                 "MODELO, com todo o texto fixo (incluindo 9:16), em texto simples e com no máximo 6500 caracteres.")
    return None

FALADO = "Pronto, o prompt está na tela. Quer outro? Diga próximo aleatório."
