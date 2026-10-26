const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
function criar(mini = false) {
  const enviados = [], callbacks = [];
  class El {
    constructor(tag) { this.tag = tag; this.children = []; this.hidden = false; this.played = 0; }
    appendChild(v) { this.children.push(v); }
    insertAdjacentElement() {}
    setAttribute() {}
    removeAttribute(k) { delete this[k]; }
    play() { this.played++; return Promise.resolve(); }
    pause() { this.paused = true; }
    load() {}
  }
  const ids = Object.fromEntries(['cfg-avatar','avatar-motor','avatar-motor-status','mini'].map(x => [x,new El(x)]));
  const face = new El('face');
  const document = {getElementById: id => ids[id], createElement: t => new El(t), querySelector: () => new El('presence'),
    querySelectorAll: () => [face], body: {classList: {add(){},remove(){}}}};
  const context = {document, URLSearchParams,location: {search: mini ? '?mini=1' : ''},console,
    window: {chrome: {webview: {postMessage: m => enviados.push(m),addEventListener: (t,f) => callbacks.push(f)}}}};
  vm.runInNewContext(fs.readFileSync('desktop/bella/ui/avatar.js','utf8'),context);
  return {ids, v: face.children[0], enviados, receber: data => callbacks.forEach(f => f({data}))};
}
const id = 'a'.repeat(32), url = 'data:video/mp4;base64,AAAA';
const p = criar();
assert.equal(p.v.played,0);
p.receber({tipo:'config',avatarAnimado:false,avatarDisponivel:true});
p.receber({tipo:'estado',ocupada:true});assert.equal(p.ids['cfg-avatar'].disabled,true);
p.receber({tipo:'avatar_video',id,url});
assert.equal(p.v.played,0,'desligado nao reproduz video');
p.ids['cfg-avatar'].checked = true; p.ids['cfg-avatar'].onchange();
assert.equal(p.enviados.at(-1).avatarAnimado,true);
p.receber({tipo:'config',avatarAnimado:true,avatarDisponivel:true});
p.receber({tipo:'estado',ocupada:true});assert.equal(p.ids['cfg-avatar'].disabled,false);
p.receber({tipo:'avatar_video',id,url});
assert.equal(p.v.played,1); assert.equal(p.v.muted,false);
p.v.onplaying(); assert.equal(p.enviados.at(-1).acao,'avatar_inicio');
p.receber({tipo:'avatar_parar',id:'b'.repeat(32)}); assert.equal(p.v.hidden,false);
p.v.onended(); assert.equal(p.enviados.at(-1).acao,'avatar_fim'); assert.equal(p.v.hidden,true); assert.equal(p.v.src,undefined);
p.receber({tipo:'avatar_video',id,url:'https://externo/video.mp4'});
assert.equal(p.enviados.at(-1).acao,'avatar_erro');assert.equal(p.v.played,1);
p.receber({tipo:'avatar_video',id,url});
p.receber({tipo:'config',avatarAnimado:false});
assert.equal(p.v.hidden,true); assert.equal(p.v.src,undefined);
const m = criar(true);
m.receber({tipo:'config',avatarAnimado:true});m.receber({tipo:'avatar_video',id,url,tempo:1.5});
assert.equal(m.v.muted,true);m.v.duration=2.8;m.v.onloadedmetadata();assert.equal(m.v.currentTime,1.5);
m.v.onplaying();m.v.onended();assert.equal(m.enviados.length,0,'mini nao duplica audio ou confirma o video principal');
console.log('OK: opt-in, ponte, reproducao, fonte local, cancelamento, mini muda e sincronizacao ao abrir.');
