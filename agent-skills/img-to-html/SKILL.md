---
name: img-to-html
description: >-
  Recria um mock de UI como HTML, CSS e JS estáticos, com wireframe tipado,
  fundo, componentes e fontes, assets nativos e revisão final em etapas.
  Use quando o usuário mencionar img-to-html ou pedir para recriar uma
  interface a partir de uma imagem como HTML.
---

# Img → HTML

Transforme PNG/JPG/WebP de uma interface em HTML fiel. Peça a referência se
faltar; aceite anexo, caminho ou URL. Saída: `design-systems/<slug>/`, com
slug kebab-case derivado do arquivo/contexto ou informado pelo usuário.
O entrypoint é exatamente `index.html`.

## Componentes

Use `to-wireframe` na etapa 1. Se não estiver no catálogo, leia a dependência
incluída em `../to-wireframe/SKILL.md`. Ela é uma implementação local
compatível, não uma cópia verificada do upstream.
Use a ferramenta nativa `image_gen.imagegen` para imagens, sem OpenRouter,
API keys, gpt2, uv ou scripts externos de geração. Leia
`references/native-images.md` antes da primeira geração nas etapas 2, 3 ou 4.
`find-font` é opcional, com fallback visual descrito abaixo.

## Pipeline e gates

1. Referência → to-wireframe format=ascii → wireframe.txt e plano.
2. Fundo completo com CSS e/ou imagens.
3. Estrutura, componentes, seus fundos e fontes.
4. Assets restantes gerados nativamente, se houver.
5. Revisão final integrada.

Ao terminar cada etapa, mostre caminho e prévia/screenshot quando disponível;
pergunte se está correto ou o que mudar e pare. Só avance após confirmação
explícita (“aprovado”, “pode seguir”, “ok”). Correções exigem nova apresentação
e aprovação. Aprovar o plano não substitui os gates de implementação.
Instruções explícitas do usuário podem alterar esse fluxo. Gates aplicam-se
à execução de um mock, não à instalação/manutenção da skill. Se não houver
assets restantes, registre no plano e omita a etapa 4.

## Arquivos e stack

- `reference.[ext]`: cópia da entrada.
- `wireframe.txt`: contrato canônico.
- `index.html`: estrutura, textos e controles.
- `assets/styles.css`: todo o CSS.
- `assets/app.js`: somente para comportamento real.
- `assets/crops/{id}.png`: recortes da referência.
- `assets/{id}.png`: mídias finais, ou outra extensão real apropriada.

HTML, CSS e JS separados. Sem build, bundler, framework, node_modules,
Tailwind ou CDN de framework. Abra index.html diretamente; adapte a abertura
ao sistema operacional. Use link para assets/styles.css no head e, somente
se necessário, script externo assets/app.js com defer. Não use style/script
inline ou atributos style. Use CSS único por padrão; acima de ~1500 linhas,
pode separar por região e adicionar links. assets/ é a única pasta auxiliar.
Use custom properties no :root para cores, radius, sombras e tipografia.
Regiões viram classes; tags tipadas viram utilitários; mesmo id = mesmo
visual. Conteúdo repetido fica no HTML, sem loops JS para gerar markup.
Caminhos relativos. React/Vite somente se solicitado explicitamente.

## Etapa 1 — Wireframe ASCII tipado e plano

Crie a pasta de saída e copie a imagem para reference.[ext]. Leia/invoque
to-wireframe com format=ascii, image=design-systems/<slug>/reference.[ext]
e output=design-systems/<slug>/wireframe.txt. Não gere SVG. Vocabulário,
aninhamento e revisão estrutural pertencem à dependência. Não altere seu
resultado diretamente: correções voltam para ela com mesma referência/formato.

Junto do wireframe, apresente tabela curta de região, etapa e técnica;
agrupe regiões iguais. Não adicione plano ao ASCII, ids ou textos da UI.

| Região | Etapa | Técnica |
| --- | --- | --- |
| Fundo e arte decorativa | 2 | CSS, imagem ou camadas |
| Nav, hero e cards | 3 | HTML/CSS, fontes antes do ajuste fino |
| Fundo ilustrado de componente | 3 | Imagem e CSS com a superfície |
| Área de mídia | 3 / 4 | Estrutura na 3; conteúdo na 4 |
| Ícones e avatares | 4 | Assets nativos baseados nos recortes |
| Tela completa | 5 | Comparação integrada |

