# SOLO BOT — Como ele conversa e como as contas se ligam

## 1. Contas: a Conta Solo é o hub, os sistemas se ligam a ela

O Finances e o Rotinas continuam com os próprios usuários. Nada é migrado e
nenhuma senha é copiada. O que nasce é a **Conta Solo**: e-mail e senha no
Solo Bot, que é quem fala com as pessoas no Telegram e no WhatsApp.

```
            Conta Solo (solo_bot)
            ├── canais:   Telegram 123456 · WhatsApp 5561…
            ├── Solo Finances → usuario_id 4  ("jefferson")
            └── Solo Rotinas  → usuario_id 1  ("Arquiteto")
```

### O vínculo nasce de DENTRO do sistema (decisão)

1. No Finances (ou no Rotinas), aba **Bots**, o usuário toca em **Conectar ao Solo Bot**.
2. O backend do sistema, que sabe quem está logado, grava um **código de uso único**
   (10 min) amarrado ao `usuario_id` e devolve a URL
   `https://<solobot>/conectar?app=finances&codigo=…`.
3. O navegador abre o Solo Bot. Se não houver sessão, mostra **entrar / criar conta**
   ali mesmo e volta para a tela de consentimento.
4. A tela mostra *"Solo Finances quer se conectar à sua Conta Solo"* com o nome do
   usuário do lado de lá. O usuário confirma.
5. O Solo Bot troca o código **servidor a servidor** (`POST /interno/bot/resgatar`
   pela rede interna, com token de serviço) e recebe `{usuario_id, nome}`.
   O código morre ali.
6. O vínculo é gravado e o navegador volta para o sistema de origem.

Por que assim:

- **O sistema prova quem é o usuário.** O código só sai de uma sessão autenticada
  do próprio sistema, e o Solo Bot nunca vê a senha do Finances nem do Rotinas.
- **O código não serve para nada fora da rede interna.** Quem interceptar a URL
  ainda precisaria do token de serviço para resgatá-lo, e ele é de uso único.
- **É um fluxo OAuth de verdade (authorization code).** O dia em que você quiser
  "Entrar com Conta Solo" no Finances e no Rotinas (SSO), o caminho é o mesmo e
  só inverte o sentido. A unificação completa dos usuários fica disponível sem
  migração forçada.

Regras: uma Conta Solo tem **no máximo um vínculo por sistema**, e um usuário de
um sistema pertence a **uma** Conta Solo. Reconectar troca o vínculo antigo e avisa.

### Canais pertencem à Conta Solo, não aos sistemas

O Telegram e o WhatsApp são ligados **uma vez**, no painel do Solo Bot:

- **Telegram:** botão *Abrir no Telegram* → `t.me/<bot>?start=<token>`. Um toque,
  e o `/start <token>` chega sozinho. Não há código para digitar.
- **WhatsApp:** botão *Abrir no WhatsApp* → `wa.me/<número>?text=SOLO 482913`.
  A mensagem já vai pronta; basta enviar.

Os dois tokens valem 10 minutos e são de uso único, com castigo após 5 erros por
origem (15 min), a mesma defesa dos bots atuais.

## 2. A conversa

### Três estados

| Estado | Quando | O que o texto livre faz |
|---|---|---|
| **Hub** | sem modo ativo | pergunta *"Para qual sistema?"* (ou vai direto se só houver um conectado) |
| **Modo Finances** | após `/fin` ou ao tocar em Finances | vai para o `nucleo.py` do Finances |
| **Modo Rotinas** | após `/rot` ou ao tocar em Rotinas | vai para o `conversa.py` do Rotinas |

- O modo ativo **expira após 30 minutos** sem mensagem e volta ao hub.
- **Responder a um aviso** (manhã do Rotinas, fatura do Finances) ativa o modo
  daquele sistema, e a resposta cai no lugar certo.
- Toda resposta de sistema vem com **selo** na primeira linha: `💰 Finances` ou
  `⚔️ Rotinas`. Quem lê sempre sabe com quem está falando.

### Quem não tem conta

O bot fica **mudo** para quem não tem Conta Solo: não responde, nem baixa áudio. A única exceção é
quem manda um **código de vínculo** (`/start CODIGO` no Telegram, `SOLO 123456` no WhatsApp), que
recebe a confirmação ou o erro. `RESPONDER_DESCONHECIDOS=1` no `.env` volta a mandar boas-vindas.

