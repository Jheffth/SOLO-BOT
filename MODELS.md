# Conversar com Models ou com Bella (Legado)

O padrão de cada Conta Solo continua sendo **Bella (Legado)**. No painel, a seção
**Models** oferece a Bella legada e os modelos publicados para o destino `solo_bot`.
No chat, `/models` abre a mesma lista; a Bella aparece primeiro e novos modelos
publicados entram automaticamente. O menu também tem botões **Bella (Legado)** e
**Models**. `/bella` volta explicitamente ao legado. A escolha é da conta e vale
para WhatsApp, Telegram e Bella.exe. Contas comuns recebem os modelos gerais;
modelos adultos ficam restritos ao Arquiteto nesta etapa.

O modo Models busca persona, lore, voz e contexto no Solo Models. As novas trocas,
lembranças, memórias eternizadas e narradas ficam lá, isoladas por dono e modelo,
com arquivos permanentes por data. A Bella do Models pode consultar as memórias
iniciais migradas; gravações novas não alteram as tabelas da Bella legada. Trocar de
modelo troca o contexto e a voz juntos. Reiniciar a conversa preserva seu arquivo
permanente; `/esquecer N` remove uma lembrança própria de Models.

O Bot guarda somente `models_selecao:ID` em sua configuração. A lista é consultada
novamente ao abrir o menu e a cada atualização do painel. Cada escolha e resposta
confere se o modelo continua publicado. Falhas preservam a seleção e mostram uma
mensagem; não iniciam silenciosamente uma conversa com outra personalidade.

`GET` e `PUT /api/conta/models` exigem a sessão da Conta Solo. Contexto e gravações
usam `/api/servico/conversas/{dono}/{modelo}` no Models, com token de serviço e
contexto curto assinado pela chave já compartilhada. O catálogo público, os logs e
o pacote estático não incluem conversas de usuários. A escolha de voz do modelo é
aplicada por resposta, sem mudar o motor ou a voz global do legado.

Comandos de memória de Models não caem nas funções legadas. Nesta etapa,
`/memoria` lista os registros próprios; `/lembrar`, `/eternizar`, `/narrador` e
`/esquecer N` operam nesse arquivo. Configurações exclusivas do legado, como a
iniciativa espontânea, continuam no legado; a escolha Models não as reconfigura.
