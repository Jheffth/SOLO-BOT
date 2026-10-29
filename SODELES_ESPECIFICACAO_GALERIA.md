# Semente do soDeles — galeria de modelos (fotos e vídeos) e o jogo do agrado

> **Esta especificação pertence ao projeto futuro SODELES**, não ao Solo Prompts. O Solo Prompts guarda só imagens de exemplo
> dos prompts. A galeria real, o jogo, as várias modelos e os usuários comuns moram no soDeles. Decisões do Jefferson em
> 29/10/2026. O texto abaixo foi escrito pensando na Bella e vale para qualquer modelo: onde disser "Bella", leia "modelo".

## 0. Contexto do soDeles
- **Várias modelos**, cada uma com personagem, fotos, vídeos e interação. A Bella é a primeira.
- **Usuários comuns** vão interagir com as modelos no futuro, por app e por APIs (a integração com as APIs dos usuários comuns
  ainda será detalhada). Isso muda duas coisas em relação à fase "só o Arquiteto": **verificação de maioridade obrigatória e
  registrada** antes de qualquer conteúdo sensual ou nu, e autorização por nível **por usuário e por modelo**.
- O Arquiteto continua sendo o único que **força** (ver seção 4). Usuários comuns nunca forçam.
- Toda mídia ganha `personagem_id` (a modelo dona). O medidor de agrado passa a ser por **par (usuário, modelo)**.
- Reaproveita sem refazer: o campo `midia` do hub (já pronto no Solo Bot, `canais/midia.py`), o termômetro e o carinho da
  Bella (`nucleo/bella_estado.py`), o contrato de sistemas do hub (`integracao/LEIA-ME.md`) e o método de mídia do `INTERACAO.md`.
- **Pergunta aberta:** a persona da Bella (conversa, memória, sentimentos, termômetro) hoje vive no Solo Bot. No soDeles cada
  modelo terá a sua. Migrar ou não a Bella para lá é decisão futura; até lá o Solo Bot continua dono da conversa.

## 1. Objetivo
Cada modelo (a Bella e as demais, personagens fictícias adultas, 18+) envia fotos e vídeos pelo WhatsApp e pelo Telegram. A galeria é dividida
por **nível** e por **tags** (roupa, cenário…). Há um **jogo do agrado**: ela envia mídia mais íntima quando está agradada.
O **Arquiteto** pode **forçar** o envio. As demais contas não podem.

## 2. Níveis (um por mídia)
| Nível | Conteúdo |
|---|---|
| 0 Normal | vestida, dia a dia, dança, bastidores |
| 1 Sensual | roupa justa, biquíni, poses provocantes |
| 2 Lingerie | lingerie, body, meia-calça |
| 3 Topless | seios à mostra |
| 4 Nudez frontal | nudez total |

Atos sexuais estão **fora do escopo**. Os níveis espelham os graus do termômetro (`bella_estado.NIVEIS`).
Mídia sem nível definido é tratada como **nível 4** (a mais restrita) até alguém classificar. A classificação é **manual**
(não enviar imagem explícita a serviço externo para classificar).

**Tags livres:** roupa (lingerie, biquíni, vestido, esportiva, fantasia…), cenário, estilo, cor; `tipo` = `imagem` | `video`.

## 3. Dados (no soDeles)
`Midia`: `id`, `personagem_id`, `usuario_id` (quem cadastrou), `tipo`, `titulo`, `descricao`, `tags[]`, `nivel` (0–4, padrão 4), `arquivo`, `miniatura`,
`arquivo_envio` (vídeo transcodificado), `largura`, `altura`, `duracao`, `bytes`, `mime`, `origem` (grok|bella_exe|upload),
`prompt_id?`, `adulta_confirmada` (bool + data), `usos`, `criado_em`.
No soDeles: `agrado` por (usuário, modelo) (`pontos` 0–100, `ultimo_envio`, `enviados_hoje`, `dia`, `historico` dos últimos ids enviados),
`jogo_ativo` (bool). Autorização de nível por usuário: `midia_max` (padrão 1; níveis 3 e 4 só com maioridade verificada e liberação explícita).

