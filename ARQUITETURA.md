# SOLO BOT — Arquitetura

Um bot só (Telegram + WhatsApp), com painel web próprio (cadastro, login,
canais, sistemas), atendendo vários projetos Solo na mesma VPS (Contabo).
Projetos iniciais: **Solo Finances** e **Solo Rotinas**.

Como ele conversa e como as contas se ligam: **[INTERACAO.md](INTERACAO.md)**.

## Decisões

| Data | Decisão |
|---|---|
| 30/09/2026 | O SOLO BOT assume o **token do Telegram e a instância Evolution do Rotinas**. Os vínculos do Finances são refeitos. |
| 30/09/2026 | Roteamento por **prefixo + modo ativo** (`/fin`, `/rot`, expira em 30 min). |
| 30/09/2026 | **Conta Solo** é o hub. Os sistemas se ligam a ela **de dentro para fora**, num fluxo *authorization code* (ver INTERACAO.md). Nada de migrar usuários. |
| 30/09/2026 | Os canais (Telegram/WhatsApp) pertencem à Conta Solo, não aos sistemas. |

## Peças

```
Telegram ─┐                            ┌─► solo_finances  /interno/bot/{mensagem,acao,resgatar}
          ├─► solo_bot ────────────────┤
WhatsApp ─┘   conta · canais · vínculo └─► solo_routines  /interno/bot/{mensagem,acao,resgatar}
(Evolution)   sessão · modo · render
   ▲             ▲
   │             └── POST /interno/enviar  ◄── avisos dos sistemas
   └── painel web (cadastro, login, canais, sistemas, admin)
```

```
SOLO BOT/
├── backend/
│   ├── main.py            FastAPI + arquivos estáticos
│   ├── config.py          variáveis de ambiente
│   ├── database.py        modelos (SQLAlchemy)
│   ├── seguranca.py       senha, JWT, tokens, comparação em tempo constante
│   ├── nucleo/
│   │   ├── roteador.py    o cérebro do hub: modo ativo, comandos, pergunta pendente
│   │   ├── modulos.py     registro dos sistemas + cliente HTTP interno
│   │   └── render.py      opções neutras → teclado Telegram / lista WhatsApp
│   ├── canais/            telegram.py · evolution.py (só transporte)
│   └── routers/           auth · conta · conectar · webhooks · interno · admin
├── frontend/              entrar/cadastro · painel · conectar · admin (HTML/CSS/JS, sem build)
├── tests/                 pytest: fluxos de ponta a ponta + adaptadores
├── integracao/            o que encaixa em cada sistema (ver integracao/LEIA-ME.md)
└── Dockerfile · docker-compose.yml · .env.example
```

## Contrato interno (Solo Bot → sistema)

Todos com cabeçalho `X-Solo-Token: <BOT_SERVICE_TOKEN do sistema>`, só na rede interna.

| Rota | Corpo | Resposta |
|---|---|---|
| `POST /interno/bot/resgatar` | `{codigo}` | `{usuario_id, nome}` ou 404 |
| `POST /interno/bot/mensagem` | `{usuario_id, canal, origem, texto}` | `{mensagens: [{texto, opcoes}]}` |
| `POST /interno/bot/acao` | `{usuario_id, canal, origem, dados}` | `{mensagens: [...], curta}` |
| `POST /interno/bot/desvinculado` | `{usuario_id}` | `{ok}` (opcional) |

E no sentido contrário (sistema → Solo Bot):

| Rota | Corpo |
|---|---|
| `POST /interno/enviar` | `{app, usuario_id, texto, opcoes?}` (cabeçalho `X-Solo-Token` do sistema) |

## Migração (sem derrubar nada)

1. Subir o `solo_bot` ao lado dos bots atuais (banco `solo_bot_db` no mesmo `solo_db`).
2. Encaixar `integracao/finances` e `integracao/rotinas` nos backends.
3. Apontar o webhook do Telegram do Rotinas e a Evolution do Rotinas para o `solo_bot`.
4. Cada usuário cria a Conta Solo, liga os canais e conecta os sistemas pela aba Bots.
5. Desligar o Telegram e a Evolution/Redis próprios do Finances e remover os webhooks antigos.

## Subir na VPS

```bash
# 1. banco próprio no Postgres que já existe
docker exec -it solo_db createdb -U admin solo_bot_db

# 2. código em /root/app/solo_bot, .env a partir do .env.example
cd /root/app/solo_bot && cp .env.example .env && nano .env

# 3. subir
docker compose up -d --build

# 4. Caddy (mesmo Caddyfile dos outros)
solobot.duckdns.org {
    reverse_proxy solo_bot:8000
}
```

Depois, crie a conta com o e-mail de `ADMIN_EMAILS` e abra **Administração**:
*Ligar webhook* (Telegram) e *Gerar QR / Reaplicar webhook* (WhatsApp).

## Testes

```bash
pip install -r requirements.txt pytest
python -m pytest -q tests
```

## Pendência de segurança

`01 - SOLO ROTINAS/webapp/docker-compose.yml` (serviço `whatsapp`, `DATABASE_CONNECTION_URI`)
ainda carrega a senha do Postgres em texto puro num arquivo versionado. Mover para `.env` e trocar a senha.
