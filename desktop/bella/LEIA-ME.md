# Bella — assistente do Solo Bot para Windows

Aplicativo portátil para Windows 10/11 de 64 bits, .NET Framework 4.8 e Microsoft Edge WebView2.
O computador precisa de um microfone padrão e conexão ao Solo Bot para executar pedidos.

## Arquivos no Windows

### Word e programas instalados

Na aba **Comandos**, escolha **Microsoft Word — abrir, ditar ou criar texto** e
cadastre uma frase. Os modelos **Word: abrir ou retomar**, **Word: ditado direto**,
**Word: criar conteúdo** e **Word: pedido livre** já preenchem os campos; clique em
**Salvar comando** para habilitar cada um. Exemplos:

- `Abrir Word`: abre ou reutiliza o Word instalado, com um documento disponível.
- `Escreva {pedido}`: diga “Escreva o amor é lindo”. O ditado literal é inserido
  diretamente, sem chamada de interpretação ao Gemini.
- `Faça {pedido}`: diga “Faça uma rima com amor”. Uma chamada ao Gemini interpreta
  e gera o conteúdo antes de inseri-lo. Não precisa cadastrar cada assunto.
- `No Word {pedido}`: permite pedidos mais livres, como “No Word, crie uma carta”.

Um cadastro do tipo Word também habilita abertura e ditados claros por esse aplicativo.
A escrita ocorre no ponto de edição do documento ativo; se houver uma seleção, o texto
novo entra depois dela, sem apagá-la. Sem documento aberto, cria um novo. Documentos
protegidos ou somente para leitura exigem liberar a edição no próprio Word. Esta versão
usa o Microsoft Word para Windows instalado; não automatiza Word na web ou outros editores.
O documento fica aberto, sem salvar ou fechar automaticamente. Confira o documento
antes de repetir uma ação que apresentou erro. O conteúdo existente nunca é enviado à IA.

Para outros aplicativos, escolha **Abrir outro programa instalado** e **Escolher programa**.
São aceitos executáveis `.exe` locais, sem argumentos, atalhos ou scripts. A Bella tenta
trazer a janela existente para a frente antes de iniciar outra instância. O tipo genérico
apenas abre o aplicativo; escrita automática está disponível no tipo Word.

### Tempo de resposta

**Configurações → Escuta → Ativação rápida** pula a saudação falada e libera o pedido
após a frase de ativação. É opcional e não muda o modo apertar para falar. A mesma seção
mostra os tempos recentes de chamada, transcrição, interpretação, aplicativo, sistemas
e busca de voz na rede, sem armazenar o conteúdo dos pedidos em um log de desempenho.
As confirmações dos comandos de aplicativo usam a voz do Windows para evitar outra
espera por síntese na rede. Ditados por texto e abertura direta dispensam Gemini;
pedidos por voz ainda precisam de transcrição, e criação de conteúdo precisa da IA.

### Frases de ativação

Em **Configurações → Escuta**, edite até três frases e clique em **Salvar frases**.
Os padrões são **Olá Bella**, **Oi Bella** e **E aí Bella**. Mantenha pelo menos uma;
deixe os outros campos vazios se quiser menos opções. A mudança vale na hora e fica
salva neste usuário do Windows. Acentos, caixa e pontuação não mudam a chamada.

Diga a frase completa, faça uma pausa e aguarde a saudação antes do pedido. A Bella
ignora resultados parciais, palavras extras e falas com baixa confiança. O detector
usa as frases cadastradas junto de uma saída para falas desconhecidas.
O modelo local verifica as palavras ao salvar e avisa se alguma não é reconhecida.
Prefira duas ou mais palavras para reduzir ativações acidentais. Reconhecimento de
voz pode errar em ambientes barulhentos; use **Apertar para falar** para ativação por tecla.

### Apertar para falar

Em **Configurações → Escuta**, marque **Apertar para falar**. Por padrão, segure **F8
por 5 segundos**, até aparecer **Pode falar**. Fale mantendo a tecla pressionada e
solte para enviar. **Trocar tecla** aceita outra tecla e combinações com Ctrl, Alt
ou Shift; o tempo pode variar de 1 a 30 segundos. As preferências ficam salvas.

Nesse modo, o microfone fica fechado durante a espera e as frases não ativam a gravação.
Soltar cedo ou sem falar não envia nada. Funciona em segundo plano; você também pode
pausar pelo botão de escuta. O texto continua disponível. Desmarcar a opção restaura
a chamada por voz e o atalho Ctrl+Alt+B. A gravação tem limite de 29 segundos.

