# Galeria da Bella (fotos/vídeos) — onde está a especificação

A especificação completa fica no repositório **Solo Prompts**: `C:\JEFFERSON\PROJETOS\SOLO PROMPTS\ESPECIFICACAO_GALERIA.md`.

O que muda **no Solo Bot**:
- `Resposta.diz(..., midia=)` e `_traduzir`: campo `midia` ao lado de `audio`; envio em `canais/evolution.py` (mídia) e `canais/telegram.py` (`sendPhoto`/`sendVideo`/`sendAnimation`, spoiler) e em `canais/entrega.py`.
- Comandos do hub: `/foto`, `/video`, `/galeria`, `/forcar`, `/jogo`, `/agrado`, `/salvarmidia`, com a decisão de enviar **sempre no código** (nível, agrado, temperatura, `midia_max`, `conta.admin`), nunca pelo modelo.
- Tabelas: `bella_agrado` (e `jogo_ativo`, `midia_max` por conta) em `database.py`; o termômetro e o carinho já existem em `nucleo/bella_estado.py`.
- Regra central: só o Arquiteto (`conta.admin`) força; ninguém mais, nem por texto no chat.
