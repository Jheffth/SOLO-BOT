const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('frontend/admin.html', 'utf8');
for (const block of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new Function(block[1]);
const start = html.indexOf('  async function carregarVoz()');
const end = html.indexOf('  document.getElementById("voz-recarregar").onclick', start);
const functionSource = html.slice(start, end);
const modes = ['automatico', 'elevenlabs', 'voicestudio'];
function panel(current, unavailable = false) {
  return {
    disponivel: !unavailable,
    motor: {atual: current, opcoes: modes.map(id => ({id, nome:id, configurado: id !== 'voicestudio' || !unavailable}))},
    conta:{atual:'automatica',opcoes:[]},creditos:[],modelo:{atual:'flash',opcoes:[],fixo_no_env:false},
    voz:{id:'bella',nome:'Bella',origem:'tela'},vozes:[],voz_sistema:{id:'bella',origem:'mesma'}
  };
}
function setup(mode, unavailable = false) {
  const elements = new Map();
  const radios = [];
  const calls = [], errors = [];
  let current = mode, fail = false;
  const target = {
    _html:'',
    set innerHTML(value) {
      this._html = value;
      radios.length = 0;
      for (const tag of value.matchAll(/<(?:button|input|fieldset|p)[^>]*\bid="([^"]+)"[^>]*>/g)) {
        elements.set(tag[1], {disabled:/\sdisabled(?=[\s>])/.test(tag[0]), value:(tag[0].match(/\bvalue="([^"]*)"/)||[])[1] || ''});
      }
      for (const tag of value.matchAll(/<input[^>]*name="voz-motor"[^>]*>/g)) {
        radios.push({value:tag[0].match(/value="([^"]+)"/)[1], checked:/\schecked(?=[\s>])/.test(tag[0]), disabled:/\sdisabled(?=[\s>])/.test(tag[0])});
      }
    },
    get innerHTML() { return this._html; },
    querySelectorAll(selector) { return selector === 'input[name="voz-motor"]' ? radios : []; },
    querySelector(selector) { assert.equal(selector,'input[name="voz-motor"]:checked'); return radios.find(r => r.checked); }
  };
  elements.set('voz-corpo',target);
  const context = {
    document:{getElementById:id=>elements.get(id)},
    api: async (url,opts) => { calls.push([url,opts]); if(opts) { if(fail) throw Error('Falha simulada'); current=opts.body.motor; return {ok:true}; } return panel(current,unavailable); },
    esc:s=>String(s ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
    icon:()=>'<svg aria-hidden="true"></svg>', toast:msg=>errors.push(msg),carregando:(button,on)=>{button.disabled=on;},tocando:null,CAT:{},fmt:String
  };
  vm.createContext(context);vm.runInContext(functionSource,context);
  return {context,elements,radios,calls,target,errors,setFailure:()=>{fail=true;},choose(id) {const r=radios.find(r=>r.value===id); assert.ok(!r.disabled);radios.forEach(x=>{x.checked=x===r;});r.onchange();}};
}
(async () => {
  for (const mode of modes) {
    const t=setup(mode);
    await t.context.carregarVoz();
    assert.equal(t.radios.length,3);
    assert.equal(t.radios.find(r=>r.checked).value,mode);
    assert.equal(t.elements.get('voz-motor-salvar').disabled,true);
    assert.equal(t.calls.length,1,'renderizar não gera áudio nem faz consultas extras');
    assert.equal(t.target.innerHTML.includes('id="voz-conta"'),mode!=='voicestudio');
    t.choose(mode==='voicestudio'?'elevenlabs':'voicestudio');
    assert.equal(t.elements.get('voz-motor-salvar').disabled,false);
    await t.elements.get('voz-motor-salvar').onclick();
    const writes=t.calls.filter(([,opts])=>opts);
    assert.equal(writes.length,1);
    assert.equal(writes[0][1].method,'PUT');
    assert.equal(writes[0][1].body.motor,mode==='voicestudio'?'elevenlabs':'voicestudio');
  }
  const missing=setup('automatico',true);await missing.context.carregarVoz();
  assert.equal(missing.radios.find(r=>r.value==='voicestudio').disabled,true);
  assert.ok(missing.target.innerHTML.includes('Configuração pendente'));
  const failed=setup('voicestudio');await failed.context.carregarVoz();failed.choose('elevenlabs');failed.setFailure();
  await failed.elements.get('voz-motor-salvar').onclick();
  assert.equal(failed.elements.get('motor-options').disabled,false);
  assert.equal(failed.elements.get('voz-motor-salvar').disabled,false);
  assert.ok(failed.errors.includes('Falha simulada'));
  console.log('OK: três motores, escolha persistida, indisponibilidade, recuperação de falha e nenhuma geração automática.');
})().catch(error=>{console.error(error);process.exitCode=1;});