### Comandos e automações

Clique em **Comandos**, no topo da janela, ou na aba **Comandos** das configurações.
Escolha **Tipo de ação**: pasta, site, Google, YouTube ou Maps. Os **Modelos prontos**
preenchem o formulário; ajuste e salve para criar seu comando. Há exemplos de escrita
criativa, pesquisa livre, vídeos, lugares, Gmail, agenda, WhatsApp Web, Downloads e Documentos.

As pesquisas básicas já funcionam sem cadastro:

- “Pesquisar sobre escrita criativa” abre os resultados no Google.
- “Pesquisar no YouTube sobre técnicas de escrita” abre a busca de vídeos.
- “Pesquisar no Maps sobre cafeterias em São Paulo” abre a busca no mapa.

Para **abrir uma pasta**, basta dizer "Abra a pasta Solo Bot" ou informar seu caminho completo.
Não é preciso cadastrar cada diretório. Se quiser um atalho com uma frase personalizada, preencha **Frase do comando** (por exemplo, `Abrir minha pasta de Projetos`) e **Caminho
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

Além da busca automática de pastas, a Bella busca, lista e abre arquivos, cria pastas e pode mover, renomear ou excluir
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

Downloads, Documentos e Área de Trabalho e caminhos completos são abertos diretamente.
Para outros nomes, a Bella consulta um índice local de diretórios do perfil do usuário e
dos discos locais fixos, respeitando as permissões do Windows. Ao pedir para abrir, um único resultado abre diretamente, inclusive com a busca ainda
parcial ou um nome aproximado. Vários resultados mostram caminhos para escolher; as
escolhas expiram em cinco minutos. Pedidos de pesquisa apenas mostram os resultados.
O caminho é conferido novamente ao abrir. Não segue links ou junctions. Para nomes com
"em" ou "para", use aspas. Pastas fora do índice ainda podem ser abertas pelo caminho completo.

A busca automática concede somente descoberta e abertura de pastas. Abrir arquivos,
listar conteúdo, criar, mover, renomear e excluir continuam limitados às pastas escolhidas
nas configurações; o índice nunca altera essa lista. Pastas protegidas ou indisponíveis
podem não ser encontradas. Windows, Lixeira, dados internos de volume e diretórios de
cache/dependências (node_modules, .git, .venv, venv, __pycache__, .cache, .nuget) ficam fora
da varredura automática. Pastas de nuvem marcadas como reparse point também ficam fora
por precaução; as regras anteriores dos arquivos locais do OneDrive continuam valendo.

O índice só começa no primeiro pedido que precisa dele. Usa um único trabalhador em
segundo plano, com prioridade reduzida, pausas entre lotes e no máximo 60 mil diretórios
ou 90 segundos por varredura. Não lê conteúdo de arquivos, não instala serviços, não
cria observadores por pasta e não varre continuamente. Novos pedidos reutilizam o índice
em memória; depois de 15 minutos, uma nova consulta inicia a atualização. Não há gravação
do índice em disco. Fechar a Bella cancela as próximas etapas da varredura.
O pedido fica ativo enquanto a busca necessária está em andamento. A conversa e a Mini-Bella
mostram uma contagem real das pastas consultadas, sem porcentagem estimada. O botão
**Cancelar busca** interrompe a solicitação sem esperar uma leitura de disco bloqueada.
Os resultados aparecem automaticamente; não é preciso repetir o pedido. Ao encontrar
candidatos, mostra as opções mesmo que o índice geral ainda esteja incompleto. Se atingir
os limites sem resultado, explica que não conseguiu concluir e permite refinar pelo caminho.
A pasta da instalação e seus ancestrais entram primeiro no índice. Variações de transcrição
como "Solobote" podem encontrar "Solo Bot"; se houver um único resultado, ele abre diretamente.

As respostas de pasta usam a voz configurada da ElevenLabs pela rota de voz local, que já
reutiliza os áudios no servidor. Só um código fixo é enviado, sem caminhos. A procura não
consulta IA para interpretar esses pedidos claros. Se a voz configurada falhar, a resposta
permanece na tela e há um aviso; não troca silenciosamente para a voz do Windows.
O contador da busca é visual, sem falas repetidas durante a varredura. Por voz, permanece a
transcrição no servidor. O tempo em Arquivos locais aparece nas medições já existentes.

Nomes e resultados ficam no computador. O pedido ativado por voz é transcrito no servidor
antes de escolher entre arquivos e os sistemas Solo; o servidor não executa operações locais.
Para responder com a voz atual, recebe somente um código de uma frase fixa, cujo áudio é
salvo e reutilizado por voz. Sem conexão para a síntese, a Bella usa a voz do Windows.
Pedidos locais por texto funcionam sem conexão; pedidos por voz precisam da transcrição.

