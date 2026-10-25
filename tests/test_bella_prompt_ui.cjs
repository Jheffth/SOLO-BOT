const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class Elemento {
  constructor(tag) {this.tag = tag; this.children = []; this.attrs = {}; this.classes = new Set(); this.value = '';
    this.classList = {add: c => this.classes.add(c), remove: c => this.classes.delete(c), toggle: (c, on) => on ? this.classes.add(c) : this.classes.delete(c)};}
  appendChild(x) {this.children.push(x);}
  setAttribute(k, v) {this.attrs[k] = v;}
  focus() {} select() {this.selecionado = true;}
}
const copiados = [];
const contexto = {document: {createElement: t => new Elemento(t), execCommand: () => true}, setTimeout: () => 0,
  navigator: {clipboard: {writeText: async t => { copiados.push(t); }}}};
vm.createContext(contexto);
const fonte = fs.readFileSync('desktop/bella/ui/bella.js', 'utf8');
vm.runInContext(fonte.slice(fonte.indexOf('  const RE_PROMPT'), fonte.indexOf('  function montarResposta(')), contexto);
const prompt = 'Use a imagem da nova modelo como referência principal. ' + 'x'.repeat(700);
assert.equal(contexto.ehPrompt(prompt), true);
assert.equal(contexto.ehPrompt('Oi, tudo bem?'), false);
assert.equal(contexto.ehPrompt('Use a imagem da nova modelo como referência'), false);   // curto demais: conversa comum
const bolha = new Elemento('div');
contexto.montarPrompt(bolha, prompt);
assert.equal(bolha.classes.has('prompt'), true);
const [topo, caixa] = bolha.children;
assert.equal(caixa.tag, 'textarea');
assert.equal(caixa.readOnly, true);
assert.equal(caixa.value, prompt.trim());
const botao = topo.children[1];
botao.onclick().then ? 0 : 0;
(async () => {
  await new Promise(r => setImmediate(r));
  assert.deepEqual(copiados, [prompt.trim()]);
  assert.equal(botao.textContent, 'Copiado ✓');
  console.log('ok');
})();
