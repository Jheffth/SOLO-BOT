# Bella — assistente do Solo Bot para Windows

Primeira versão portátil para Windows 10/11 de 64 bits e .NET Framework 4.8.
O computador precisa de um microfone padrão e conexão ao Solo Bot para executar pedidos.

## Usar

1. Extraia **todo** o `Bella-Windows.zip` numa pasta permanente. Abra `Bella/Bella.exe`.
2. No painel da Conta Solo, seção **Bella no computador**, gere uma chave. Cole no aplicativo e clique em **Salvar acesso**.
3. Clique em **Ativar escuta**. Diga **Bella** e aguarde a saudação falada com seu login. Quando ela terminar, fale o pedido. A pausa no fim da frase envia o pedido.
4. Exemplos: “rotinas hoje”, “recebi 92,60 na conta Uber”, “terminei o treino”. Comandos exatos também podem ser digitados, como `/fin saldo`.
5. Para responder a uma confirmação ou escolher uma opção, chame Bella novamente e diga “sim” ou “dois”. O modo do sistema fica ativo entre pedidos por até 30 minutos.

**Ctrl + Alt + B** chama Bella sem precisar dizer o nome. **Falar agora** faz o mesmo.
Fechar a janela a mantém perto do relógio; o menu do ícone oferece abrir, falar, pausar e sair.
**Pausar escuta** libera o microfone. **Interromper voz** para a reprodução da resposta.
**Iniciar com Windows** é opcional: marque e salve para iniciar minimizada na próxima entrada.
Para desativar, desmarque e salve. Mantenha a pasta no mesmo lugar se usar essa opção.

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
use o atalho. Se captar ruído como fala, aumente o valor de **Sensibilidade** e salve;
se encerrar antes de você falar, diminua. A versão inicial mantém o modo de cada sistema,
mas ainda não oferece memória geral de conversa, identificação de pessoa pela voz ou
controle de aplicativos do Windows.

## Compilar

No PowerShell, dentro desta pasta:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Compilar.ps1
```

O script usa o compilador que acompanha o .NET Framework, baixa as bibliotecas oficiais
para `.cache`, confere SHA256 e produz `dist/Bella` e `dist/Bella-Windows.zip`.
Não instala Python, pacotes globais ou serviços. Os testes internos carregam o modelo real,
verificam que silêncio não ativa, testam o ciclo de gravação, pausas e bloqueio de duplicação.
Não abrem o microfone e não fazem operações financeiras.

Com a Bella aberta, use `-PrepararAtualizacao` para gerar o pacote em `dist/atualizacao/Bella`, sem alterar o aplicativo em uso. Para aplicar, escolha **Sair** pelo ícone perto do relógio, extraia o ZIP na pasta permanente da Bella e abra novamente. O acesso salvo e a preferência de iniciar com Windows continuam no mesmo usuário.

Para obter o pacote já compilado pelo GitHub, abra a execução de **Bella para Windows**
em [Actions](https://github.com/Jheffth/SOLO-BOT/actions/workflows/bella-windows.yml) e
baixe o artefato `Bella-Windows`. Esse download exige acesso ao GitHub.

Fontes: [API Vosk](https://github.com/alphacep/vosk-api),
[modelo português](https://alphacephei.com/vosk/models),
[proteção DPAPI](https://learn.microsoft.com/en-us/dotnet/standard/security/how-to-use-data-protection).
