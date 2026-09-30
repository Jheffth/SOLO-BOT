# Integração com o Solo Bot — Solo Rotinas

O Solo Bot (`C:\JEFFERSON\PROJETOS\SOLO BOT`) é o novo bot único de Telegram e WhatsApp para todos os projetos Solo, e **assume o token do Telegram e a instância Evolution que hoje são do Rotinas**. Cada pessoa tem uma **Conta Solo**, e o Rotinas se liga a ela **de dentro para fora**: o hunter logado aqui gera um código de uso único, o navegador vai ao Solo Bot, a pessoa confirma e o Solo Bot troca o código com este backend pela rede interna. Leia antes `SOLO BOT/INTERACAO.md` e `SOLO BOT/integracao/LEIA-ME.md`, e siga o `AGENTS.md` deste repositório (cofre, segredos, `git add -f` nomeado).

## Antes de tudo

O `RETOMAR_AQUI.md` descreve trabalho **não commitado e não testado** (o portão, o interior da dungeon, o medidor). **Não misture** esse trabalho com esta integração. Faça o commit desta tarefa adicionando **só os arquivos dela, pelo nome**. Se algum arquivo desta tarefa já tiver alterações pendentes daquele trabalho (o `main.py`, por exemplo), avise o Arquiteto antes de commitar.

## O que fazer

1. **Backend**
   - Copie `SOLO BOT/integracao/comum/solobot_ponte.py` para `webapp/backend/solobot_ponte.py`.
   - Copie `SOLO BOT/integracao/rotinas/routers/solobot.py` para `webapp/backend/routers/solobot.py`.
   - No `main.py`: `from routers import solobot`, depois `app.include_router(solobot.publico)` e `app.include_router(solobot.interno)`. O `interno` fica **sem** o prefixo `/api`: as rotas são `/interno/bot/*`.
   - **Uma linha no `motors/conversa.py`**, em `_processar`:
     ```diff
     -    usuario = vinculo.por_origem(db, canal.nome, canal.origem)
     +    # O canal do Solo Bot já chega com o hunter provado; os outros descobrem pelo chat.
     +    usuario = getattr(canal, "usuario", None) or vinculo.por_origem(db, canal.nome, canal.origem)
     ```
     O `CanalSoloBot` tem `nome = "solobot"`. Confira se a coluna `canal` de `AtoBot` e de `EscolhaPendente` aceita esse valor (tamanho, enum, check). O `/desfazer` depende disso.

2. **Configuração.** Acrescente ao `.env.example`, só com os nomes:
   `BOT_SERVICE_TOKEN`, `SOLO_BOT_URL`, `SOLO_BOT_INTERNO=http://solo_bot:8000`, `SOLO_BOT_APP=rot`.
   **E repasse as quatro na lista `environment:` do serviço `api` no `docker-compose.yml`.** Este compose não usa `env_file`, e variável fora da lista não chega ao contêiner (o comentário "ESTA LISTA FALTAVA INTEIRA" explica o porquê).

3. **Aba Bots (frontend).** Crie no topo da aba um cartão **"Solo Bot"**, no visual do Sistema:
   - `GET /api/solobot/status` devolve `{disponivel, conectado, conta, email, canais}`.
   - Conectado: mostre "Conectado como {conta}" e os canais, com um link para `SOLO_BOT_URL/painel`.
   - Não conectado: botão **Conectar ao Solo Bot** → `POST /api/solobot/conectar` → `location.href = resposta.url`.
   - O pareamento antigo continua abaixo, com a etiqueta **"Canal antigo — será desligado"**.

4. **Avisos.** Em `varrer_avisos`, `notificar_manha`, `notificar_tarde` e `notificar_noite` (em `routers/bot_telegram.py`) e no que o WhatsApp próprio envia, tente primeiro `solobot_ponte.avisar(usuario.id, texto, opcoes)`. As opções vão no formato neutro que o `conversa.py` já usa. Só se ela devolver `False`, caia no envio antigo. Um aviso não pode sair duas vezes: se o Solo Bot entregou, o caminho antigo não envia.

5. **Testes.** Crie `test_solobot.py` e adicione-o com `git add -f` nomeado. Cubra:
   - O código de conexão é gerado, resgatado com o token e não vale duas vezes.
   - Sem token, a resposta é 403.
   - `/interno/bot/mensagem` com `/hoje` devolve texto e opções vindos do motor real.
   - `/interno/bot/acao` com `ok|r|<id>` conclui a missão do hunter certo e recusa a de outro hunter.
   - O Telegram e o WhatsApp antigos continuam funcionando depois do ajuste em `conversa.py`.

   Rode a suíte do backend inteira.

6. **Commit.** Um commit só desta tarefa, com a mensagem "Integração com o Solo Bot (aba Bots, /interno/bot, avisos)".

## Não faça

- Não desligue o `bot_telegram.py`/`bot_whatsapp.py` nem mude o webhook do Telegram ou da Evolution. Quem vai apontá-los para o Solo Bot é o painel de Administração dele, na hora da virada.
- **Aproveite para corrigir a pendência de segurança:** no `docker-compose.yml`, o serviço `whatsapp` tem a senha do Postgres em texto puro em `DATABASE_CONNECTION_URI`. Troque por `${EVOLUTION_DATABASE_URI}` vindo do `.env`, acrescente o nome ao `.env.example` e avise o Arquiteto que a senha precisa ser trocada, porque ela está no histórico do git. Faça um commit separado para isso.
