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

### O que fica de fora da fase 1

- **Áudio.** O Finances já transcreve voz. Na fase 2, o Solo Bot recebe o áudio e
  repassa os bytes ao módulo ativo.
- **SSO nos sistemas** ("Entrar com Conta Solo"), que reaproveita o mesmo fluxo.
