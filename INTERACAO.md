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

**Antes de perguntar, o bot tenta entender** (`nucleo/intencao.py`):

1. **Palavras:** o vocabulário de cada sistema, tirado do manifesto (comandos e exemplos) e de uma
   base fixa ("gastei", "saldo", "rotina", "missão"…). Não custa nada. Se só um sistema casa e ele
   aceita texto livre, a mensagem vai direto.
2. **IA (Gemini):** quando as palavras não bastam, ou quando o destino só entende comandos, ela
   escolhe o sistema e **traduz a frase em comando**: "o que tem pra hoje?" vira `/hoje` no Rotinas,
   e "terminei a leitura" vira `/ok leitura`. A resposta mostra o que foi entendido
   (`🧭 Entendi: Rotinas · /hoje`).

O mesmo vale **dentro de um modo**. No Rotinas, frases viram comandos. No Finances, que entende texto
livre, a IA só entra quando há palavras de outro sistema, mesmo que também haja termos financeiros.
Com confiança alta (pelo menos 0,85), o bot **troca de
sistema sozinho**: dizer "gastei 40 no mercado" no modo Rotinas vai para o Finances. Na dúvida (confiança
abaixo de 0,6), ele pergunta como antes.

No manifesto, `exemplos` preenchido significa que o sistema aceita texto livre, e aí a frase vai
como está. Vazio significa que o sistema só entende comandos, e aí a frase é traduzida.

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

### O que fica para depois

- **SSO nos sistemas** ("Entrar com Conta Solo"), que reaproveita o mesmo fluxo de conexão.
- **Roteamento pelo conteúdo**, para o "gastei 40 no almoço" ir ao Finances sem precisar de `/fin`.
