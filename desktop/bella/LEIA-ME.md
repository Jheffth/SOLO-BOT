# Bella — assistente do Solo Bot para Windows

Aplicativo portátil para Windows 10/11 de 64 bits, .NET Framework 4.8 e Microsoft Edge WebView2.
O computador precisa de um microfone padrão e conexão ao Solo Bot para executar pedidos.

## Usar

1. Extraia **todo** o `Bella-Windows.zip` numa pasta permanente. Abra `Bella/Bella.exe`.
2. Na primeira vez, a Bella mostra três passos. No painel da Conta Solo, seção **Bella no computador**,
   gere uma chave, cole no campo e clique em **Começar**. Ela já começa a ouvir.
3. Diga **Bella** e aguarde a saudação falada com seu login. Quando ela terminar, fale o pedido.
   A pausa no fim da frase envia o pedido.
4. Exemplos: “rotinas hoje”, “recebi 92,60 na conta Uber”, “terminei o treino”. Também dá para
   escrever no campo de baixo, inclusive comandos exatos como `/fin saldo`.
5. Quando a resposta trouxer uma lista, as opções aparecem como **botões**: clique, ou chame a
   Bella e diga “dois”. Para uma confirmação, diga “sim”. O modo do sistema fica ativo por até 30 minutos.

### A tela

- **No centro, a Bella**: a foto dela (ou o orbe colorido) com um **anel vivo** que mostra o estado:
  apagado com a escuta pausada, girando devagar esperando o nome, **ciano e reagindo à sua voz**
  enquanto ouve, girando rápido enquanto pensa, pulsando enquanto fala.
- **O selo no alto** (“Ouvindo ‘Bella’”) liga e pausa a escuta. Pausada, o microfone fica livre.
- **A conversa** vem em balões, com o sistema que respondeu (💰 Finances, ⚔️ Rotinas) e, em cinza,
  o que a Bella entendeu (“🧭 Entendi: …”).
- **🎤** (ou **Ctrl + Alt + B**) chama a Bella sem dizer o nome. **■** interrompe a voz.
- **⚙ Configurações**: foto da Bella, iniciar com o Windows, Mini-Bella, sensibilidade do microfone
  (com um medidor ao vivo: fale normalmente, a barra deve passar da marca amarela) e a chave.
- Fechar a janela mantém a Bella perto do relógio. O ícone muda de cor com o estado; o menu dele
  oferece abrir, falar, pausar e sair.

### A foto da Bella

Em **⚙ → Aparência**, clique em **Escolher foto** ou arraste uma imagem (JPG, PNG ou WEBP) para a
área tracejada. Ajuste o recorte arrastando e aproximando, e clique em **Usar esta foto**.
A foto aparece no centro, ao lado de cada resposta e na Mini-Bella. **Recortar** reabre o ajuste
com a imagem original; **Remover** volta ao orbe; **Só orbe** esconde a foto sem apagá-la.
A foto fica **só neste computador** (`%LOCALAPPDATA%\Solo\Bella\foto.jpg`) e nunca vai ao servidor.

### Mini-Bella

Com a janela fechada, quando você chama a Bella aparece uma pílula pequena acima da barra de
tarefas, com a foto, o que ela ouviu e a resposta. Ela não rouba o foco de quem está digitando e
some sozinha alguns segundos depois. Um clique abre a janela. Dá para desligar nas configurações.

### Requisito: WebView2

A tela é desenhada pelo **Microsoft Edge WebView2**, que já vem no Windows 11 e na maioria dos
Windows 10 atualizados. Se faltar, a Bella avisa e abre a página oficial de download da Microsoft.

## Áudio e acesso