### Comandos do hub (valem em qualquer modo)

| Comando | Faz |
|---|---|
| `/menu` ou `oi` | cartão inicial: saudação + sistemas conectados como botões |
| `/fin [comando]` | entra no Finances; com argumento, executa e fica no modo |
| `/rot [comando]` | idem para o Rotinas |
| `/sair` | volta ao hub |
| `/conta` | canais e sistemas ligados, com link para o painel |
| `/ajuda` | ajuda do hub; dentro de um modo, a ajuda **do sistema** |

Exemplos:

```
você: /fin gastei 42 no mercado
bot:  💰 Finances
      ✅ Despesa de R$ 42,00 — Mercado …

você: 60 uber                  ← continua no modo Finances
você: /rot hoje                ← troca para o Rotinas e mostra o dia
você: /sair
você: comprei pão 8            ← hub: "Para qual sistema?" [💰 Finances] [⚔️ Rotinas]
```

Com prefixo, o hub reconhece o primeiro termo pelo manifesto: `/fin saldo nubank` envia
`/saldo nubank`, e `/rot hoje` envia `/hoje`. A barra explícita também funciona (`/fin /saldo`).
Frases livres são preservadas, como `/fin recebi 92,60 Uber`. Se o manifesto ainda não estiver
disponível, use a barra explícita para garantir o comando. Respostas completas copiadas do bot
com selos, erros ou recibos são recusadas antes de chegar ao sistema, para que exemplos de ajuda
não sejam executados como pedidos.

**Antes de perguntar, o bot tenta entender** (`nucleo/intencao.py`):

1. **Palavras:** o vocabulário de cada sistema, tirado do manifesto (comandos e exemplos) e de uma
   base fixa ("gastei", "saldo", "rotina", "missão"…). Não custa nada. Se só um sistema casa e ele
   aceita texto livre, lançamentos vão direto, preservando valores e descrições.
   Comandos anunciados também funcionam sem barra: "saldo" e "saldo Uber Conta" viram
   `/saldo` e `/saldo Uber Conta`, inclusive na Bella e em outro modo ativo. Em comandos
   compartilhados, o modo atual decide; sem modo, a intenção precisa resolver a ambiguidade.
   Uma palavra isolada parecida com comando ("saltos" no modo Finances) gera uma sugestão
   para repetir "saldo", sem executar nada. Comandos ocultos não entram nesse reconhecimento.
2. **IA (Gemini):** quando as palavras não bastam, ou quando o destino só entende comandos, ela
   escolhe o sistema e **traduz a frase em comando**: "o que tem pra hoje?" vira `/hoje` no Rotinas,
   "terminei a leitura" vira `/ok leitura` e "qual meu saldo?" vira `/saldo` no Finances.
   Consultas precisam de um comando anunciado; se a IA falhar ou inventar um comando,
   não são encaminhadas como lançamentos. A resposta mostra o que foi entendido
   (`🧭 Entendi: Rotinas · /hoje`).

O mesmo vale **dentro de um modo**. No Rotinas, frases viram comandos. No Finances, que entende texto
livre, a IA entra para consultas naturais ou quando há palavras de outro sistema, mesmo que também haja termos financeiros.
Com confiança alta (pelo menos 0,85), o bot **troca de
sistema sozinho**: dizer "gastei 40 no mercado" no modo Rotinas vai para o Finances. Na dúvida (confiança
abaixo de 0,6), ele pergunta como antes.

No manifesto, `exemplos` preenchido significa que o sistema aceita registros em texto livre,
e esses registros vão como estão. Consultas e comandos literais são traduzidos.
Vazio significa que o sistema só entende comandos, e aí a frase é traduzida.

A mensagem que gerou a pergunta **não se perde**: o bot guarda e a encaminha
assim que o usuário escolhe.

### Botões: um formato neutro, dois desenhos

Os sistemas respondem no formato que o `conversa.py` já usa:

```json
{"texto": "…", "opcoes": [{"titulo": "Banho", "acoes": [{"rotulo": "✅ Concluir", "dados": "ok|r|12"}]}]}
```

- **Telegram:** teclado inline. O `callback_data` vai com o prefixo do sistema
  (`rot:ok|r|12`), e é assim que o toque volta para quem o ofereceu.
- **WhatsApp:** lista numerada (`*1.* ✅ Concluir — Banho`). A escolha fica guardada
  **no Solo Bot** por 10 minutos, é de uso único, e o `2` volta como ação ao sistema.

