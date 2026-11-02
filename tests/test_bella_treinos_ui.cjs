/* O compositor diferencia anexo automático, pedido de prompt e comando de treino. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const fonte=fs.readFileSync('desktop/bella/ui/bella.js','utf8');
const elementos={'compositor':{},'entrada':{value:''},'extrair-tudo':{checked:false},'captura-prompt':{},'captura-pedido':{value:''}};
const enviados=[];
const c={estado:{ocupada:false},anexo:'data:image/jpeg;base64,AAAA',captura:null,
 $:id=>elementos[id],document:{querySelectorAll:()=>[]},enviar:(acao,dados)=>enviados.push({acao,...dados}),
 tirarAnexo:()=>{c.anexo=null;},fecharCaptura:()=>{c.captura=null;},toast:()=>{throw Error('Toast inesperado');}};
vm.createContext(c);
vm.runInContext(fonte.slice(fonte.indexOf('    $("compositor").onsubmit'),fonte.indexOf('    // Ferramentas laterais:')),c);
function enviar(texto,tudo=false){c.anexo='data:image/jpeg;base64,AAAA';elementos.entrada.value=texto;elementos['extrair-tudo'].checked=tudo;elementos.compositor.onsubmit({preventDefault(){}});return enviados.at(-1);}
assert.equal(enviar('').texto,'analise esta imagem','print sem legenda chega neutro ao servidor');
assert.equal(enviar('/rot treino caminhada',true).texto,'/rot treino caminhada','configuração de prompt não altera legenda de treino');
assert.equal(enviar('/prompt rua').texto,'/prompt rua','pedido explícito de prompt continua separado');
assert.ok(enviar('',true).texto.startsWith('/promptmodelo'),'extração selecionada solicita prompt explicitamente');
const i=fonte.indexOf('    $("captura-prompt").onclick');
vm.runInContext(fonte.slice(i,fonte.indexOf('    $("captura-pedido").addEventListener',i)),c);
c.captura='data:image/jpeg;base64,AAAA';elementos['captura-prompt'].onclick();
assert.equal(enviados.at(-1).texto,'/prompt ','botão Criar prompt tem destino explícito');
console.log('Compositor: treino automático, legenda preservada, prompts e captura separados — OK');
