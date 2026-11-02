# Prints de corrida nos canais

WhatsApp, Telegram e Bella.exe reconhecem prints do Strava e registram as métricas no Solo Rotinas. Corrida é o padrão escolhido pelo Arquiteto. Não é preciso entrar no modo Rotinas antes de enviar o print.

## Como usar

- Conecte a conta do Rotinas ao Solo Bot na guia Bots do Rotinas. Os canais devem estar vinculados à mesma Conta Solo.
- Envie o print do Strava, sozinho ou com uma legenda. Prints como o exemplo “Trilha matinal” são registrados automaticamente; a resposta mostra data, distância, duração e total do dia.
- Para corrigir a data no envio, use `/rot treino 01/11/2026`. Para mudar a modalidade: `/rot treino caminhada` ou `/rot treino 01/11/2026 ciclismo`.
- Hoje/Ontem no print usam a data de envio da mensagem no fuso do aplicativo, mesmo se o processamento ocorrer depois da meia-noite. Uma data explícita na legenda prevalece. Sem data reconhecível, o bot pede uma legenda com a data e não grava.
- Consulte e edite o histórico e as metas na guia **Corrida e exercícios**.

## Separação das imagens

Pedidos explícitos de prompt (`/prompt`, `/promptmodelo`, `/promptroupa`, `prompt dessa roupa` etc.) seguem o fluxo de prompts. O botão Criar prompt e as opções de extração da Bella também são pedidos explícitos.

Nos demais anexos, o Solo Bot consulta o Rotinas antes de guardar a imagem como referência. O Rotinas identifica a marca Strava com rótulos esportivos; só registra quando distância e tempo estão legíveis. Se confirmar que não é Strava, o fluxo anterior de referências continua. Um print incompleto ou uma falha de leitura nunca alimentam o cache de prompts nem o Solo Prompts.

A Bella atualizada envia anexos sem legenda com um pedido neutro. A frase automática do executável anterior também é reconhecida, permitindo compatibilidade com o backend novo. Sem vínculo ao Rotinas, a identificação pode funcionar, mas não há gravação até conectar a conta.

## Contrato e privacidade

`POST /interno/bot/imagem` no Rotinas exige `X-Solo-Token`. Corpo: `usuario_id?`, `canal`, `origem`, `imagem_base64`, `mime`, `legenda?`, `enviado_em?` (ISO com fuso). O hub resolve o usuário remoto pelo vínculo da Conta Solo; não aceita um dono de treino escolhido na legenda. Sem `usuario_id`, a chamada só identifica o anexo e orienta a conexão.

Resposta: `{tratado, estado, mensagens}`. Apenas `tratado: false` permite seguir ao fluxo de prompts. Estados tratados incluem registrado, duplicado, incompleto, sem_vinculo, invalido e indisponivel. Mensagens usam o formato neutro dos canais. O registro é propriedade do Rotinas, que aplica as mesmas validações do cadastro web e recalcula métricas e metas.

A imagem permanece temporária no OCR e não entra na história da Bella, no acervo de prompts ou em logs de conteúdo. A atividade do hub registra somente “print de treino”, sem métricas ou localização.

A tabela `importacoes_treino` do Rotinas impõe assinatura única por usuário, data, distância e duração, além da proteção pelo hash do arquivo. Isso evita somar novamente um treino recomprimido por outro canal. Dois treinos distintos com exatamente os mesmos números e data devem ser cadastrados manualmente. Excluir uma atividade exclui sua assinatura; editar não libera reenvio do original.

## Publicação e testes

Publique Solo Bot e Solo Rotinas juntos. O Rotinas precisa da imagem com Tesseract português/inglês da versão 1.10.0. O contrato novo não exige alterações no Solo Finances. Atualização da Bella: `desktop/bella/Compilar.ps1 -SemDownload -PrepararAtualizacao`.

- Solo Bot: `python -m pytest -q tests`.
- Rotinas: `python -m pytest -q test_treinos.py test_treinos_bot.py`, mais `test_solobot.py` e `test_bot_conversa.py` em processos separados com bancos temporários.
- Interface: `node tests/test_bella_treinos_ui.cjs` e os testes existentes de prompts/imagens.
- Bella: compilação executa a suíte interna sem microfone.


Validação desta entrega: 730 testes do Solo Bot e 63 testes de métricas/importação do Rotinas aprovados; comandos/manifesto do Rotinas e testes das interfaces de treino, prompt e imagens aprovados. A Bella foi compilada com a suíte interna aprovada, em uma pasta de atualização separada. O print real foi reconhecido e registrado corretamente; três recompressões produziram uma única atividade. Os testes usaram contas e bancos temporários, sem envio de mensagens reais aos canais. O ambiente temporário de OCR foi removido após a validação.
