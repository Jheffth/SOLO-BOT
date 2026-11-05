const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const fonte = fs.readFileSync('desktop/bella/ui/bella.js', 'utf8');
function elemento() {
  return {style: {}, classList: {toggle() {}}, setAttribute(k, v) { this[k] = v; }};
}
const ids = Object.fromEntries(['btn-recortar', 'btn-remover', 'arquivo', 'soltar', 'btn-escolher',
  'btn-trocar-foto', 'foto-origem', 'modelo-nome', 'foto-nome', 'cfg-chave', 'cfg-servidor'].map(id => [id, elemento()]));
ids['cfg-chave'].value = 'chave em edição';
ids['cfg-servidor'].value = 'servidor em edição';
const avatares = [elemento(), elemento(), elemento()]; // principal, resposta e Mini-Bella
const previa = elemento();
const contexto = {MINI: false, config: {aparencia: 'foto'}, $: id => ids[id],
  document: {body: elemento(), querySelectorAll: s => s === '[data-avatar]' ? avatares : [previa]}};
vm.createContext(contexto);
const inicio = fonte.indexOf('  function aplicarAvatar()');
const fim = fonte.indexOf('  function aplicarConfig(c)', inicio);
assert.ok(inicio >= 0 && fim > inicio);
vm.runInContext(fonte.slice(inicio, fim), contexto);
contexto.aplicarPerfil({foto: 'data:image/jpeg;base64,AAAA', fotoModels: true, modeloNome: 'Kellen Iara'});
assert.ok(avatares.every(a => a.style.backgroundImage.includes('AAAA')));
assert.equal(ids.arquivo.disabled, true);
assert.equal(ids['modelo-nome'].textContent, 'Kellen Iara');
assert.equal(ids['foto-nome'].textContent, 'Foto de Kellen Iara');
assert.ok(ids['foto-origem'].textContent.includes('Kellen Iara'));
contexto.aplicarPerfil({foto: 'data:image/jpeg;base64,BBBB', fotoModels: true, modeloNome: 'Bella'});
assert.ok(avatares.every(a => a.style.backgroundImage.includes('BBBB') && !a.style.backgroundImage.includes('AAAA')));
assert.equal(ids['modelo-nome'].textContent, 'Bella');
contexto.aplicarPerfil({foto: null, fotoModels: true, modeloNome: 'Modelo sem capa'});
assert.ok(avatares.every(a => a.style.backgroundImage === ''));
contexto.aplicarPerfil({foto: 'data:image/jpeg;base64,LOCAL', fotoModels: false});
assert.equal(ids.arquivo.disabled, false);
assert.equal(ids['modelo-nome'].textContent, 'Bella Legado');
assert.ok(avatares.every(a => a.style.backgroundImage.includes('LOCAL')));
assert.equal(ids['cfg-chave'].value, 'chave em edição');
assert.equal(ids['cfg-servidor'].value, 'servidor em edição');
contexto.config.aparencia = 'orbe';
contexto.aplicarPerfil({foto: 'data:image/jpeg;base64,BBBB', fotoModels: true});
assert.ok(avatares.every(a => a.style.backgroundImage === ''));
console.log('OK: troca de retrato, modelo sem capa, legado, Mini-Bella, opção orbe e campos em edição preservados.');

contexto.aplicarPerfil({foto: 'data:image/jpeg;base64,BBBB', fotoModels: true, modeloNome: 'Nova modelo'});
assert.equal(ids['modelo-nome'].textContent, 'Nova modelo');
contexto.aplicarPerfil({modeloNome: 'Modelo renomeada'});
assert.equal(ids['modelo-nome'].textContent, 'Modelo renomeada');
console.log('OK: nome acompanha a foto, retorno ao Legado e renomeação com a mesma capa.');