### Áudio

A pessoa pode mandar áudio no Telegram ou no WhatsApp, e o Solo Bot escolhe um de dois caminhos:

- **Há um único sistema conectado e ele entende áudio** (`"audio": {"recebe": true}` no manifesto; hoje, o Finances): o Solo
  Bot entrega os bytes, e o sistema ouve com o contexto dele. O Finances conhece as contas e pede
  "sim" antes de uma transferência ou de um valor alto.
- **Há vários sistemas conectados, ou o único sistema não entende áudio:** o Solo Bot transcreve (Gemini, com o Grok de reserva)
  e segue como se a pessoa tivesse digitado. O que ele ouviu vai repetido no topo da resposta
  (`🎤 “terminei o treino”`).

Com vários sistemas, a transcrição passa pela mesma análise de intenção do texto, inclusive no
modo Finances. Pedidos de Rotinas podem trocar o modo automaticamente; pedidos financeiros
seguem como texto original com `via_audio: true`, preservando valores e a origem por voz.

**Resposta falada é do Solo Bot, para todos os sistemas** (ElevenLabs, `nucleo/fala.py`).
Falhas de transcrição informam o serviço e uma categoria segura (limite de uso, acesso recusado,
modelo indisponível, conexão, demora ou resposta inválida), sem expor chaves ou o conteúdo do áudio.
Uma transcrição cortada é descartada e passa ao próximo serviço configurado. Falha de conexão com
um sistema e demora na resposta têm mensagens distintas; na demora, confira o resultado no sistema
antes de repetir, porque o pedido pode ter sido processado mesmo sem resposta ao hub.

Na transcrição do hub (incluindo Bella), falhas temporárias do Gemini, como HTTP 503,
recebem uma nova tentativa após uma pausa curta. Persistindo a falha, o mesmo áudio vai
para `GEMINI_AUDIO_MODEL_RESERVA` (padrão: `gemini-3.1-flash-lite`) com a mesma chave.
O principal é `GEMINI_AUDIO_MODEL` (padrão: `GEMINI_MODEL`). São até três pedidos por conta,
com espera de resposta de até 12 segundos por pedido e orçamento de 40 segundos por conta.
Depois entram a chave Gemini reserva e o Grok, se configurados. Chave recusada e limite
de uso não são repetidos nessa conta. A recuperação ocorre somente na transcrição:
o comando transcrito é encaminhado uma única vez ao sistema.

Na Administração → Voz do bot → **Conta de voz**, escolha **Automática** (padrão), **Principal**,
**Secundária** ou outra conta configurada. A escolha é persistente e vale para todos os sistemas,
incluindo avisos e amostras. Manual usa somente a conta escolhida; Automática tenta as contas em
ordem a cada fala e passa à próxima se a anterior falhar, inclusive por falta de créditos.

As chaves continuam apenas no servidor: `ELEVENLABS_API_KEY` (principal),
`ELEVENLABS_API_KEY_SECONDARY` (secundária) e, para novas contas, `ELEVENLABS_API_KEY_3`,
`ELEVENLABS_API_KEY_4`, etc. Após configurar novas chaves, recrie o contêiner para carregá-las.
O painel mostra as contas e seus saldos, nunca as chaves. Ao mudar a seleção de conta, as vozes
escolhidas no painel (bot e Sistema) são limpas, pois vozes clonadas podem pertencer só à conta anterior.
Escolha novamente as vozes na lista da conta selecionada. Na troca automática, se a voz não existir
na próxima conta, o bot escolhe uma voz disponível nela. Uma voz fixada no servidor ou solicitada
explicitamente na amostra é preservada e precisa estar acessível na conta de destino.

A preferência é da Conta Solo: `/voz audio` (padrão: fala quando a pessoa mandou áudio),
`/voz sempre` ou `/voz nunca`, também no painel ("Resposta por voz"). O sistema pode mandar
`falado`, uma versão da resposta feita para o ouvido; o Finances manda. Se não mandar:
- **resposta curta:** o Solo Bot limpa o texto (tira emoji, marcação, selo e o eco "🎤") e fala;
- **lista ou resposta longa:** a Gemini faz um **resumo falado**, de 2 ou 3 frases, a partir do texto
  e dos itens dos botões. Por exemplo, "Você tem quatro missões hoje. O treino já foi. Faltam a leitura e o banho.".
  A lista completa continua indo por escrito.