- A chamada “Bella” é reconhecida localmente pelo Vosk com o modelo português. A grafia fonética no modelo é “bela”; isso não altera o nome do aplicativo.
- O áudio ambiente de espera não é enviado. Só o pedido ativado é enviado como WAV ao Solo Bot para transcrição. A gravação termina após pausa, com limite de 30 segundos. Sem fala, volta à espera sem enviar.
- Durante processamento e resposta falada, o detector ignora o áudio para não ouvir a própria resposta. Não há envio automático de um segundo pedido.
- ElevenLabs gera a resposta na voz configurada no Solo Bot. Se o servidor não enviar áudio, o aplicativo usa a voz disponível no Windows (o idioma depende das vozes instaladas).
- A chamada tem **20 saudações diferentes**, com o login da Conta Solo (nome cadastrado para contas antigas sem login). As frases são fixas e não usam Gemini. São sorteadas sem repetição até completar o ciclo.
- Na ativação, Bella prepara os áudios que faltam em segundo plano. A ElevenLabs cobra a **primeira geração** de cada frase/login/voz/modelo; as reutilizações leem arquivos, sem pedir nova síntese. Chamadas simultâneas à mesma frase compartilham a geração.
- Os MP3 ficam no volume persistente do servidor e em `%LOCALAPPDATA%\Solo\Bella\saudacoes` no computador. O aplicativo consulta a voz atual em cada chamada. Trocar voz, modelo ou login seleciona outro conjunto; voltar a uma voz anterior reaproveita seus arquivos. A troca automática para a conta secundária acompanha a voz que realmente respondeu. Sem conexão, usa o último catálogo conhecido deste acesso; chave recusada bloqueia o cache.
- Durante a saudação, o microfone ignora o áudio. Só depois começa a gravação, inclusive pelo atalho. Pausar durante a saudação mantém o microfone desligado.
- A chave fica cifrada para o usuário atual do Windows usando DPAPI. O aplicativo não guarda a senha Solo nem as chaves de Gemini ou ElevenLabs.
- A chave pode ser revogada ou trocada no painel, independentemente da Siri e dos outros canais. HTTPS é obrigatório, exceto em testes locais.
- Mensagens ficam apenas na janela e não são gravadas em histórico no computador. O áudio de respostas a pedidos é temporário e apagado após reprodução; as saudações são preservadas para reutilização. O servidor mantém seu registro habitual de comandos, sem guardar o conteúdo do pedido.
- Falha de conexão **não** reenvia o pedido automaticamente. Confira o resultado no sistema antes de repetir uma operação financeira.

O reconhecimento da chamada depende do microfone, pronúncia e ruído. Se não ativar,
use o atalho. Se captar ruído como fala, leve a **Sensibilidade** para “ambiente barulhento”;
se encerrar antes de você falar, para “silencioso”. O medidor ao vivo ajuda a achar o ponto. A versão inicial mantém o modo de cada sistema,
mas ainda não oferece memória geral de conversa, identificação de pessoa pela voz ou
controle de aplicativos do Windows.

## Compilar

No PowerShell, dentro desta pasta:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Compilar.ps1
```

O script usa o compilador que acompanha o .NET Framework, baixa as bibliotecas oficiais
para `.cache`, confere o SHA256 do Vosk e a assinatura digital da Microsoft nas DLLs do WebView2,
copia a tela (`ui/`) e produz `dist/Bella` e `dist/Bella-Windows.zip`.
Não instala Python, pacotes globais ou serviços. Os testes internos carregam o modelo real,
verificam que silêncio não ativa, testam o ciclo de gravação, pausas e bloqueio de duplicação.
Conferem também que a tela e as DLLs do WebView2 estão no pacote e que a foto só aceita imagem de verdade.
Não abrem o microfone e não fazem operações financeiras.

Com a Bella aberta, use `-PrepararAtualizacao` para gerar o pacote em `dist/atualizacao/Bella`, sem alterar o aplicativo em uso. Para aplicar, escolha **Sair** pelo ícone perto do relógio, extraia o ZIP na pasta permanente da Bella e abra novamente. O acesso salvo e a preferência de iniciar com Windows continuam no mesmo usuário.

Para obter o pacote já compilado pelo GitHub, abra a execução de **Bella para Windows**
em [Actions](https://github.com/Jheffth/SOLO-BOT/actions/workflows/bella-windows.yml) e
baixe o artefato `Bella-Windows`. Esse download exige acesso ao GitHub.

Fontes: [API Vosk](https://github.com/alphacep/vosk-api),
[modelo português](https://alphacephei.com/vosk/models),
[proteção DPAPI](https://learn.microsoft.com/en-us/dotnet/standard/security/how-to-use-data-protection).
