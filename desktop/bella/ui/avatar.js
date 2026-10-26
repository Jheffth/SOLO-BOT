/* O video contem a propria trilha de voz: o espelho da Mini-Bella e sempre mudo. */
(() => {
  'use strict';
  const ponte = window.chrome && window.chrome.webview;
  const mini = new URLSearchParams(location.search).get('mini') === '1';
  const cfg = document.getElementById('cfg-avatar');
  const motor = document.getElementById('avatar-motor');
  const status = document.getElementById('avatar-motor-status');
  const videos = [];
  let atual = null, habilitado = false;
  const enviar = (acao, dados = {}) => { if (ponte) ponte.postMessage(Object.assign({ acao }, dados)); };
  const aviso = document.createElement('p');
  aviso.className = 'avatar-progresso'; aviso.hidden = true; aviso.setAttribute('role', 'status');
  const alvo = mini ? document.getElementById('mini') : document.querySelector('.presenca');
  if (alvo) alvo.insertAdjacentElement('afterend', aviso);
  Array.from(document.querySelectorAll(mini ? '.mini-av' : '#app .presenca [data-avatar="grande"]')).slice(0, 1).forEach(el => {
    const v = document.createElement('video');
    v.className = 'avatar-video'; v.hidden = true; v.playsInline = true; v.preload = 'auto';
    // Apenas um elemento no principal pode tocar som, inclusive quando a janela estiver oculta.
    v.muted = mini || videos.length > 0;
    el.appendChild(v); videos.push(v);
  });
  function parar(id) {
    if (id && atual && atual !== id) return;
    atual = null;
    videos.forEach(v => { v.onplaying = v.onended = v.onerror = v.onloadedmetadata = null; v.pause(); v.removeAttribute('src'); v.load(); v.hidden = true; });
    document.body.classList.remove('avatar-em-video');
  }
  function receber(m) {
    if (m.tipo === 'config') {
      habilitado = !!m.avatarAnimado;
      if (cfg) cfg.checked = habilitado;
      if (status) status.textContent = m.avatarDisponivel ? 'Instalação local encontrada. A animação só roda com a opção marcada.' : 'Selecione a instalação local para ativar a animação.';
      if (!habilitado && atual) { const id = atual; parar(); if (!mini) enviar('avatar_fim', { id }); }
    }
    if (m.tipo === 'estado') {
      if (motor) motor.disabled = !!m.ocupada;
      if (cfg) cfg.disabled = !!m.ocupada && !habilitado;
    }
    if (m.tipo === 'avatar_estado') {
      const etapas = { preparando: 'Preparando avatar…', audio: 'Conferindo áudio…', modelo: 'Carregando motor de animação…', geracao: 'Animando a foto…', pronto: 'Vídeo pronto.', reproduzindo: 'Bella falando' };
      const match = /^quadros:(\d{1,3})$/.exec(m.etapa || '');
      aviso.textContent = match ? 'Animando a foto: ' + Math.min(100, Number(match[1])) + '%' : etapas[m.etapa] || '';
      aviso.hidden = !aviso.textContent;
    }
    if (m.tipo === 'avatar_parar') parar(m.id);
    if (m.tipo !== 'avatar_video') return;
    if (!habilitado || !/^[a-f0-9]{32}$/.test(m.id || '') || !/^data:video\/mp4;base64,[A-Za-z0-9+/=]+$/.test(m.url || '') || m.url.length > 23 * 1024 * 1024) {
      if (!mini) enviar('avatar_erro', { id: m.id }); return;
    }
    parar(); atual = m.id;
    if (!videos.length) { if (!mini) enviar('avatar_erro', { id: m.id }); return; }
    document.body.classList.add('avatar-em-video');
    videos.forEach((v, index) => {
      const id = m.id;
      const principal = !mini && index === 0;
      v.onplaying = () => { if (atual === id && principal) enviar('avatar_inicio', { id }); };
      v.onended = () => { if (atual !== id) return; if (principal) enviar('avatar_fim', { id }); parar(id); };
      v.onerror = () => { if (atual !== id) return; if (principal) enviar('avatar_erro', { id }); parar(id); };
      v.onloadedmetadata = () => { if (atual === id && mini && Number.isFinite(m.tempo) && m.tempo > 0) v.currentTime = Math.min(m.tempo, Math.max(0, v.duration - 0.05)); };
      v.src = m.url; v.hidden = false;
      v.play().catch(() => { if (atual === id) { if (principal) enviar('avatar_erro', { id }); parar(id); } });
    });
  }
  if (cfg) cfg.onchange = () => enviar('preferencias', { avatarAnimado: cfg.checked });
  if (motor) motor.onclick = () => enviar('avatar_motor');
  if (ponte) ponte.addEventListener('message', e => receber(e.data));
})();
