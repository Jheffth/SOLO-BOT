/* A escolha de conversa pertence à Conta Solo; o catálogo vem do Models. */
(function () {
  "use strict";
  const alvo = document.querySelector('#models-escolha');
  if (!alvo) return;
  let atual = null;
  let ocupado = false;
  async function carregar() {
    if (ocupado) return;
    try {
      const dados = await Solo.api('/api/conta/models');
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
      for (const modelo of dados.modelos) {
        const card = document.createElement('div'); card.className = 'pilha';
        const botao = document.createElement('button'); botao.type = 'button';
        botao.className = 'btn ' + (atual === modelo.id ? 'primario' : 'pequeno');
        botao.textContent = modelo.nome + (atual === modelo.id ? ' · Em uso' : ' · Usar');
        botao.setAttribute('aria-pressed', String(atual === modelo.id));
        botao.addEventListener('click', () => escolher(modelo.id));
        const descricao = document.createElement('p'); descricao.className = 'muted pequeno';
        descricao.textContent = modelo.descricao;
        card.append(botao, descricao); alvo.append(card);
      }
      if (dados.disponivel && !dados.modelos.length) {
        const vazio = document.createElement('p'); vazio.className = 'muted';
        vazio.textContent = 'Nenhum modelo publicado disponível para sua conta.'; alvo.append(vazio);
      }
    } catch { alvo.textContent = 'Não foi possível carregar Models. Tente novamente em instantes.'; }
  }
  async function escolher(ident) {
    ocupado = true;
    alvo.querySelectorAll('button').forEach(b => b.disabled = true);
    try {
      await Solo.api('/api/conta/models', {method: 'PUT', body: {modelo_id: ident}});
      Solo.toast(ident ? 'Modelo selecionado. Pode conversar pelos seus canais.' : 'Bella (Legado) selecionada.');
    } catch (e) { Solo.toast(e.message); }
    finally { ocupado = false; await carregar(); }
  }
  carregar();
  setInterval(() => { if (!document.hidden) carregar(); }, 30000);
})();
