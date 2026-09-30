# Regras para agentes neste repositório (Solo Bot)

Vale para qualquer assistente: Claude, Codex, Antigravity. Leia `ARQUITETURA.md` e `INTERACAO.md` antes de mudar algo.

## Comandos de um sistema NÃO se criam aqui

A lógica de cada comando mora no sistema dono dele:
- Solo Finances → `webapp/backend/bot/nucleo.py` (passo a passo: `BOT_COMANDOS.md` daquele repo)
- Solo Rotinas → `webapp/backend/motors/conversa.py` (passo a passo: `BOT_COMANDOS.md` daquele repo)

O Solo Bot descobre os comandos pelo `bot_manifesto.json` de cada sistema, sozinho
(POST /interno/manifesto ao subir o sistema + busca a cada 10 min). Pediram "comando
novo no bot do Finances/Rotinas"? O trabalho é NO REPOSITÓRIO DO SISTEMA, não aqui.

## O que muda aqui

Só o que não pertence a nenhum sistema:
- sistema novo (bloco em `SOLO_MODULOS` + `integracao/`);
- comando que junta sistemas (ex.: `/resumo`), em `backend/nucleo/roteador.py`;
- recurso de canal (voz, novo aplicativo) em `backend/canais/` e `backend/nucleo/voz.py`;
- o jeito de conversar do hub (`/menu`, `/sair`, `/conta`, modo ativo).

Mudou o contrato com os sistemas (`integracao/`)? Copie de novo para o Finances e o Rotinas
e anote em `integracao/LEIA-ME.md`.

## Sempre

- `python -m pytest -q tests` antes de commitar.
- Commit com `git add` nomeado. Nunca `.env`, `temp_env.txt` ou scripts com senha.
