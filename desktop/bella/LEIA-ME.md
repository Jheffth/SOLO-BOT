# Bella — assistente do Solo Bot para Windows

Aplicativo portátil para Windows 10/11 de 64 bits, .NET Framework 4.8 e Microsoft Edge WebView2.
O computador precisa de um microfone padrão e conexão ao Solo Bot para executar pedidos.

## Arquivos no Windows

### Comandos e automações

Clique em **Comandos**, no topo da janela, ou na aba **Comandos** das configurações.
Escolha **Tipo de ação**: pasta, site, Google, YouTube ou Maps. Os **Modelos prontos**
preenchem o formulário; ajuste e salve para criar seu comando. Há exemplos de escrita
criativa, pesquisa livre, vídeos, lugares, Gmail, agenda, WhatsApp Web, Downloads e Documentos.

As pesquisas básicas já funcionam sem cadastro:

- “Pesquisar sobre escrita criativa” abre os resultados no Google.
- “Pesquisar no YouTube sobre técnicas de escrita” abre a busca de vídeos.
- “Pesquisar no Maps sobre cafeterias em São Paulo” abre a busca no mapa.

Para **abrir uma pasta**:
Preencha **Frase do comando** (por exemplo, `Abrir minha pasta de Projetos`) e **Caminho
da pasta** (`C:\JEFFERSON\PROJETOS`), ou use **Escolher pasta**, e clique em **Salvar comando**.
Diga a frase ou escreva na conversa: a Bella abre o caminho cadastrado diretamente.
“Abra” e “abrir”, letras maiúsculas, acentos e pontuação são equivalentes.
Também pode dizer “Quero que abra a minha pasta de projetos” ou “Gostaria de abrir…”.
Para frases mais livres, a Bella consulta o Gemini para escolher entre os comandos
cadastrados. A interpretação recebe somente o pedido, as frases e seus identificadores;
os caminhos cadastrados continuam no computador. Só abre automaticamente uma pasta
quando há uma correspondência segura. Na dúvida ou sem interpretação disponível,
mostra as opções para você escolher, sem enviar esse pedido ao Finanças.