Escolha CSS para cores/gradientes/formas simples, imagens para arte/texturas
complexas, camadas para ajustes independentes. Fundo único também é válido.
Preserve texto/controles em HTML. Classifique imagens pela função: fundo da
tela na 2; fundo de componente na 3; conteúdo/ícone/avatar na 4. Não aprove
superfície sem seu fundo essencial. Não recorte/gere assets nesta etapa.
Revise uma vez cobertura das regiões e distinção entre fundos e assets
restantes; mostre wireframe e plano no mesmo gate.

## Etapa 2 — Fundo completo

Após aprovação do wireframe/plano, crie index.html mínimo com link CSS e
body vazio; styles.css com reset curto e :root. Faça o fundo conforme o
plano: CSS, imagem única ou composição. Gere agora as imagens essenciais
usando o procedimento nativo, sem adiar para a etapa 4. Aguarde todas as
camadas necessárias antes de compor. Sem nav/cards/conteúdo; elementos
decorativos, pseudo-elementos e backgrounds são permitidos. Ajuste posição,
escala, recorte, transparência e mistura. Compare no navegador. Gate.

## Etapa 3 — Estrutura, componentes e fontes

Implemente estrutura e textos do wireframe: nav/topbar/sidebar primeiro,
depois tipos de card e demais regiões. Fundos dos componentes entram junto,
inclusive suas imagens. Um gate no final.

Para cada tag distinta, determine família/peso antes de ajustes finos.
Se find-font estiver disponível, use crop de uma linha com text= case-sensitive;
caso contrário, escolha a Google Font mais próxima visualmente e informe a
aproximação. Use link Google Fonts ou @font-face no CSS e aplique família/peso
às classes. Mesmo id de tag = mesma tipografia. Confirme carregamento antes
de ajustar quebras, dimensões ou espaçamentos. Google Fonts exige rede;
prefira fontes locais disponíveis se a saída precisar funcionar offline.

Itere medindo: pixels de cor; ângulo/stops dos gradientes; glass/opacidade;
bordas/rim light; glow e sombras externas/inset; radius/padding/espaçamento;
tamanho, altura de linha e tracking. Por superfície: crop ou comparação lado
a lado, amostragem de pixels, markup/classe, valores reutilizáveis em :root,
screenshot e ajuste. Só assets da etapa 4 ficam como placeholders, com
dimensões reservadas. Fundos e fontes devem estar completos. Gate.

## Etapa 4 — Assets restantes com geração nativa

Implemente [ico:], [img:], [av:] e demais assets previstos. Preserve fundos
aprovados; não regenere apenas para cumprir esta etapa. Prepare recortes e
siga references/native-images.md, usando imagegen nativo sem OpenRouter.
Mantenha destinos separados e aguarde conclusão real antes de integrar.
Compare o conjunto na composição e aplique o gate da etapa, sem aprovação
extra por arquivo. Sem pendências, omita a etapa conforme o plano.

## Etapa 5 — Revisão final integrada

Compare screenshot completa com referência no mesmo viewport, com fontes
e mídias carregadas. Confira cobertura do wireframe/plano, sobreposição,
recortes, alinhamentos, quebras e espaçamentos. Verifique caminhos relativos
e comportamentos reais. Informe aproximações/pendências. Mostre tela completa
e arquivos finais. Gate. Não adie a escolha de fontes/fundos para cá.

## Não fazer

- Pular gates ou adiantar etapas sem autorização explícita.
- Medir pixels, recortar, executar OCR externo ou gerar arte na etapa 1.
- Inventar textos ilegíveis; fazer caixas sem região; achatar cards-filho.
- Marcar nav ativo como link; use botão ou variante.
- Substituir por Lucide/placeholder parecido um asset que o plano pede gerar.
- Usar CSS/JS inline, criar package.json ou espalhar auxiliares fora de assets/.
- Declarar asset salvo, geração concluída ou fidelidade perfeita sem verificar.

Origem: texto fornecido pelo usuário de rtadewald/skills/img-to-html.
Consulte ../INSTALLATION.md para proveniência e limites da instalação.