**Avisos também podem sair em voz** (painel → Avisos → Voz nos avisos):
- **Personalizada** (padrão): fala quando o sistema pede (`voz: true`). No Finances, os avisos em formato
  áudio; no Rotinas, as missões marcadas para voz. O roteiro vem no `falado` do sistema ou, na falta, do resumo
  falado acima.
- **Sempre** / **Nunca**: passam por cima do pedido do sistema.

**Tom do aviso** (`tom`): `"sussurro"` é a voz do Sistema quando cobra (os Ecos do Rotinas). Sai
numa voz própria (admin → Voz do bot → 👁 Voz do Sistema; sem escolha, a voz do bot), com atuação
instável e dramática, e sussurrada de verdade nos modelos expressivos. O texto vai em itálico. A frase
é falada **exatamente como veio**, nunca resumida. Tom que o Solo Bot não conhece é ignorado.

Avisos respeitam o **horário de silêncio**: o que chega na janela espera numa fila e sai quando ela
termina. Aviso com **validade** (`valido_ate`) que vence na fila é descartado, porque um "faltam 15 min"
entregue às 7h da manhã só atrapalha.

Sem modo ativo e com dois sistemas conectados, o áudio é transcrito e o bot tenta identificar
o destino; se não conseguir, pergunta "para qual sistema?". O áudio não é guardado em lugar
nenhum. O limite é de 90 segundos por áudio.

### Siri (iPhone, Apple Watch, CarPlay)

"E aí, Siri, Solo Bot" é **mais um canal** (`siri`), com o mesmo roteador, a mesma intenção e o mesmo modo
ativo. O atalho do app Atalhos dita a fala, faz `POST /api/atalho` com a chave pessoal no cabeçalho
`X-Solo-Chave` e fala o campo `falar` da resposta (ou toca `audio_base64`, a voz do Solo Bot, se
pediu `voz: true`).

- A **chave** nasce no painel (seção Siri), aparece uma vez só e fica guardada só como sha256.
  Trocar invalida a anterior; revogar desliga.
- Não existe vínculo de chat: a origem `siri:<conta>` só é criada depois de conferida a chave.
- **Listas** voltam numeradas, e o próximo pedido "dois" (ou "opção 2") escolhe, com validade curta.
- Avisos **não** passam pela Siri: o iPhone não recebe mensagens empurradas por um atalho.
  Continuam no Telegram e no WhatsApp.
- Freio: 30 pedidos por minuto por conta.
- O nome do atalho é a frase de ativação. "Solo" sozinho a Siri lê como pesquisa (solo = chão):
  use "Solo Bot". Em português, a ativação é "E aí, Siri" (ou "Siri"), não "Ei Siri".

### Bella (Windows)

A Bella é um aplicativo portátil, com janela de conversa e ícone perto do relógio. A tela é HTML/CSS
(`desktop/bella/ui`) num WebView2: a foto da Bella (ou o orbe) com um anel que mostra o estado, a conversa
em balões com opções clicáveis, as configurações numa gaveta e a Mini-Bella sobre a barra de tarefas.
A foto fica só no computador. Gere uma chave
em **Painel → Bella no computador**, cole no aplicativo e clique em **Começar**. O acesso da Bella é independente
da Siri; trocar ou revogar uma chave não afeta os outros canais. No computador, a chave é cifrada
para o usuário Windows; no servidor, fica somente seu hash.

- **Ativar escuta:** uma das até três frases editáveis (padrões: “Olá Bella”, “Oi Bella”, “E aí Bella”) é detectada localmente. Só a frase completa, ao terminar, com confiança em cada palavra ativa a saudação;
  quando terminar e aparecer “Pode falar”, fale o pedido; a
  pausa envia um WAV de até 30 segundos ao hub. O áudio ambiente de espera não é enviado.
- **Ctrl + Alt + B** ou **Falar agora:** grava o pedido sem precisar da chamada. Também aceita texto.
- **Pausar escuta:** desliga a captura e libera o microfone. Fechar a janela mantém o aplicativo
  no ícone; **Sair** encerra. Iniciar com Windows é opcional, marcado pelo usuário.
- **Resposta:** usa a voz ElevenLabs do Solo Bot; se não vier áudio, usa a voz instalada no Windows.
  Durante processamento e reprodução, a escuta não gera pedidos. Interromper voz para a reprodução.
