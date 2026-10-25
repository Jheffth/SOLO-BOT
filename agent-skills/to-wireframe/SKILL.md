---
name: to-wireframe
description: >-
  Cria wireframe ASCII tipado de uma imagem de interface, com regiões,
  hierarquia e textos legíveis. Use em to-wireframe format=ascii ou como
  dependência de img-to-html para planejar uma recriação HTML.
---

# To Wireframe — implementação local compatível

Criada para suprir a dependência descrita em img-to-html; não é a versão
original de rtadewald nem implementa recursos além dos descritos aqui.
Entrada: image, output, format=ascii. Peça imagem se faltar. Inspecione
visualmente. Não meça pixels, crie recortes, execute OCR externo ou gere arte/CSS.

Identifique regiões, organização relativa e hierarquia pai/filho. Toda caixa
recebe identificador: nav, hero, card, card2 etc. Mesmo id significa mesmo
tipo visual/classe; tipos diferentes recebem ids diferentes. Preserve
cards-filho como caixas aninhadas. Use tags:
- [h1: texto], [h2: texto], [h3: texto]: títulos.
- [t1: texto], [t2: texto], [t3: texto]: famílias de texto.
- [btn: texto], [btn-active: texto]: botão e navegação selecionada.
- [lnk: texto]: link comum, nunca navegação ativa.
- [ico: nome], [img: nome], [av: nome]: assets de ids estáveis.
- [input: rótulo]: campo; [illegible: localização]: texto ilegível.

Transcreva apenas texto legível, sem completar por suposição. Use caixas
ASCII com +, - e |, largura suficiente para tags inteiras. Não finja escala
medida. Faça uma única revisão de labels, hierarquia, cards-filho, tipos e
texto. Salve UTF-8 no output solicitado. Não insira plano/técnicas/etapas nos
ids nem no arquivo. A skill chamadora apresenta o plano e aplica seu gate.
Correções estruturais regeneram o mesmo arquivo com a mesma referência.
