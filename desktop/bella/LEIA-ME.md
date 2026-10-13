# Bella — assistente do Solo Bot para Windows

Primeira versão portátil para Windows 10/11 de 64 bits e .NET Framework 4.8.
O computador precisa de um microfone padrão e conexão ao Solo Bot para executar pedidos.

## Usar

1. Extraia **todo** o `Bella-Windows.zip` numa pasta permanente. Abra `Bella/Bella.exe`.
2. No painel da Conta Solo, seção **Bella no computador**, gere uma chave. Cole no aplicativo e clique em **Salvar acesso**.
3. Clique em **Ativar escuta**. Diga **Bella**, faça uma breve pausa e fale o pedido quando aparecer **Pode falar**. A pausa no fim da frase envia o pedido.
4. Exemplos: “rotinas hoje”, “recebi 92,60 na conta Uber”, “terminei o treino”. Comandos exatos também podem ser digitados, como `/fin saldo`.
5. Para responder a uma confirmação ou escolher uma opção, chame Bella novamente e diga “sim” ou “dois”. O modo do sistema fica ativo entre pedidos por até 30 minutos.

**Ctrl + Alt + B** ativa a gravação sem precisar dizer o nome. **Falar agora** faz o mesmo.
Fechar a janela a mantém perto do relógio; o menu do ícone oferece abrir, falar, pausar e sair.
**Pausar escuta** libera o microfone. **Interromper voz** para a reprodução da resposta.
**Iniciar com Windows** é opcional: marque e salve para iniciar minimizada na próxima entrada.
Para desativar, desmarque e salve. Mantenha a pasta no mesmo lugar se usar essa opção.

## Áudio e acesso

- A chamada “Bella” é reconhecida localmente pelo Vosk com o modelo português. A grafia fonética no modelo é “bela”; isso não altera o nome do aplicativo.
- O áudio ambiente de espera não é enviado. Só o pedido ativado é enviado como WAV ao Solo Bot para transcrição. A gravação termina após pausa, com limite de 30 segundos. Sem fala, volta à espera sem enviar.
- Durante processamento e resposta falada, o detector ignora o áudio para não ouvir a própria resposta. Não há envio automático de um segundo pedido.
- ElevenLabs gera a resposta na voz configurada no Solo Bot. Se o servidor não enviar áudio, o aplicativo usa a voz disponível no Windows (o idioma depende das vozes instaladas).
- A chave fica cifrada para o usuário atual do Windows usando DPAPI. O aplicativo não guarda a senha Solo nem as chaves de Gemini ou ElevenLabs.
- A chave pode ser revogada ou trocada no painel, independentemente da Siri e dos outros canais. HTTPS é obrigatório, exceto em testes locais.
- Mensagens ficam apenas na janela e não são gravadas em histórico no computador. O áudio da resposta é temporário e apagado após reprodução. O servidor mantém seu registro habitual de comandos, sem guardar o conteúdo do pedido.
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

Para obter o pacote já compilado pelo GitHub, abra a execução de **Bella para Windows**
em [Actions](https://github.com/Jheffth/SOLO-BOT/actions/workflows/bella-windows.yml) e
baixe o artefato `Bella-Windows`. Esse download exige acesso ao GitHub.

Fontes: [API Vosk](https://github.com/alphacep/vosk-api),
[modelo português](https://alphacephei.com/vosk/models),
[proteção DPAPI](https://learn.microsoft.com/en-us/dotnet/standard/security/how-to-use-data-protection).