A busca de arquivos usa nomes (sem ler o conteúdo), nas pastas escolhidas e subpastas, até 10 mil itens
ou cinco segundos. Mostra até dez resultados e avisa se a consulta foi parcial. Informe uma
pasta mais específica para refinar. Abertura aceita documentos, planilhas, imagens e mídia;
não executa programas ou scripts. Caminhos de rede e links de pasta não entram nesta versão.
Arquivos locais do OneDrive são aceitos; sua abertura pode precisar de download pelo Windows.
Para nomes com “para” ou “em”, use aspas por texto, como `abrir arquivo "C:\Minha pasta\Relatório.pdf"`.

## Usar

1. Extraia **todo** o `Bella-Windows.zip` numa pasta permanente. Abra `Bella/Bella.exe`.
2. Na primeira vez, a Bella mostra três passos. No painel da Conta Solo, seção **Bella no computador**,
   gere uma chave, cole no campo e clique em **Começar**. Ela já começa a ouvir.
3. Diga **Olá Bella** (ou outra frase cadastrada) e aguarde a saudação falada com seu login. Quando ela terminar, fale o pedido.
   A pausa no fim da frase envia o pedido.
4. Exemplos: “rotinas hoje”, “recebi 92,60 na conta Uber”, “terminei o treino”. Também dá para
   escrever no campo de baixo, inclusive comandos exatos como `/fin saldo`.
5. Quando a resposta trouxer uma lista, as opções aparecem como **botões**: clique, ou chame a
   Bella e diga “dois”. Para uma confirmação, diga “sim”. O modo do sistema fica ativo por até 30 minutos.

### A tela

- **No centro, a Bella**: a foto dela (ou o orbe colorido) com um **anel vivo** que mostra o estado:
  apagado com a escuta pausada, girando devagar esperando o nome, **ciano e reagindo à sua voz**
  enquanto ouve, girando rápido enquanto pensa, pulsando enquanto fala.
- **O selo no alto** (“Esperando chamada”) liga e pausa a escuta. Pausada, o microfone fica livre.
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

- As frases cadastradas são reconhecidas localmente pelo Vosk com o modelo português. A grafia fonética no modelo é “bela”; isso não altera o nome do aplicativo.
- O áudio ambiente de espera não é enviado. Só o pedido ativado é enviado como WAV ao Solo Bot para transcrição. A gravação termina após pausa, com limite de 30 segundos. Sem fala, volta à espera sem enviar.
- Durante processamento e resposta falada, o detector ignora o áudio para não ouvir a própria resposta. Não há envio automático de um segundo pedido.
- ElevenLabs gera a resposta na voz configurada no Solo Bot. Se o servidor não enviar áudio, o aplicativo informa a falha na tela, sem substituir pela voz do Windows.
- A chamada tem **20 saudações diferentes**, com o login da Conta Solo (nome cadastrado para contas antigas sem login). As frases são fixas e não usam Gemini. São sorteadas sem repetição até completar o ciclo.
- Na ativação, Bella prepara os áudios que faltam em segundo plano. A ElevenLabs cobra a **primeira geração** de cada frase/login/voz/modelo; as reutilizações leem arquivos, sem pedir nova síntese. Chamadas simultâneas à mesma frase compartilham a geração.
- Os MP3 ficam no volume persistente do servidor e em `%LOCALAPPDATA%\Solo\Bella\saudacoes` no computador. O aplicativo consulta a voz atual em cada chamada. Trocar voz, modelo ou login seleciona outro conjunto; voltar a uma voz anterior reaproveita seus arquivos. A troca automática para a conta secundária acompanha a voz que realmente respondeu. Sem conexão, usa o último catálogo conhecido deste acesso; chave recusada bloqueia o cache.
- Durante a saudação, o microfone ignora o áudio. Só depois começa a gravação, inclusive pelo atalho. Pausar durante a saudação mantém o microfone desligado.
- A chave fica cifrada para o usuário atual do Windows usando DPAPI. O aplicativo não guarda a senha Solo nem as chaves de Gemini ou ElevenLabs.
- A chave pode ser revogada ou trocada no painel, independentemente da Siri e dos outros canais. HTTPS é obrigatório, exceto em testes locais.
- Mensagens ficam apenas na janela e não são gravadas em histórico no computador. O áudio de respostas a pedidos é temporário e apagado após reprodução; as saudações são preservadas para reutilização. O servidor mantém seu registro habitual de comandos, sem guardar o conteúdo do pedido, exceto as últimas trocas da conversa pessoal, mantidas só na RAM por até 30 minutos.
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
## Respostas sem esperar o áudio