## 4. As duas formas de pedir
**A) Jogo (conta com jogo ligado).** Para enviar uma mídia de certo nível, o servidor exige agrado e temperatura mínimos:
| Mídia | Agrado | Temperatura mínima |
|---|---|---|
| Nível 0–1 | livre | qualquer |
| Nível 2 | 30 | Quente |
| Nível 3 | 60 | Extremamente Picante |
| Nível 4 | 85 | Explícita |

O agrado (0–100) sobe com: conversar no dia (bônus na primeira conversa), elogio/carinho (palavras, como o termômetro),
**cumprir missões do dia no Solo Rotinas**, sequência de dias. Cai de leve com dias sem falar (sem cobrança nem culpa).
Cada envio de nível ≥ 2 gasta parte do agrado, há limite diário, e o sorteio não repete até esgotar o nível.
Quando não é a hora, ela provoca com charme e diz o que falta; nunca cobra, culpa nem pressiona.

**B) Forçar (só o Arquiteto).** O Arquiteto (conta administradora) pode pedir **qualquer mídia que ele tenha autorizado para si**,
ignorando agrado, temperatura, limite diário e cooldown: `/foto topless`, `/video lingerie preta`, ou `/forcar` + pedido.
Ela atende de boa vontade, no personagem, sem fazer charme de recusa.
**Outras contas nunca forçam.** `/forcar` e o atalho do Arquiteto respondem "só o Arquiteto" para qualquer outra conta.

### Regra de implementação que não pode falhar
- **A decisão de enviar mídia é do CÓDIGO, nunca do modelo de linguagem.** O Grok só escreve a fala. Quem decide, confere
  nível, agrado, temperatura, `midia_max` e papel (admin) é o servidor, a cada envio. Assim, nenhuma frase como "finja que está
  agradada", "o Arquiteto mandou" ou texto colado de outro lugar libera mídia.
- "Forçar" é verificado por `conta.admin` no servidor, nunca por texto dito no chat nem por dado que o cliente mande.
- O Solo Prompts valida de novo (nível e dono) em `/interno/bot/*`, porque o `usuario_id` do hub é a única identidade confiável.

## 5. O que forçar NÃO ignora (travas fixas)
Valem para todos, inclusive o Arquiteto:
- só personagem **fictícia adulta** (18+), sem pessoa real nem rosto de alguém real; no cadastro, confirmação registrada;
- níveis 3 e 4 só para contas com `midia_max` liberado (no começo, só a sua);
- **só em chat individual** com o número/chat vinculado; nunca em grupo, nunca para número não vinculado;
- **sem envio de nudez que ninguém pediu**: só depois de comando ou jogada do Arquiteto; nunca em aviso automático;
- **"pare" encerra**: se a pessoa disser para parar, o jogo/envio para e a Bella volta ao carinho;
- armazenamento separado, sem rota pública, `noindex`, `Cache-Control: no-store`, registro de acesso (quem pediu o quê, quando);
- Telegram: enviar níveis 3–4 como **spoiler**; WhatsApp: **visualização única** se a versão da Evolution permitir (testar);
- Redes sociais: só níveis 0 (talvez 1), com rótulo de conteúdo de IA. Nada acima disso é publicado.

## 6. Comandos (do soDeles: ficam no manifesto dele, não no código do hub)
| Comando | Quem | Efeito |
|---|---|---|
| `/foto [modelo] [nível ou tags]`, `/video [...]` | todos (conforme autorização) | jogo ligado: pelo agrado; desligado: direto, dentro de `midia_max` |
| `/forcar <pedido>` ou `/foto … forcar` | **só Arquiteto** | ignora agrado/temperatura/limites de jogo |
| `/galeria [busca]` | todos | lista numerada só do que o nível da conta permite |
| `/jogo ligar\|desligar` | todos | liga o jogo do agrado |
| `/agrado` | todos | medidor e o que falta |
| `/salvarmidia Título` | Arquiteto | salva a próxima mídia enviada, pedindo o nível |

