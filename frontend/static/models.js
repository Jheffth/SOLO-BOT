/* A escolha de conversa pertence à Conta Solo; o catálogo vem do Models. */
(function () {
  "use strict";
  const alvo = document.querySelector('#models-escolha');
  if (!alvo) return;
  let atual = null;
  let ocupado = false;
  let revisao = 0;
  async function carregar() {
    if (ocupado) return;
    const pedido = ++revisao;
    try {
      const dados = await Solo.api('/api/conta/models');
      if (ocupado || pedido !== revisao) return;
      atual = dados.modelo_id;
      alvo.replaceChildren();
      const legado = document.createElement('button');
      legado.type = 'button'; legado.className = 'btn ' + (!atual ? 'primario' : 'pequeno');
      legado.textContent = 'Bella (Legado)' + (!atual ? ' · Em uso' : '');
      legado.setAttribute('aria-pressed', String(!atual));
      legado.addEventListener('click', () => escolher(null));
      alvo.append(legado);
      const titulo = document.createElement('h3'); titulo.textContent = 'Models'; alvo.append(titulo);
      if (!dados.disponivel) {
        const aviso = document.createElement('p'); aviso.className = 'muted';
        aviso.textContent = dados.aviso || 'Models indisponível no momento. Sua escolha foi preservada.';
        alvo.append(aviso);
      }
      const marcadas = (dados.presentes && dados.presentes.length) ? dados.presentes : (atual ? [atual] : []);
      if (dados.cena_disponivel && dados.modelos.length > 1) {
        const dica = document.createElement('p'); dica.className = 'faint pequeno';
        dica.textContent = 'Marque até 3 para conversar com várias na mesma cena; desmarque para tirar uma da cena. A Bella (Legado) conversa sozinha.';
        alvo.append(dica);
      }
      for (const modelo of dados.modelos) {
        const card = document.createElement('div'); card.className = 'pilha';
        if (dados.cena_disponivel) {
          // Arquiteto: chave liga/desliga; mais de uma ligada vira cena.
          const linha = document.createElement('div'); linha.className = 'linha';
          const ligada = marcadas.includes(modelo.id);
          const chave = document.createElement('button'); chave.type = 'button'; chave.className = 'chave';
          chave.setAttribute('role', 'switch'); chave.setAttribute('aria-checked', String(ligada));
          chave.setAttribute('aria-label', (ligada ? 'Tirar ' : 'Colocar ') + modelo.nome + ' na conversa');
          chave.addEventListener('click', () => alternar(modelo.id, marcadas));
          const nome = document.createElement('b'); nome.textContent = modelo.nome +
            (ligada ? (marcadas.length > 1 ? (modelo.id === atual ? ' · Na cena (anfitriã)' : ' · Na cena') : ' · Em uso') : '');
          linha.append(chave, nome); card.append(linha);
        } else {
          const botao = document.createElement('button'); botao.type = 'button';
          botao.className = 'btn ' + (atual === modelo.id ? 'primario' : 'pequeno');
          botao.textContent = modelo.nome + (atual === modelo.id ? ' · Em uso' : ' · Usar');
          botao.setAttribute('aria-pressed', String(atual === modelo.id));
          botao.addEventListener('click', () => escolher(modelo.id));
          card.append(botao);
        }
        const descricao = document.createElement('p'); descricao.className = 'muted pequeno';
        descricao.textContent = modelo.descricao;
        card.append(descricao); alvo.append(card);
      }
      if (dados.disponivel && !dados.modelos.length) {
        const vazio = document.createElement('p'); vazio.className = 'muted';
        vazio.textContent = 'Nenhum modelo publicado disponível para sua conta.'; alvo.append(vazio);
      }
    } catch {
      if (!ocupado && pedido === revisao) alvo.textContent = 'Não foi possível carregar Models. Tente novamente em instantes.';
    }
  }
  async function escolher(ident) {
    ocupado = true;
    ++revisao;
    alvo.querySelectorAll('button').forEach(b => b.disabled = true);
    try {
      await Solo.api('/api/conta/models', {method: 'PUT', body: {modelo_id: ident}});
      Solo.toast(ident ? 'Modelo selecionado. Pode conversar pelos seus canais.' : 'Bella (Legado) selecionada.');
    } catch (e) { Solo.toast(e.message); }
    finally { ocupado = false; await carregar(); }
  }
  async function alternar(ident, marcadas) {
    const nova = marcadas.includes(ident) ? marcadas.filter(i => i !== ident) : [...marcadas, ident];
    if (!nova.length) return escolher(null);          // nenhuma marcada: volta à Bella (Legado)
    if (nova.length > 3) { Solo.toast('A cena comporta até 3 modelos.'); return; }
    ocupado = true;
    ++revisao;
    alvo.querySelectorAll('button').forEach(b => b.disabled = true);
    try {
      const r = await Solo.api('/api/conta/models/cena', {method: 'PUT', body: {modelos: nova}});
      Solo.toast(r.presentes.length > 1 ? 'Cena atualizada. Pode conversar pelos seus canais.' : 'Modelo selecionado. Pode conversar pelos seus canais.');
    } catch (e) { Solo.toast(e.message); }
    finally { ocupado = false; await carregar(); }
  }
  carregar();
  setInterval(() => { if (!document.hidden) carregar(); }, 30000);
})();