- **Sessão:** o modo Finanças/Rotinas e as opções ficam no canal `bella`, separados do WhatsApp,
  Telegram e Siri. “Dois” escolhe a segunda opção e “sim” responde a uma confirmação do sistema.
- **Aplicativos:** a aba Comandos permite escolher Microsoft Word ou outro executável local.
  Word entende abertura, ditado e criação de texto; reutiliza o documento ativo, preserva
  o conteúdo e não salva automaticamente. Outros programas aceitam somente abertura.
- **Desempenho:** Ativação rápida pula a saudação. Os tempos das etapas ficam visíveis
  nas configurações; o ditado literal e a abertura direta não pedem interpretação por IA.
- **Reentrega:** um identificador de pedido impede executar a mesma chamada duas vezes. Se a resposta
  se perder, confira o resultado no sistema antes de repetir; o aplicativo não reenvia sozinho.

**Saudações da chamada:** há 20 frases fixas com `conta.usuario` (o login Solo; se ausente,
o primeiro nome cadastrado). O aplicativo embaralha e completa o ciclo antes de repetir.
`GET /api/bella/saudacoes` devolve o catálogo da conta autenticada e o perfil da voz ativa;
`POST /api/bella/saudacao` recebe apenas o ID de uma frase desse catálogo. Ambos exigem a
chave da Bella, e a geração tem limite de chamadas. Saudar não altera modo ou opções pendentes.

Na ativação, o cliente prepara os áudios que faltam em segundo plano. Cada frase é sintetizada
uma vez por texto/login, voz, modelo, formato e ajustes de voz, sem Gemini. O MP3 é gravado
atomicamente em `BELLA_AUDIO_DIR`, no volume Docker `bella-audios`, e copiado para o cache
do usuário Windows. Os arquivos sobrevivem a reinícios e deploys; não vão ao Git.
Uma trava impede duas sínteses simultâneas da mesma frase no processo do servidor.

A voz ativa inclui a conta e voz que realmente responderam, inclusive após falta de crédito
na principal. O último perfil bem-sucedido é guardado na configuração; mudar conta, voz,
modelo ou chaves invalida esse perfil. Saudações procuram o cache dessa voz, e não o da voz
anterior. Respostas normais continuam tentando a principal no modo automático; quando ela
volta a responder, a próxima saudação acompanha. Amostras com voz explícita e sussurros não mudam a voz do bot.
O cliente confere o catálogo a cada chamada; sem rede, usa o último perfil conhecido, e uma
chave recusada impede usar o cache. A saudação inteira termina antes da gravação do pedido.

A Bella também oferece controle local de arquivos, em `desktop/bella/Arquivos.cs`.
Pastas permitidas são escolhidas no aplicativo, inicialmente Documentos, Downloads e Área de
Trabalho. Buscar, listar, abrir e criar pastas são diretos; mover, renomear e excluir mostram
uma proposta com caminhos e exigem confirmação de uso único, válida por cinco minutos.
Há reconferência do item e do acesso antes da ação; colisões não substituem arquivos.
O Windows faz a exclusão pela Lixeira, podendo pedir sua confirmação nativa.
Links de pasta não são seguidos; arquivos locais de nuvem usam apenas tags reconhecidas.

Na aba **Comandos**, o usuário cadastra uma frase e o caminho de uma pasta para abrir
diretamente. `ComandosPastas.cs` valida os cadastros; `Arquivos.cs` reconhece a frase
antes da busca geral e reconfere a pasta na abertura. Os cadastros são locais, cifrados
nas preferências, e aceitam edição, teste e remoção. Eles permitem somente abrir a pasta
escolhida; não ampliam as raízes de busca nem concedem acesso para alterar seus arquivos.
Maiúsculas, acentos, pontuação e os verbos “abra/abre/abrir” são equivalentes; frases
duplicadas, respostas de confirmação e números de escolhas não podem ser cadastrados.
“Quero que abra a minha pasta de projetos” e “Gostaria de abrir…” são reconhecidos
diretamente. Outras frases de abertura podem consultar `/api/bella/interpretar-comando`,
que usa `nucleo/comandos_locais.py` e o Gemini. Recebe só pedido, frases e IDs, sem os
caminhos cadastrados. O retorno é validado contra o catálogo recebido; confiança abaixo
de 0,85, ambiguidade, ID desconhecido ou falha não abrem nada automaticamente.
O cliente oferece uma escolha local em vez de mandar esse pedido de pasta ao Finanças.
A interpretação exige chave Bella, tem limite próprio e não executa comandos, grava
cadastros ou altera o modo e as escolhas dos sistemas. A abertura permanece no Windows.