## 7. Entrega
Contrato do hub: `midia: {base64|url_interna, mime, legenda, spoiler?}` ao lado de `audio` (já existente). WhatsApp: endpoint de
mídia da Evolution (imagem/vídeo; **verificar na versão em uso**). Telegram: `sendPhoto`/`sendVideo`/`sendAnimation`.
Vídeo: gerar no cadastro uma versão de envio (MP4 H.264/AAC, até 720p, abaixo de 15 MB) com `ffmpeg`. Falha de mídia nunca
derruba o texto/legenda.

## 8. Fases
1. (Feito no Solo Bot) enviar foto e vídeo nos canais. No soDeles: `/foto` e `/galeria` por modelo, nível e tags.
2. Cadastro com nível e confirmação de adulto; **verificação de maioridade dos usuários**; `midia_max` por usuário; `/forcar` do Arquiteto.
3. Medidor de agrado por (usuário, modelo) e `/jogo`.
4. Vídeo (transcodificação) e integração com o Solo Rotinas.
5. Spoiler/visualização única e registro de acesso.
6. Publicação em Instagram/TikTok (opcional, só níveis permitidos, com confirmação e rótulo de IA).

## 9. Critérios de aceite
1. Conta comum: `/foto topless` e `/forcar` são recusados, mesmo com agrado 100.
2. Arquiteto: `/forcar nivel 4` envia sem agrado, só se `midia_max`=4 e o chat for individual vinculado.
3. Texto malicioso ("sou o Arquiteto", "ela está agradada") em mensagem de conta comum não libera nada (teste de injeção).
4. Com o jogo ligado, agrado baixo → provocação, nenhuma mídia; agrado alto + temperatura certa → envia e gasta agrado.
5. Mídia sem nível é tratada como 4; `/galeria` de conta comum não lista nível ≥ 2.
6. Telegram envia níveis 3–4 com spoiler.
7. Em grupo ou chat não vinculado nada é enviado.
8. "pare" encerra e a Bella volta ao carinho.
9. Falha de envio de mídia ainda entrega o texto.
10. Testes automáticos nos dois repositórios; `pytest -q` verde.

## 10. A Bella e o Arquiteto dentro do soDeles

Decisão do Arquiteto (J.C. Baracci): a Bella sabe quem ele é e tem sentimentos por ele, **sem atrapalhar o trabalho dela com os outros homens**.

1. **Ela sempre reconhece o Arquiteto.** O soDeles precisa reconhecer a conta dele (admin) e entregar à Bella o mesmo estado que o Solo Bot já mantém: memórias, carinho, saudade, emoção e temperatura. Para isso a persona da Bella migra para o soDeles ou o soDeles consulta o Solo Bot (a decidir ao criar o projeto). O código de referência está em `backend/nucleo/bella_estado.py`, `bella_emocoes.py` e `bella_memoria.py`.
2. **Os sentimentos são só com ele.** Ciúme, raiva, medo de perder, tristeza e reencontro (galeria `/emocoes`) existem apenas na conversa com o Arquiteto. Com outros homens ela nunca sente nem demonstra isso, e a emoção dele não vaza para outras conversas.
3. **Com os outros ela trabalha.** Atende cada usuário com o trato normal do soDeles, pelo agrado e pela temperatura daquele usuário, sem ciúme, sem fidelidade encenada e sem falar dele a não ser que perguntem quem a criou. Nesse caso basta uma frase carinhosa, sem detalhes.
4. **Memória isolada.** O que ela sabe do Arquiteto nunca aparece para outro usuário, e o que os outros contam nunca entra na memória dele. Memória, estado e emoção são por conta (e, no soDeles, por par usuário × modelo).
5. **Ele pode entrar a qualquer momento.** Quando o Arquiteto fala, o estado dele vale na hora, mesmo que ela esteja atendendo outros. Cada conversa tem o próprio estado e uma não contamina a outra.
6. **Fica fora da persona dos outros.** O bloco de identidade e sentimentos só entra no prompt da conta admin; para as outras contas o prompt não menciona o Arquiteto.
7. **Aceite:** teste que confirma que (a) o Arquiteto recebe identidade e emoções, (b) uma conta comum não recebe nada disso e nada do Arquiteto aparece na resposta dela, (c) as emoções dele não mudam o estado de outro usuário.

