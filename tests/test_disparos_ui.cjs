const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Elemento {
  constructor(tag) { this.tag=tag; this.children=[]; this.dataset={}; this.disabled=false; this.hidden=false; this._value=''; this.textContent=''; }
  set value(v) {this._value=String(v);}
  get value() {return this._value;}
  append(...xs) {this.children.push(...xs);}
  appendChild(x) {this.children.push(x);}
  replaceChildren(...xs) {this.children=xs; if(this.tag==='audio-destinatario') this.value='';}
  reset() {}
}
const ids=['audio-destinatario','audio-texto','audio-enviar','audio-consultar','audio-novo','audio-destino','audio-contagem','audio-status','audio-contatos','audio-historico','audio-contato-form','audio-contato-salvar','audio-contato-nome','audio-contato-numero','audio-envio-form'];
const fonte=fs.readFileSync('frontend/static/disparos.js','utf8');
function preparar({recuperar=false,falhar=false,falharHistorico=false}={}) {
  const el=Object.fromEntries(ids.map(id=>[id,new Elemento(id)]));
  const calls=[],avisos=[],dados={contatos:[{id:1,nome:'<Contato>',numero:'5511999999999'}],envios:[],whatsapp_configurado:true,voz_configurada:true};
  const storage=new Map(recuperar ? [['solo-audio-pedido:7','pedido-antigo']] : []);
  const context={setInterval,clearInterval,window:{},document:{getElementById:id=>el[id],createElement:t=>new Elemento(t)},sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},crypto:{randomUUID:()=> '00000000-0000-4000-8000-000000000001'},Solo:{toast:x=>avisos.push(x),api:async(url,opts)=>{
    calls.push([url,opts]);
    if(url==='/api/admin/audios') {if(falharHistorico && calls.some(([u])=>u.endsWith('/enviar'))) throw Error('Histórico indisponível'); return dados;}
    if(url==='/api/admin/audios/enviar') {if(falhar) throw Error('Conexão caiu'); return {pedido_id:opts.body.pedido_id,numero:dados.contatos[0].numero,estado:'enviado',detalhe:'Aceito'};}
    if(url.includes('/envios/')) return {pedido_id:'pedido-antigo',numero:'5511999999999',estado:'incerto',detalhe:'Confira no WhatsApp'};
    if(url.endsWith('/contatos') && opts.method==='POST') {dados.contatos.push({id:2,...opts.body});return dados.contatos.at(-1);}
    throw Error('Rota inesperada '+url);
  }}};
  vm.createContext(context); vm.runInContext(fonte,context);
  const api=context.window.iniciarEnviosAudio({id:7});
  return {el,calls,storage,api};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  const t=preparar(); await flush();
  assert.equal(t.calls.length,1); assert.equal(t.calls[0][0],'/api/admin/audios');
  assert.equal(t.el['audio-contatos'].children[0].children[0].children[0].textContent,'<Contato>');
  t.el['audio-destinatario'].value=1; t.el['audio-texto'].value='Olá! Uma mensagem exata.'; t.el['audio-texto'].oninput();
  assert.equal(t.el['audio-enviar'].disabled,false);
  assert.ok(t.el['audio-destino'].textContent.includes('+5511999999999'));
  const evento={preventDefault(){}};
  const primeiro=t.el['audio-envio-form'].onsubmit(evento);
  await t.el['audio-envio-form'].onsubmit(evento); await primeiro;
  const envios=t.calls.filter(([url])=>url.endsWith('/enviar'));
  assert.equal(envios.length,1); assert.equal(envios[0][1].body.texto,'Olá! Uma mensagem exata.');
  assert.equal(t.el['audio-enviar'].disabled,true);
  assert.equal(t.storage.has('solo-audio-pedido:7'),true);
  await t.api.consultar(); assert.equal(t.calls.filter(([url])=>url.endsWith('/enviar')).length,1);
  t.el['audio-novo'].onclick(); assert.equal(t.storage.size,0); assert.equal(t.el['audio-texto'].value,'');
  const f=preparar({falhar:true}); await flush();
  f.el['audio-destinatario'].value=1; f.el['audio-texto'].value='Mensagem'; f.el['audio-texto'].oninput();
  await f.el['audio-envio-form'].onsubmit(evento); await f.el['audio-envio-form'].onsubmit(evento);
  assert.equal(f.calls.filter(([url])=>url.endsWith('/enviar')).length,1);
  assert.equal(f.el['audio-status'].dataset.estado,'incerto');
  await f.api.consultar(); assert.equal(f.calls.filter(([url])=>url.endsWith('/enviar')).length,1);
  const h=preparar({falharHistorico:true}); await flush();
  h.el['audio-destinatario'].value=1; h.el['audio-texto'].value='Mensagem'; h.el['audio-texto'].oninput();
  await h.el['audio-envio-form'].onsubmit(evento);
  assert.equal(h.el['audio-status'].dataset.estado,'enviado','falha no histórico não desfaz confirmação de envio');
  const r=preparar({recuperar:true}); await flush();
  assert.equal(r.calls.filter(([url,opts])=>opts?.method==='POST').length,0);
  assert.ok(r.calls.some(([url])=>url.endsWith('/envios/pedido-antigo')));
  console.log('OK: lista salva, destinatário visível, texto exato, envio único, falha e recuperação sem reenvio.');
})().catch(e=>{console.error(e);process.exitCode=1;});
