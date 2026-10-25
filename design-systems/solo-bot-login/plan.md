# Solo Bot — referência e plano de recriação

Etapa 1. Referência estrutural: frontend/index.html, frontend/static/solo.css,
frontend/static/solo.js e frontend/static/logo.svg. reference.html é uma
cópia do HTML original, para registro; não é a implementação final.
O navegador não estava disponível: ainda não existe screenshot de referência
e não houve comparação visual. O wireframe foi transcrito do código existente,
uma adaptação do requisito de entrada por imagem, sem alegar análise visual.

## Direção

Recriar o login existente em HTML/CSS/JS separados, preservando conteúdo e
identidade escura, auroras violeta/ciano/esmeralda, superfícies de vidro e
hierarquia de duas colunas. Preservar também o tema claro existente.
Não redesenhar o sistema de autenticação nem criar novos campos/rotas.

| Região | Etapa | Técnica |
| --- | --- | --- |
| Fundo, auroras e grade | 2 | CSS, pseudo-elementos e gradientes |
| Marca, cabeçalho, hero e integrações | 3 | HTML semântico, logo existente e CSS |
| Cartão de acesso e abas | 3 | HTML/CSS, estados de entrada e cadastro |
| Formulários e contexto de conexão | 3 | Campos existentes, validação e JS externo |
| Conversa de demonstração | 3 | Mensagens no HTML; JS apenas para comportamento |
| Tipografia | 3 | Famílias Sora, Inter e JetBrains Mono já declaradas no projeto; verificar carregamento |
| Ícones e logo | 3 | Reutilizar os SVGs existentes; não gerar substitutos |
| Mobile e movimento reduzido | 3 | Preservar formulário primeiro até 960px e ocultar demonstração até 520px |
| Revisão integrada | 5 | Navegador desktop/mobile, tema claro/escuro, teclado e fluxos existentes |

Não há imagens novas ou assets pendentes de geração: omitir etapa 4.
Geração nativa só será necessária se o usuário solicitar nova arte.

## Comportamentos a preservar na implementação

- Login por usuário ou e-mail e senha.
- Cadastro com nome, usuário, e-mail opcional e senha.
- Mostrar/ocultar senha, força da senha e erros acessíveis.
- POST /api/auth/entrar e POST /api/auth/cadastro.
- Sessão existente por GET /api/auth/eu.
- Destino local proximo e contexto de /conectar.
- Alternância de tema, foco por teclado e prefers-reduced-motion.
- Nenhum envio de credenciais durante a inspeção ou validação visual.

## Entrega e integração

A implementação revisável será design-systems/solo-bot-login/index.html,
assets/styles.css e assets/app.js. Na etapa 3, ligar chamadas existentes pela
mesma origem ao servir pelo Solo Bot; abertura por file:// só valida a parte
visual, não autentica. Na revisão final, integrar ao frontend real com os
caminhos estáticos existentes, verificar CSP e preservar rotas de conexão.

Etapas 1 e 2 aprovadas pelo usuário com “avance”. Etapa 3 implementada em
index.html, assets/styles.css, assets/app.js e assets/logo.svg. Formulário,
cadastro, demonstração estática, tema, foco/abas por teclado, força da senha,
erros, prevenção de envio duplicado e rotas existentes estão presentes.
As mensagens de demonstração permanecem no HTML, sem geração por loops JS.

Validação: sintaxe JS pelo Node; harness Node com DOM/API simulados verificou
login, cadastro sem e-mail, payload/cookies same-origin, validação de campos,
mostrar senha, tema, recusa de destinos externos, preservação do retorno para
conexão e recuperação após erro do servidor. HTML foi conferido quanto a IDs
únicos, assets locais e ausência de estilos/scripts inline; CSS foi analisado.
Não houve login/cadastro real nem envio de credenciais a um servidor.

Limite: o navegador integrado bloqueou a abertura de file:// por política de
URL. Comparação visual desktop/mobile, carregamento real de fontes e teste
de integração com o backend ainda estão pendentes; os testes simulados não
substituem essas verificações. As fontes Google requerem rede e têm fallback
de sistema.

Etapa 3 aprovada pelo usuário com “aprovo”. Não há etapa 4, conforme o plano.

## Etapa 5 — integração e validação final

A versão aprovada foi integrada a frontend/index.html, com CSS e JavaScript
em frontend/static/login.css e frontend/static/login.js. Usa static/logo.svg
existente. As rotas /, /entrar e /cadastro continuam servindo o mesmo HTML;
nenhuma alteração no backend, contratos ou credenciais. O Dockerfile já copia
frontend inteiro, incluindo os arquivos novos. Não houve deploy.

Verificações concluídas: correspondência exata entre a prévia e o frontend
(somente caminhos de assets diferem); sintaxe JavaScript; testes simulados
de login/cadastro/erros/retorno local; integridade do HTML/CSS e arquivos.
Não foi encontrada política CSP no middleware atual que exija adaptação.
CSS/JS não têm conteúdo inline.

A suíte pytest foi tentada com banco temporário dentro do workspace para
resolver o erro anterior de SQLite. O banco foi criado, mas a suíte travou
ao inicializar TestClient. Uma execução focada com faulthandler_timeout=20
identificou socket.accept em socket._fallback_socketpair, durante criação
do event loop asyncio do Windows, antes de executar o primeiro teste.
As execuções foram interrompidas. A suíte de backend não está validada neste
ambiente; não foram alterados testes nem a aplicação para contornar o bloqueio.

Abertura visual no navegador e carregamento de fontes continuam pendentes
pelas restrições já registradas. A versão integrada está pronta para a
conferência e aprovação final do usuário, com esses limites explícitos.
