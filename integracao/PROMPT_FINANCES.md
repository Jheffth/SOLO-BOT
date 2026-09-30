# Integração com o Solo Bot — Solo Finances

O Solo Bot (`C:\JEFFERSON\PROJETOS\SOLO BOT`) é o novo bot único de Telegram e WhatsApp para todos os projetos Solo. Cada pessoa tem uma **Conta Solo**, e o Finances se liga a ela **de dentro para fora**: o usuário logado aqui gera um código de uso único, o navegador vai ao Solo Bot, a pessoa confirma e o Solo Bot troca o código com este backend pela rede interna. Leia antes `SOLO BOT/INTERACAO.md` e `SOLO BOT/integracao/LEIA-ME.md`.

## O que fazer

1. **Backend**
   - Copie `SOLO BOT/integracao/comum/solobot_ponte.py` para `webapp/backend/solobot_ponte.py`.
   - Copie `SOLO BOT/integracao/finances/routers/solobot.py` para `webapp/backend/routers/solobot.py`.
   - No `main.py`: `from routers import solobot`, depois `app.include_router(solobot.publico)` e `app.include_router(solobot.interno)`. O `interno` fica **sem** o prefixo `/api`: as rotas são `/interno/bot/*`.
   - Confira que `bot.nucleo.responder(db, canal, id_externo, usuario, texto)` ainda tem essa assinatura e que `Usuario` tem `id`, `nome`, `login` e `ativo`. Se algo mudou, ajuste o router, nunca o núcleo.

2. **Configuração.** O `.env` real fica fora do git. Acrescente ao `.env.example`, só com os nomes:
   `BOT_SERVICE_TOKEN`, `SOLO_BOT_URL`, `SOLO_BOT_INTERNO=http://solo_bot:8000`, `SOLO_BOT_APP=fin`.
   O compose usa `env_file`, então elas chegam ao contêiner sem mudança.

3. **Aba Bots (frontend).** Crie no topo da aba um cartão **"Solo Bot"**:
   - `GET /api/solobot/status` devolve `{disponivel, conectado, conta, email, canais}`.
   - Conectado: mostre "Conectado como {conta} ({email})" e os canais (Telegram/WhatsApp), com um link "Gerenciar no Solo Bot" para `SOLO_BOT_URL/painel`.
   - Não conectado: botão **Conectar ao Solo Bot** → `POST /api/solobot/conectar` → `location.href = resposta.url`.
   - `disponivel: false`: explique que falta configurar o `BOT_SERVICE_TOKEN` no servidor.
   - O pareamento antigo (código de 6 dígitos, QR da Evolution própria) continua abaixo, com a etiqueta **"Canal antigo — será desligado"**. Não apague nada ainda.
   - Siga o visual atual do Finances.

4. **Avisos.** Onde o `bot/avisos.py` envia pelo Telegram ou pelo WhatsApp próprios, tente primeiro `solobot_ponte.avisar(usuario.id, texto)`. Só se ela devolver `False`, caia no envio antigo. Assim nada se perde durante a migração.

5. **Testes.** Crie `tests/test_solobot.py` cobrindo:
   - `/api/solobot/conectar` gera uma URL, e `/interno/bot/resgatar` com o token devolve o usuário.
   - O mesmo código não vale duas vezes.
   - Sem o token `X-Solo-Token`, a resposta é 403.
   - `/interno/bot/mensagem` passa pelo `nucleo.responder`.
   - Usuário inativo devolve `{"desvinculado": true}`.

   Rode a suíte inteira.

6. **Commit.** Um commit só com estes arquivos, com a mensagem "Integração com o Solo Bot (aba Bots, /interno/bot, avisos)". Confira o `git status` antes: nenhum `.env` ou segredo pode entrar.

## Não faça

- Não remova os serviços `whatsapp`/`redis` do compose nem o webhook antigo do Telegram. Isso é a última etapa da migração, depois que o Solo Bot estiver no ar.
- Não escreva nenhum segredo em código, commit ou log.