A resposta aparece na conversa assim que a operação termina. A Bella busca a voz
em seguida, sem repetir a ação. Se o serviço de voz demorar ou falhar, ela avisa na tela, sem voz do Windows; as pesquisas e os resultados dos sistemas continuam disponíveis.

Pedidos como “Abra o Word e escreva uma mensagem sua para mim” geram texto criativo
em primeira pessoa como Bella e o inserem uma vez no Word. “Escreva” seguido de
texto literal continua como ditado; pedidos de mensagem, carta ou poema usam criação.
Respostas de aplicativos também solicitam a voz ElevenLabs por código fixo, com
confirmação genérica “Abri o item” compatível com o servidor atual. O documento
não é enviado à síntese. Saudações, erros e respostas dos sistemas nunca usam
a voz do Windows; sem áudio, a resposta e o aviso permanecem na tela.

## Conversa pessoal opcional

Em Configurações → Conversa, o Modo Safada ativa o Grok para mensagens livres e
criação no Word, com flerte, sensualidade e duplo sentido. Por padrão o Grok evita descrições
sexuais explícitas. Com `BELLA_CONTEUDO_ADULTO=1` no servidor, o modo passa a permitir conversa
sensual e explícita entre adultos que consentem, como fantasia. Os limites nunca mudam: nada com
menores de 18 anos, sem consentimento, com pessoas reais identificáveis ou que incentive violência
ou crime, e a Bella não pressiona nem alega exclusividade. O modo começa desligado e fica salvo
nas preferências cifradas da Bella.
A voz continua na ElevenLabs; não há reserva de voz Windows nem troca de provedor
quando o Grok falha. Ditado literal e aberturas diretas continuam locais.
Com o modo ativo, use /fin e /rot para os sistemas ou desligue o modo para usar suas
frases livres. Pastas e comandos locais mantêm prioridade. A conversa tem memória curta: o servidor guarda as últimas trocas (padrão 6, por 30 minutos) só na RAM, por conta, e apaga ao reiniciar; `DELETE /api/bella/conversa` esquece na hora. A resposta vai até 900 caracteres (`BELLA_CONVERSA_MAX_CHARS`); `BELLA_MEMORIA_TURNOS=0` desliga a memória. Sem ferramentas e sem acesso a documentos ou sistemas.
A chave GROK_API_KEY fica no servidor. Para ver o saldo pré-pago do Grok em Administração → Saldo do Grok, defina XAI_MANAGEMENT_KEY (chave de gerenciamento, criada em console.x.ai → Settings → Management Keys; não é a chave normal) e XAI_TEAM_ID. GROK_TEXT_MODEL configura o modelo de texto
(padrão grok-4.7). A geração usa a Responses API oficial, com store=false e timeout.
A rota autenticada /api/bella/conversa separa a geração da síntese existente por voz_id.
O backend atualizado precisa estar publicado antes de usar esse modo na Bella.

## Imagens pelo Grok

O botão Imagens abre um painel recolhível, separado do chat. Gere pela descrição
nesse painel, por /imagem <descrição> ou por “Bella, gere uma imagem de…”. A geração
funciona independentemente do modo de conversa. A imagem não é anexada ao chat;
ali aparece somente uma confirmação. O painel mostra geração em andamento e erros,
pode ser recolhido sem descartar resultados e oferece Salvar original pelo diálogo
nativo do Windows. A confirmação falada usa ElevenLabs.
São guardados no computador os seis últimos originais (até 8 MB cada), em
%LocalAppData%/Solo/Bella/imagens. Apenas prévias JPEG de até 900 pixels entram
na interface, e a leitura/geração dessas prévias ocorre fora da thread da janela.
Ao entrar a sétima, o original mais antigo da galeria é removido; cópias exportadas
pelo usuário permanecem. Não há sincronização de imagens ou URLs remotas no WebView.
O servidor usa GROK_API_KEY e GROK_IMAGE_MODEL (padrão grok-imagine-image-2.0).
A rota autenticada POST /api/bella/imagem gera uma imagem por pedido, limita
concorrência, bloqueia IDs repetidos e não tenta novamente após falha ou timeout.
Cada geração utiliza o saldo da conta xAI. Não há geração automática ao abrir a aba.
O backend precisa ser atualizado antes de usar a função no aplicativo.
