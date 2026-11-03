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
  const alvo=new Elemento('div'); let tick,soltar; let consultas=0,selecionado=null;
  const lista=[{id:'bella',nome:'Bella',descricao:'Modelo publicado'}];
  const antigo=new Promise(resolve=>{soltar=resolve;});
  const Solo={toast:()=>{},api:async(url,opts)=>{
    if(opts) { selecionado=opts.body.modelo_id; return {}; }
    ++consultas;
    if(consultas===2)return antigo;
    return {modelo_id:selecionado,disponivel:true,modelos:lista};
  }};
  const contexto={Solo,document:{hidden:false,querySelector:()=>alvo,createElement:t=>new Elemento(t)},setInterval:fn=>{tick=fn;}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/static/models.js'),'utf8'),contexto);
  const esperar=()=>new Promise(resolve=>setImmediate(resolve));
  await esperar();
  assert.equal(alvo.querySelectorAll('button')[0].attrs['aria-pressed'],'true');
  tick(); // A consulta automática antiga fica pendente.
  await alvo.querySelectorAll('button')[1].events.click();
  assert.equal(selecionado,'bella');
  assert.equal(alvo.querySelectorAll('button')[1].attrs['aria-pressed'],'true');
  soltar({modelo_id:null,disponivel:true,modelos:lista});
  await esperar();
  assert.equal(alvo.querySelectorAll('button')[1].attrs['aria-pressed'],'true');
  assert.equal(alvo.querySelectorAll('button')[0].attrs['aria-pressed'],'false');
  console.log('OK: resposta automática atrasada não desfaz a escolha Models.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
