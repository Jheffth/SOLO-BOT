# Conversar com Models ou com Bella (Legado)

O padrão de cada Conta Solo continua sendo **Bella (Legado)**. No painel, a seção
**Models** oferece a Bella legada e os modelos publicados para o destino `solo_bot`.
No chat, `/models` abre a mesma lista; a Bella aparece primeiro e novos modelos
publicados entram automaticamente. O menu também tem botões **Bella (Legado)** e
**Models**. `/bella` e `/safada` abrem a conversa escolhida sem trocar o modelo;
`/bella legado` volta explicitamente ao legado. A escolha é da conta e vale
para WhatsApp, Telegram e Bella.exe. Contas comuns recebem os modelos gerais;
modelos adultos ficam restritos ao Arquiteto nesta etapa.

O modo Models busca persona, lore, voz e contexto no Solo Models. As novas trocas,
lembranças, memórias eternizadas e narradas ficam lá, isoladas por dono e modelo,
com arquivos permanentes por data. A Bella do Models pode consultar as memórias
iniciais migradas; gravações novas não alteram as tabelas da Bella legada. Trocar de
modelo troca o contexto e a voz juntos. Reiniciar a conversa preserva seu arquivo
permanente; `/esquecer N` remove uma lembrança própria de Models.

Todas as mensagens de conversa, inclusive perguntas de idade, são respondidas
livremente pela IA. Antes de responder, ela recebe a ficha completa e atual da
personagem: nascimento, idade calculada com data de referência, identidade,
aparência, gostos, personalidade e comportamento. A ficha vem novamente do Solo
Models a cada mensagem. Os fatos atuais prevalecem sobre descrições ou respostas
antigas contraditórias; a personalidade e o contexto autorizado da relação dão
forma à resposta, sem frases prontas e sem inventar dados ausentes.

A ficha entra como instrução explícita fora do JSON da persona e é reforçada junto
da mensagem atual, depois do histórico. Esse reforço é interno: só a fala original
da pessoa e a resposta da IA são gravadas. As conversas anteriores são preservadas.
A idade não possui tratamento especial por palavra-chave nem resposta automática.
Essa regra pertence ao modo Models; não altera a Bella Legado.

O Bot guarda somente `models_selecao:ID` em sua configuração. A lista é consultada
novamente ao abrir o menu e a cada atualização do painel. Cada escolha e resposta
confere se o modelo continua publicado. Falhas preservam a seleção e mostram uma
mensagem; não iniciam silenciosamente uma conversa com outra personalidade.

A escolha não expira com a sessão de conversa. `/menu`, `/sair`, `/bella` e
`/safada` preservam o modelo escolhido. Somente a opção explícita Bella (Legado),
no painel/menu, ou `/bella legado` limpa a seleção Models. Uma falha ao consultar
essa preferência retorna indisponibilidade; não é interpretada como escolha do
legado. O painel descarta respostas de atualização anteriores à última escolha.

Na conversa Models ativa, cumprimentos como “Oi?” são mensagens para o modelo;
`/menu` e `/sair` continuam abrindo o hub. O histórico enviado ao provedor alterna
mensagens com papel `user` e `assistant`, conservando o texto de cada participante
e a ordem das trocas, inclusive quando a conversa já contém histórico salvo.

`GET` e `PUT /api/conta/models` exigem a sessão da Conta Solo. Contexto e gravações
usam `/api/servico/conversas/{dono}/{modelo}` no Models, com token de serviço e
contexto curto assinado pela chave já compartilhada. O catálogo público, os logs e
o pacote estático não incluem conversas de usuários. A escolha de voz do modelo é
aplicada por resposta, sem mudar o motor ou a voz global do legado.

Comandos de memória de Models não caem nas funções legadas. Nesta etapa,
`/memoria` lista os registros próprios; `/lembrar`, `/eternizar`, `/narrador` e
`/esquecer N` operam nesse arquivo. Configurações exclusivas do legado, como a
iniciativa espontânea, continuam no legado; a escolha Models não as reconfigura.