Para **abrir um site**, cadastre uma frase e o endereço HTTP/HTTPS. O site abre no
navegador padrão do Windows. Para **pesquisar**, escolha um assunto fixo ou marque
**Usar o assunto que eu disser** e coloque `{assunto}` na frase, como `Pesquisar sobre
{assunto}`. Você pode dizer “Pesquisar sobre escrita criativa” e depois “Pesquisar
sobre criação de personagens”, usando o mesmo comando. **Testar** pergunta o assunto
se ele for variável. A resposta fica pendente por cinco minutos; “cancelar” cancela.
As páginas abrem diretamente com os resultados, usando o assunto codificado no endereço.
Google, YouTube e Maps não precisam de uma nova chave de serviço para essa navegação.
O Maps usa o [formato oficial de URLs](https://developers.google.com/maps/documentation/urls/get-started).

Cada cadastro tem **Testar**, **Editar** e **Remover**. Remover apaga apenas o comando.
As associações, tipos e assuntos fixos ficam cifrados junto das preferências e continuam disponíveis depois de
reiniciar. Frases duplicadas e caminhos inexistentes são recusados. É possível cadastrar
até 50 comandos pessoais, além das três pesquisas básicas. Um comando de pasta permite apenas abrir aquela pasta; buscar e alterar seus
arquivos continuam dependendo do acesso concedido abaixo. A pasta é conferida novamente
a cada abertura. Sites aceitam somente endereços HTTP/HTTPS sem credenciais.
Na interpretação por IA vão só frases, identificadores e tipos; caminhos, endereços
cadastrados e assuntos fixos não são enviados. O Gemini pode devolver um assunto para
uma pesquisa variável; o Windows monta o endereço apenas no motor definido pelo comando.
Comandos de pastas das versões anteriores continuam disponíveis como tipo Pasta.

### Buscar e cuidar dos arquivos

A Bella busca, lista e abre arquivos e pastas, cria pastas e pode mover, renomear ou excluir
itens **depois de você confirmar**. Em **Configurações → Arquivos deste computador**, escolha
as pastas de acesso. Documentos, Downloads e Área de Trabalho são as escolhas iniciais.
**Remover acesso** tira a pasta da lista, sem apagar nada. Adicione suas pastas de projetos
quando quiser trabalhar nelas. Não é necessário executar a Bella como administrador.

Exemplos por voz ou texto:

- “listar downloads”
- “buscar arquivo relatório em documentos”
- “abrir pasta documentos”
- “abra meus downloads”
- “abra minha pasta de projetos” (adicione a pasta Projetos nas configurações)
- “criar uma pasta chamada Estudos em documentos”
- “mover arquivo relatório.pdf dos downloads para documentos”
- “renomear arquivo relatório.pdf para relatório-final.pdf”
- “excluir arquivo rascunho.txt”
- `/arquivos ajuda` mostra exemplos na conversa.

Se houver vários itens, escolha pelo número ou botão. Mover, renomear e excluir mostram
o caminho exato e o destino; “sim” confirma e “não” ou “cancelar” cancela. A confirmação
vale cinco minutos e só se usa uma vez. Se o arquivo mudar ou o acesso à pasta for removido,
é preciso fazer um novo pedido. Arquivos no destino nunca são substituídos automaticamente.
Excluir usa a Lixeira e pode abrir a confirmação nativa do Windows. A pasta principal de
acesso não pode ser movida, renomeada ou excluída por esses comandos.

Downloads, Documentos e Área de Trabalho são reconhecidos diretamente, inclusive com
“meu”, “minha”, “meus” ou “minhas”. Pastas escolhidas nas configurações também podem ser
chamadas pelo nome, como “minha pasta de projetos”. Uma referência direta não varre as
demais pastas. Se faltar acesso, a Bella indica onde adicioná-lo; não amplia o acesso sozinha.

Nomes e resultados ficam no computador. O pedido ativado por voz é transcrito no servidor
antes de escolher entre arquivos e os sistemas Solo; o servidor não executa operações locais.
Para responder com a voz atual, recebe somente um código de uma frase fixa, cujo áudio é
salvo e reutilizado por voz. Sem conexão para a síntese, a Bella usa a voz do Windows.
Pedidos locais por texto funcionam sem conexão; pedidos por voz precisam da transcrição.

A busca usa nomes (sem ler o conteúdo), nas pastas escolhidas e subpastas, até 10 mil itens
ou cinco segundos. Mostra até dez resultados e avisa se a consulta foi parcial. Informe uma
pasta mais específica para refinar. Abertura aceita documentos, planilhas, imagens e mídia;
não executa programas ou scripts. Caminhos de rede e links de pasta não entram nesta versão.
Arquivos locais do OneDrive são aceitos; sua abertura pode precisar de download pelo Windows.
Para nomes com “para” ou “em”, use aspas por texto, como `abrir arquivo "C:\Minha pasta\Relatório.pdf"`.

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
controle geral de aplicativos do Windows. O controle inicial de arquivos está descrito acima.

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
Os testes de arquivos usam uma pasta temporária, abertura simulada e um provedor simulado
de Lixeira. Conferem confirmação, cancelamento, limites de acesso, colisões, expiração e
roteamento de voz; nenhum arquivo pessoal é alterado e nenhuma janela de documento é aberta.

Com a Bella aberta, use `-PrepararAtualizacao` para gerar o pacote em `dist/atualizacao/Bella`, sem alterar o aplicativo em uso. Para aplicar, escolha **Sair** pelo ícone perto do relógio, extraia o ZIP na pasta permanente da Bella e abra novamente. O acesso salvo e a preferência de iniciar com Windows continuam no mesmo usuário.

Para obter o pacote já compilado pelo GitHub, abra a execução de **Bella para Windows**
em [Actions](https://github.com/Jheffth/SOLO-BOT/actions/workflows/bella-windows.yml) e
baixe o artefato `Bella-Windows`. Esse download exige acesso ao GitHub.

Fontes: [API Vosk](https://github.com/alphacep/vosk-api),
[modelo português](https://alphacephei.com/vosk/models),
[proteção DPAPI](https://learn.microsoft.com/en-us/dotnet/standard/security/how-to-use-data-protection).
