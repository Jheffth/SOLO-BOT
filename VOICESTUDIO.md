# VoiceStudio como motor secundário do Solo Bot

O ElevenLabs permanece em primeiro lugar, incluindo o modelo Flash e as contas
reservas já existentes. O VoiceStudio só é chamado quando essa cadeia falha.
Uma resposta bem-sucedida do ElevenLabs não faz nenhuma chamada ao VoiceStudio.
Sem a configuração abaixo, o comportamento anterior permanece igual.

## Configuração no backend do Solo Bot

Adicione ao `.env` da VPS (não ao frontend e nunca ao Git):

```dotenv
VOICESTUDIO_URL=https://seu-endereco-privado
VOICESTUDIO_API_KEY=chave-do-backend-voicestudio
VOICESTUDIO_VOICE_ID=id-do-perfil-clonado
VOICESTUDIO_MODEL=omnivoice
VOICESTUDIO_TIMEOUT=120
VOICESTUDIO_STEPS=16
```

`VOICESTUDIO_URL` aceita a base sem caminho ou terminando em `/v1`.
URL ou ID da voz vazios desativam o motor secundário.
O Compose existente já carrega `.env`; recrie o serviço após configurar.

## Onde o serviço está

O Solo Bot está na VPS e o VoiceStudio está no computador Windows. Por isso,
`http://127.0.0.1:3900` na configuração da VPS aponta para a própria VPS,
não para o computador. Antes de ativar, estabeleça uma conexão privada entre
eles (por exemplo, uma rede privada com TLS ou um túnel autenticado).
Não abra a porta 3900 do computador à internet.

O VoiceStudio deve aceitar conexões pelo endereço privado escolhido e usar
`OMNIVOICE_API_KEY` no backend. O mesmo valor vai em `VOICESTUDIO_API_KEY` no
Solo Bot. O cliente envia `Authorization: Bearer ...`, sem redirecionamentos.
Mantenha a chave no servidor. Chaves não são retornadas no áudio nem escritas
nos registros. HTTP sem TLS só deve atravessar loopback ou túnel cifrado.

O VoiceStudio deve estar aberto, com o motor pronto e o computador disponível.
Se preferir funcionamento permanente, hospede o VoiceStudio em um servidor
privado com recursos de inferência; transfira também o perfil e sua referência.
Copiar somente o ID não transfere a voz para outra instalação.

## Voz da Bella

O clone está salvo como **Bella Solo Bot - ElevenLabs**. Consulte
`GET /v1/audio/voices` na instalação escolhida e use o ID desse perfil em
`VOICESTUDIO_VOICE_ID`. O ID pertence àquela instalação.

São enviados português (`pt`), velocidade natural e 16 passos por padrão, como
no modo interativo do VoiceStudio. `VOICESTUDIO_STEPS` permite ajustar de 1 a 128;
32 recupera o perfil de maior qualidade e exige mais processamento. O ganho real
depende do hardware, tamanho da fala e carga do motor. Falas normais
não recebem instrução de sussurro. Apenas o tom explícito `sussurro` já usado
pelos Ecos é convertido para `instruct: whisper`.

## Formatos, falhas e cache

- Telegram recebe OGG/Opus; Bella, WhatsApp e os demais clientes recebem MP3.
- O formato `{base64, mime}` existente é preservado.
- Falhas de conexão, autenticação, geração ou respostas sem áudio não quebram
  a resposta em texto.
- Saudações e Ecos mantêm cache persistente separado por provedor, endereço,
  voz, modelo, texto, formato e parâmetros. O cache do ElevenLabs não é
  substituído pelo cache da reserva.
- A reserva não altera o perfil ativo do ElevenLabs. No pedido seguinte,
  o ElevenLabs volta a ser tentado primeiro.
- O tempo limite configurado vale para o pedido ao VoiceStudio. Ele se soma
  às tentativas do ElevenLabs; ajuste-o ao orçamento do cliente e do proxy.

## Validação

`python -m pytest -q tests/test_voicestudio.py` cobre prioridade, ordem das
contas, falhas, formatos, autenticação, cache e recuperação do principal.
Antes de commitar, execute também `python -m pytest -q tests` no projeto.

Na implantação, confirme `/health` pela mesma rede privada usada pelo Solo Bot,
gere uma frase curta pelo perfil clonado e simule uma falha controlada do
ElevenLabs. Verifique áudio na Bella e nos canais em uso e restaure o principal.
A reserva só está operacional depois desses testes pela rede real.

## Escolha manual do motor

Em **Administração → Voz do bot → Motor de voz**, selecione e aplique:

- **Automático** (padrão): ElevenLabs e suas contas primeiro; VoiceStudio após falha.
- **ElevenLabs**: somente ElevenLabs, respeitando a conta escolhida.
- **VoiceStudio**: somente o clone configurado no VoiceStudio, sem gastar na ElevenLabs.

A escolha fica salva no banco e vale para todos os canais, incluindo a Bella e suas
saudações. Motores sem configuração não podem ser selecionados. O botão Ouvir testa
o motor atual. No VoiceStudio, os ajustes de conta, voz e modelo ElevenLabs ficam
ocultos; voltam a aparecer ao selecionar ElevenLabs ou Automático.

## Clonar uma voz pelo WhatsApp ou Telegram (`/clonarvoz`)

Só a conta administradora. O comando cria um perfil clonado no VoiceStudio
(`POST /profiles`, `kind=clone`, na raiz do serviço, sem `/v1`) a partir do próximo áudio.

1. `/clonarvoz Nome da voz`: o bot passa a esperar uma amostra (10 minutos; `/clonarvoz cancelar` desiste).
2. Mande UM áudio de 10 a 60 segundos, falando normalmente, sem música ou ruído.
   Áudio com menos de 5 segundos é recusado sem gastar o pedido.
3. Esse áudio não é transcrito nem entregue a nenhum sistema: vai direto ao VoiceStudio,
   que transcreve a amostra sozinho e guarda o perfil.
4. Em Administração → Voz do bot, o perfil aparece na lista de vozes do VoiceStudio. A escolha
   continua manual.

Exige o computador com o VoiceStudio ligado e alcançável pela VPS (mesma conexão privada do motor),
e `VOICESTUDIO_API_KEY` com permissão de administrador. Clone apenas vozes suas ou com autorização.
Falhas (computador desligado, chave recusada, amostra sem fala) voltam explicadas no chat.
O pedido pendente fica só na memória do servidor: reiniciar o container o cancela.
