# Galeria de fotos e vídeos — onde está

A galeria real (fotos e vídeos das modelos, níveis, jogo do agrado, "forçar" do Arquiteto, usuários comuns e APIs) é do projeto
futuro **soDeles**. A semente da especificação está em `SODELES_ESPECIFICACAO_GALERIA.md` (neste repositório).

**O que já existe no Solo Bot e serve ao soDeles:**
- Canal de mídia genérico: campo `midia` nas respostas dos sistemas, validação e entrega em WhatsApp e Telegram
  (`canais/midia.py`, `canais/entrega.py`; contrato em `INTERACAO.md`).
- Persona da Bella: memória (`/lembrar`, `/memoria`), sentimentos e termômetro (`nucleo/bella_estado.py`).

**Regra para quando o soDeles existir:** os comandos de mídia (`/foto`, `/galeria`, `/jogo`, `/forcar`…) são do soDeles e
entram pelo manifesto dele, não no código do hub. A decisão de enviar mídia é sempre do código (nível, agrado, temperatura,
autorização, papel de administrador), nunca de um modelo de linguagem.
