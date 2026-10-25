const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Elemento {
  constructor(tag) {this.tag = tag; this.children = []; this.hidden = true; this.attrs = {}; this.classes = new Set(); this.classList = {toggle: (c, on) => on ? this.classes.add(c) : this.classes.delete(c)};}
  appendChild(x) {this.children.push(x);}
  append(...xs) {this.children.push(...xs);}
  replaceChildren(...xs) {this.children = xs;}
  setAttribute(k,v) {this.attrs[k] = v;}
  focus() {this.focou = true;}
}
const ids = {};
for (const id of ['galeria-imagens','btn-imagens','imagens-status','imagem-gerar','imagens-lista','conversa']) ids[id] = new Elemento(id);
const enviados = [];
const contexto = {document: {createElement: t => new Elemento(t)}, $: id => ids[id], enviar: (...x) => enviados.push(x), gerandoImagem: false, estado: {ocupada:false}};
vm.createContext(contexto);
const fonte = fs.readFileSync('desktop/bella/ui/bella.js','utf8');
vm.runInContext(fonte.slice(fonte.indexOf('  function abrirImagens('),fonte.indexOf('  const MIN =')),contexto);
contexto.abrirImagens(true);
assert.equal(ids['galeria-imagens'].hidden,false);
assert.equal(enviados[0][0],'imagens_abrir');
contexto.estadoImagem({gerando:true});
assert.equal(ids['imagem-gerar'].disabled,true);
assert.equal(ids['imagens-status'].classes.has('gerando'),true);
const itens = Array.from({length:9}, (_,i) => ({Id:'imagem-'+i,Previa:'data:image/jpeg;base64,AAAA',Criada:'Hoje'}));
contexto.renderizarImagens({imagens:itens,abrir:true});
assert.equal(ids['imagens-lista'].children.length,6);
assert.equal(ids['conversa'].children.length,0);
ids['imagens-lista'].children[0].children[1].children[1].onclick();
assert.equal(enviados.at(-1)[0],'imagem_salvar');
assert.equal(enviados.at(-1)[1].id,'imagem-0');
contexto.fecharImagens();
assert.equal(ids['galeria-imagens'].hidden,true);
assert.equal(ids['imagens-lista'].children.length,6);
assert.equal(ids['btn-imagens'].attrs['aria-expanded'],'false');
contexto.estadoImagem({gerando:false,erro:'Grok indisponível'});
assert.equal(ids['imagens-status'].textContent,'Grok indisponível');
assert.equal(ids['imagem-gerar'].disabled,false);
contexto.renderizarImagens({imagens:[{Previa:'https://externo/imagem.png'}],abrir:false});
assert.equal(ids['imagens-lista'].children.length,0);
assert.equal(ids['galeria-imagens'].hidden,true);
console.log('OK: painel recolhível, galeria separada, limite, exportação, progresso e erro.');
