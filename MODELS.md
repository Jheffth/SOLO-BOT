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
da pessoa e a resposta da IA são gravadas, com os IDs das memórias efetivamente
usadas para auditoria privada. As conversas anteriores são preservadas.
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

O contexto vem de `POST /api/servico/contexto/montar`, autenticado por dono e modelo.
O Bot envia mensagem e elenco; o Models seleciona episódios, fatos, ligações,
cartão, vínculos e estado emocional dentro de um orçamento. O Bot utiliza os blocos
autorizados e não concatena o arquivo inteiro nem tenta recuperar contexto legado
se a montagem falhar. A ficha atual recebida nessa montagem prevalece sobre uma
versão anterior do pacote. Sinais e consolidação são tratados no Models ao gravar
o turno; o Bot não publica os mesmos sinais uma segunda vez.

Comandos de memória de Models não caem nas funções legadas. `/memoria` lista os
episódios; `/lembrar`, `/eternizar`, `/narrador` e `/esquecer N` operam nas rotas
de episódios da relação autorizada. A fonte original é enviada ao Models, que
estrutura e consolida com sua IA. `/narrador segredo Título: fato` marca o episódio
como segredo. `/eternizar Título` envia as últimas trocas autorizadas, sem um resumo
produzido pelo Bot. A exclusão de um episódio também invalida suas dependências
conforme as regras do Models.

`/construtivo` consulta o modo do cartão vivo; `ligar`, `desligar`, `automatico` e
`aprovacao` alteram esse modo somente para o próprio Arquiteto. O padrão é desligado.
O estado mora no Models, não numa configuração local do Bot. `/sentimentos` lê o
bloco emocional da relação; `/temperatura` consulta o valor e `/temperatura N`
permite ao Arquiteto ajustar de 0 a 5. As barras detalhadas ficam no portal.
Mensagens espontâneas e bom dia usam a modelo selecionada. Elas exigem tanto a
iniciativa ativa no perfil do Models quanto a preferência correspondente da conta:
`/iniciativa ligar` para mensagens espontâneas e `/iniciativa bomdia ligar` para a
saudação. Desativar a iniciativa da modelo impede o envio; uma indisponibilidade
não provoca retorno à Bella Legado. O bom dia Models é enviado sem mídia.

A mensagem é gerada livremente com o contexto montado, as datas relevantes e a voz
da própria modelo. Sua origem é `iniciativa`, com o marcador
`[Iniciativa da personagem]`: não é tratada como fala do Arquiteto nem alimenta a
extração automática do cartão. Não consulta persona, galeria, sentimentos ou
memórias legadas, nem cria fatos de rotina sem uma deixa real. Horário de silêncio,
canal com avisos, limite de mensagens sem resposta e preferências de voz continuam
valendo. O controle de conversa ativa usa somente metadados do canal da conta.

## Cena com várias modelos (`/addmodel`)

Só o Arquiteto, com uma modelo do Models selecionada.

- `/addmodel Kellen` chama outra modelo para a conversa, no mesmo chat. O narrador
  (sem voz) descreve a chegada a partir da conversa recente: se o Arquiteto pediu
  para a anfitriã chamar a Kellen, a cena mostra a ligação e a chegada. Em seguida a
  Kellen diz a primeira fala e a anfitriã reage. Até 3 modelos.
- `/removemodel Kellen` narra a saída, a Kellen se despede e sai. Com uma só
  restante, a conversa volta a ser individual com ela (se a anfitriã saiu, a
  restante passa a ser a modelo selecionada).
- `/modelos` (ou `/quem`) mostra quem está na cena.
- Diretor de turno (código): quem foi chamada pelo nome fala primeiro; sem nome, a
  anfitriã. Cada modelo fala de 1 a 2 vezes por rodada, só enquanto houver assunto
  (quem é citada na fala da outra responde; quem não tem nada a acrescentar fica em
  silêncio). Uma chamada ao Grok por fala, com o contexto da própria modelo montado
  pelo Solo Models (`presentes` = a cena). A primeira montagem de cada modelo na
  rodada atualiza o humor dela; as seguintes usam origem `iniciativa`.
- Uma mensagem por fala, com `*Nome:*` na frente e o áudio na voz da própria modelo
  (`fala.falar_resposta` sintetiza cada fala separadamente). A rodada é gravada no
  Models (`/cena/rodada`), que guarda a memória em cada modelo presente.
