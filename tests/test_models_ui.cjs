// Uma leitura atrasada nunca pode desfazer a escolha mais recente na tela.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Elemento {
  constructor(tag) { this.tag=tag; this.children=[]; this.attrs={}; this.events={}; }
  append(...itens) { this.children.push(...itens); }
  replaceChildren() { this.children=[]; }
  setAttribute(k,v) { this.attrs[k]=v; }
  addEventListener(k,v) { this.events[k]=v; }
  querySelectorAll(tag) {
    return this.children.flatMap(c=>[...(c.tag===tag?[c]:[]),...c.querySelectorAll(tag)]);
  }
}
async function main() {
  const alvo=new Elemento('div'); let tick,soltar; let consultas=0,selecionado="bella";
  const lista=[{id:'bella',nome:'Bella',descricao:'Modelo publicado'}];
  const antigo=new Promise(resolve=>{soltar=resolve;});
  const Solo={toast:()=>{},api:async(url,opts)=>{
    if(opts) { selecionado=opts.body.modelo_id; return {}; }
    ++consultas;
    if(consultas===2)return antigo;
    return {origem:selecionado?"models":"legado"};
  }};
  const contexto={Solo,document:{hidden:false,querySelector:()=>alvo,createElement:t=>new Elemento(t)},setInterval:fn=>{tick=fn;}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/static/models.js'),'utf8'),contexto);
  const esperar=()=>new Promise(resolve=>setImmediate(resolve));
  await esperar();
  assert.equal(alvo.querySelectorAll('button').length,1); // Só a Bella Legado fica no Bot.
  assert.equal(alvo.querySelectorAll('button')[0].attrs['aria-pressed'],'false');
  tick(); // Uma leitura antiga fica pendente.
  await alvo.querySelectorAll('button')[0].onclick();
  assert.equal(selecionado,null);
  assert.equal(alvo.querySelectorAll('button')[0].attrs['aria-pressed'],'true');
  soltar({origem:'models'});
  await esperar();
  assert.equal(alvo.querySelectorAll('button').length,1);
  assert.equal(alvo.querySelectorAll('button')[0].attrs['aria-pressed'],'true');
  console.log('OK: somente Bella Legado no Bot; leitura antiga não desfaz a seleção.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
