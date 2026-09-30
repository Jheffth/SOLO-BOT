# Integração — o que encaixa em cada sistema

**Aplicado em 30/09/2026:** Solo Finances `9b83424`, Solo Rotinas `0d75014`
(e `7dcfae1`, senha da Evolution fora do compose). Os `PROMPT_*.md` ficam como
registro do que foi pedido. Se esta pasta mudar, copie de novo para os sistemas.

São arquivos prontos para copiar, mais três ajustes pequenos por sistema. Todos estão testados
contra sistemas de mentira em `tests/test_integracao.py`.

## Os dois sistemas

1. Copie `comum/solobot_ponte.py` para a raiz do backend, ao lado de `main.py`.
2. Copie `<sistema>/routers/solobot.py` para `backend/routers/solobot.py`.
3. No `main.py`:

   ```python
   from routers import solobot
   app.include_router(solobot.publico)   # /api/solobot/{status,conectar}
   app.include_router(solobot.interno)   # /interno/bot/*  (sem prefixo /api)
   ```

4. No `.env` do sistema, e **repassado no `docker-compose.yml`**. O Rotinas usa
   lista explícita de `environment:`, e variável que não está na lista não chega
   ao contêiner:

   ```
   BOT_SERVICE_TOKEN=<o mesmo "token" do bloco deste sistema em SOLO_MODULOS>
   SOLO_BOT_URL=https://solobot.duckdns.org
   SOLO_BOT_INTERNO=http://solo_bot:8000
   SOLO_BOT_APP=fin        # ou rot
   ```

5. Na aba **Bots**, um botão:

   ```js
   async function conectarSoloBot() {
     const r = await api.post("/api/solobot/conectar");   // o helper de API do sistema
     location.href = r.url;                                // vai ao Solo Bot e volta
   }
   // e o estado:  GET /api/solobot/status → {conectado, conta, email, canais}
   ```

6. Os avisos (manhã/tarde/noite no Rotinas, fatura no Finances) passam a chamar:

   ```python
   import solobot_ponte
   solobot_ponte.avisar(usuario.id, "☀️ Bom dia! 3 missões hoje.", opcoes)  # opcoes no formato neutro
   ```

   `avisar` nunca levanta exceção. Aviso que falha não derruba o job que o disparou.

   O contrato completo de `avisar` (todos opcionais depois de `texto`):

   | Parâmetro | Para quê |
   |---|---|
   | `opcoes` | botões no formato neutro |
   | `falado` | roteiro para ouvido; sem ele o Solo Bot resume sozinho |
   | `voz` | `True` pede que o aviso seja falado (a Conta Solo decide: Personalizada / Sempre / Nunca) |
   | `valido_ate` | `datetime` com fuso ou ISO 8601 com fuso. Se o aviso vencer enquanto espera o horário de silêncio, é descartado. Use em avisos de prazo |

   ```python
   from datetime import datetime, timedelta
   from zoneinfo import ZoneInfo
   inicio = datetime(2026, 10, 1, 14, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
   solobot_ponte.avisar(u.id, "⏰ Faltam 15 min: Treino", voz=missao.aviso_voz,
                        falado="Faltam quinze minutos para o treino.", valido_ate=inicio)
   ```

   Resposta de `/interno/enviar`: `{entregues, adiados, descartados, vinculado}`. `avisar` devolve
   `True` quando o Solo Bot tratou o aviso (entregou, guardou ou descartou por vencido). Nesses casos
   o sistema **não** cai para outro canal.

## Só no Rotinas: um ajuste de uma linha no `motors/conversa.py`

O motor descobre o hunter pelo `chat_id` (`vinculo.por_origem`). Pelo Solo Bot,
quem prova a identidade é o vínculo da Conta Solo, então o canal já chega com o
usuário. Em `_processar`:

```diff
-    usuario = vinculo.por_origem(db, canal.nome, canal.origem)
+    # O canal do Solo Bot já chega com o hunter provado; os outros descobrem pelo chat.
+    usuario = getattr(canal, "usuario", None) or vinculo.por_origem(db, canal.nome, canal.origem)
```

Isso não muda nada para o Telegram e o WhatsApp atuais. O `CanalWhatsApp` já tem
`self.usuario`, preenchido pelo mesmo `por_origem`.

## Depois da migração

- Finances: remover os serviços `whatsapp` e `redis` do compose e o webhook próprio do Telegram.
- Rotinas: o Telegram e a Evolution passam a apontar para o Solo Bot (painel **Administração →
  Ligar webhook / Gerar QR**). Os routers `bot_telegram.py` e `bot_whatsapp.py` podem ficar
  desligados por um tempo antes de serem apagados.

## Atenção: o número do WhatsApp

O Rotinas já tratava o caso do número do bot ser o celular do próprio dono (mensagens
`fromMe`). O Solo Bot mantém a mesma regra: `fromMe` só passa se for comando, código
`SOLO 123456` ou número de uma lista que o bot acabou de oferecer, **e** se o chat estiver
vinculado. Ainda assim, com o número pessoal, um `/comando` digitado na conversa com
outro usuário vinculado seria lido como dele. Um chip dedicado ao bot elimina esse caso.