A aba Comandos também oferece tipos **site**, **google**, **youtube** e **maps**, além
de pasta. `Navegador.cs` valida URLs HTTP/HTTPS e codifica os assuntos para abrir os
resultados no navegador padrão, com `UseShellExecute`. Google, YouTube e Maps têm três
comandos básicos de pesquisa, ativos sem cadastro; os modelos da interface preenchem
cadastros pessoais para edição e salvamento. O limite é 50 cadastros pessoais, além dos
três básicos. A configuração anterior sem `Tipo` é lida como pasta, preservando o acesso.
Buscas podem ter um termo fixo ou `{assunto}` na frase. Se faltar assunto, a Bella pergunta
e guarda a continuação local por cinco minutos. Trocar comandos ou cancelar limpa a continuação.
O Gemini recebe frase/ID/tipo e pode devolver o assunto de uma busca variável, limitado
a 500 caracteres; nunca escolhe URL, caminho, motor ou executável. Ambiguidades preservam
o assunto para a escolha. A síntese recebe só códigos fixos `site_aberto`, `pesquisa_aberta`
e `pedir_assunto`. Os resultados são exibidos pelo navegador; o aplicativo não raspa páginas.

Áudio no cliente novo vai primeiro a `POST /api/bella/transcrever` (chave Bella, UUID e WAV).
Essa rota **não roteia, não executa comandos e não altera modo ou escolhas dos sistemas**.
`PedidosWindows` decide localmente: um pedido Solo segue uma vez, como texto original com
`via_audio: true`, para `/api/bella/mensagem`; o cliente antigo pode continuar enviando WAV
diretamente nessa rota. A ação de arquivo roda só no computador. Seu resultado, nomes e caminhos
não vão ao hub. `POST /api/bella/voz-local` aceita somente o código de uma frase fixa e
sintetiza com cache persistente por perfil de voz. Sem síntese, o cliente usa a voz do Windows.
Opções dos sistemas e de arquivos têm identificadores distintos; botões antigos e respostas
numéricas de uma conversa local não confirmam operações pendentes de outro contexto.

A Bella mostra o resultado assim que a operação termina, antes de esperar a síntese.
O cliente novo pede `voz_separada: true` em `/api/bella/mensagem` e recebe um `voz_id`.
`/api/bella/voz-resposta` prepara somente a fala daquela resposta, sem executar o comando
novamente. O identificador vale três minutos, uma vez, vinculado à conta e à chave atual;
o servidor mantém no máximo 256 respostas em memória. Reinício ou falha da voz preserva
o resultado e a fala do Windows. O cliente limita essa espera a 12 segundos (8 nas respostas
locais). Clientes anteriores continuam recebendo texto e áudio juntos.

Identificação de pessoa pela voz, memória geral de conversa e controle geral dos aplicativos
do Windows ainda não fazem parte dela. A precisão da chamada deve ser ajustada ao microfone e ruído.

Em Configurações → Escuta, **Apertar para falar** substitui a chamada por voz por uma
tecla configurável (F8 por 5 segundos inicialmente; permite Ctrl/Alt/Shift e 1–30 segundos).
O microfone fica fechado até terminar a espera. O usuário fala mantendo a tecla e solta
para enviar; silêncio e soltura antecipada não geram pedidos. A gravação é limitada a
29 segundos e só segue ao soltar. Botão de microfone, “Bella” e Ctrl+Alt+B não contornam
essa regra. Texto continua disponível. O atalho funciona em segundo plano, respeita pausa
e exige uma nova pressão depois de responder, trocar a configuração ou interromper a espera.
Na edição das configurações, a ativação fica suspensa. Clientes antigos mantêm a chamada
por voz. Os testes locais usam relógio e microfone simulados, sem capturar áudio do usuário.

Instalação e compilação: [desktop/bella/LEIA-ME.md](desktop/bella/LEIA-ME.md).

### O que fica para depois

- **SSO nos sistemas** ("Entrar com Conta Solo"), que reaproveita o mesmo fluxo de conexão.
- **Roteamento pelo conteúdo**, para o "gastei 40 no almoço" ir ao Finances sem precisar de `/fin`.
