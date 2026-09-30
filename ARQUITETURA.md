# SOLO BOT — Arquitetura

Um bot só (Telegram + WhatsApp) atendendo vários projetos Solo na mesma VPS (Contabo).
Projetos iniciais: **Solo Finances** e **Solo Rotinas**.

## Decisões tomadas (30/09/2026)

- **Canais:** o SOLO BOT assume o **token do Telegram e a instância Evolution do Solo Rotinas**.
  Os vínculos do Finances serão refeitos no bot novo.
- **Roteamento:** **prefixo + modo ativo**. `/fin` e `/rot` trocam o contexto da conversa;
  texto livre vai para o sistema ativo; na dúvida, o bot pergunta.

## Peças

```
Telegram ─┐                          ┌─► solo_finances  POST /interno/bot/mensagem
          ├─► solo_bot (gateway) ────┤
WhatsApp ─┘   canais · vínculo ·     └─► solo_routines  POST /interno/bot/mensagem
(Evolution)   sessão · roteamento
              ▲
              └── POST /interno/enviar  ◄── avisos vindos dos sistemas
```

### solo_bot (novo contêiner, rede `solo-network`)
- Único dono do webhook do Telegram e da instância Evolution.
- Idempotência (canal + id da mensagem), sessão e **modo ativo** por conversa.
- Vínculo: um contato (chat_id / JID) ↔ um usuário **em cada** sistema.
  O código de pareamento continua sendo gerado pela aba Bots de cada sistema.
- Renderiza a resposta neutra `{texto, opcoes}`: botões inline no Telegram,
  lista numerada + escolha pendente no WhatsApp (lógica que hoje está em `conversa.py`/`bot_whatsapp.py`).
- Registro de módulos: novo projeto = uma linha de config (prefixo, nome, URL interna, token).

### Cada sistema
- Mantém o próprio cérebro: `bot/nucleo.py` (Finances) e `motors/conversa.py` (Rotinas).
- Expõe só `POST /interno/bot/mensagem` → `{usuario_id, canal, texto, dados}` → `{texto, opcoes}`.
- Protegido por token de serviço (`BOT_SERVICE_TOKEN`), acessível só pela rede interna.
- Avisos (manhã/tarde/noite, lembretes) passam a chamar `solo_bot /interno/enviar`.

## Migração (sem derrubar nada)
1. Subir `solo_bot` ao lado dos bots atuais.
2. Criar `/interno/bot/mensagem` nos dois backends.
3. Apontar o webhook do Telegram do Rotinas e a Evolution do Rotinas para o `solo_bot`.
4. Refazer os vínculos do Finances no bot novo.
5. Desligar o Telegram e a Evolution/Redis próprios do Finances; remover os webhooks antigos.

## Pendência de segurança
`01 - SOLO ROTINAS/webapp/docker-compose.yml` (serviço `whatsapp`, `DATABASE_CONNECTION_URI`)
ainda carrega a senha do Postgres em texto puro num arquivo versionado. Mover para `.env` e trocar a senha.
