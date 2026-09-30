/* Solo Bot — utilidades comuns do painel (sem build, sem framework). */
(function () {
  "use strict";

  // Ícones: traço 1.8, 24x24, herdam currentColor.
  const P = {
    mail: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m4 7 8 6 8-6"/>',
    lock: '<rect x="4" y="10" width="16" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    eyeOff: '<path d="M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4M6.6 6.6A17 17 0 0 0 2 12s3.6 7 10 7a9.6 9.6 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    alert: '<path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17.5v.01"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3.2-3.2a4.5 4.5 0 0 0-6.4-6.4L12 5.6"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3.2 3.2a4.5 4.5 0 0 0 6.4 6.4L12 18.4"/>',
    unlink: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3.2-3.2a4.5 4.5 0 0 0-6.4-6.4L12 5.6M14 10a4.5 4.5 0 0 0-6.4 0l-3.2 3.2a4.5 4.5 0 0 0 6.4 6.4L12 18.4M4 4l16 16"/>',
    bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4l2-2Z"/><path d="M10 21h4"/>',
    logout: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/>',
    shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="3"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    chat: '<path d="M4 5h16v11H9l-5 4V5Z"/><path d="M8 9.5h8M8 12.5h5"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
    activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    qr: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 17h3v4h-3"/>',
    telegram: '<path d="M21.5 4.5 2.8 11.4c-.9.4-.9 1.6.1 1.9l4.6 1.5 1.7 5.3c.3.8 1.3 1 1.9.4l2.6-2.5 4.8 3.5c.7.5 1.7.1 1.9-.7L23 5.8c.2-1-.7-1.7-1.5-1.3Z"/><path d="m7.6 14.7 9.9-6.9"/>',
    whatsapp: '<path d="M3.5 20.5 5 16a8.5 8.5 0 1 1 3.1 3.1l-4.6 1.4Z"/><path d="M9 8.6c0 3.3 3 6.4 6.4 6.4l1.2-1.5-2-1-1 .8a4.5 4.5 0 0 1-2.4-2.4l.8-1-1-2-1.5 1.1c-.3.2-.5.5-.5.6Z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/>',
  };
  function icon(nome, extra) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra || ""}>${P[nome] || ""}</svg>`;
  }

  // A marca: um núcleo com duas órbitas — violeta e esmeralda — que se cruzam.
  const LOGO = `<svg viewBox="0 0 40 40" aria-hidden="true">
    <defs><linearGradient id="lg-solo" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#a78bfa"/><stop offset=".5" stop-color="#22d3ee"/><stop offset="1" stop-color="#34d399"/></linearGradient></defs>
    <rect x="1" y="1" width="38" height="38" rx="12" fill="url(#lg-solo)" opacity=".16"/>
    <rect x="1.5" y="1.5" width="37" height="37" rx="11.5" fill="none" stroke="url(#lg-solo)" opacity=".6"/>
    <ellipse cx="20" cy="20" rx="12.5" ry="5.2" fill="none" stroke="#a78bfa" stroke-width="1.6" transform="rotate(-35 20 20)"/>
    <ellipse cx="20" cy="20" rx="12.5" ry="5.2" fill="none" stroke="#34d399" stroke-width="1.6" transform="rotate(35 20 20)"/>
    <circle cx="20" cy="20" r="4.2" fill="url(#lg-solo)"/>
    <circle cx="29.8" cy="13.2" r="1.9" fill="#a78bfa"/><circle cx="10.2" cy="13.2" r="1.9" fill="#34d399"/>
  </svg>`;

  async function api(caminho, opts) {
    opts = opts || {};
    const cfg = { method: opts.method || "GET", credentials: "same-origin", headers: {} };
    if (opts.body !== undefined) { cfg.headers["Content-Type"] = "application/json"; cfg.body = JSON.stringify(opts.body); }
    let r;
    try { r = await fetch(caminho, cfg); }
    catch (e) { throw new Error("Sem conexão com o servidor."); }
    let dados = null;
    try { dados = await r.json(); } catch (e) { /* corpo vazio */ }
    if (!r.ok) {
      let msg = dados && dados.detail;
      if (Array.isArray(msg)) msg = traduzirValidacao(msg);
      const erro = new Error(msg || `Erro ${r.status}`);
      erro.status = r.status;
      throw erro;
    }
    return dados;
  }

  function traduzirValidacao(lista) {
    const d = lista[0] || {};
    const campo = (d.loc || []).slice(-1)[0];
    const nomes = { senha: "A senha", nome: "O nome", email: "O e-mail", nova: "A nova senha" };
    if (d.type === "string_too_short") return `${nomes[campo] || "O campo"} está curto demais.`;
    return "Confira os campos.";
  }

  let caixaToasts;
  function toast(texto, tipo) {
    tipo = tipo || "ok";
    if (!caixaToasts) { caixaToasts = document.createElement("div"); caixaToasts.className = "toasts"; caixaToasts.setAttribute("role", "status"); document.body.appendChild(caixaToasts); }
    const el = document.createElement("div");
    el.className = `toast ${tipo}`;
    el.innerHTML = icon(tipo === "ok" ? "check" : "alert") + `<span></span>`;
    el.querySelector("span").textContent = texto;
    caixaToasts.appendChild(el);
    setTimeout(() => { el.style.transition = "opacity .3s, transform .3s"; el.style.opacity = "0"; el.style.transform = "translateY(8px)"; }, 3400);
    setTimeout(() => el.remove(), 3800);
  }

  function carregando(btn, sim) {
    if (sim) { btn.dataset.html = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="gira"></span>'; }
    else if (btn.dataset.html) { btn.disabled = false; btn.innerHTML = btn.dataset.html; }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function iniciais(nome) {
    const p = (nome || "?").trim().split(/\s+/);
    return ((p[0] || "")[0] + ((p.length > 1 ? p[p.length - 1][0] : "") || "")).toUpperCase();
  }

  function tempoRelativo(iso) {
    const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    if (s < 60) return "agora";
    if (s < 3600) return `há ${Math.floor(s / 60)} min`;
    if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
    const dias = Math.floor(s / 86400);
    return dias === 1 ? "ontem" : `há ${dias} dias`;
  }

  function ceu() {
    if (document.querySelector(".ceu")) return;
    const c = document.createElement("div");
    c.className = "ceu";
    c.innerHTML = '<div class="aurora a1"></div><div class="aurora a2"></div><div class="aurora a3"></div>';
    document.body.prepend(c);
  }

  function tema() {
    const salvo = (() => { try { return localStorage.getItem("solo-tema"); } catch (e) { return null; } })();
    if (salvo) document.documentElement.dataset.theme = salvo;
  }
  function alternarTema() {
    const atual = document.documentElement.dataset.theme ||
      (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    const novo = atual === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = novo;
    try { localStorage.setItem("solo-tema", novo); } catch (e) { /* ok */ }
    return novo;
  }
  tema();

  function modal(html, aoFechar) {
    const veu = document.createElement("div");
    veu.className = "veu";
    veu.innerHTML = `<div class="modal" role="dialog" aria-modal="true"><button class="btn fantasma pequeno fechar" aria-label="Fechar">${icon("x")}</button>${html}</div>`;
    const fechar = () => { veu.remove(); document.removeEventListener("keydown", tecla); aoFechar && aoFechar(); };
    const tecla = e => { if (e.key === "Escape") fechar(); };
    veu.addEventListener("click", e => { if (e.target === veu) fechar(); });
    veu.querySelector(".fechar").onclick = fechar;
    document.addEventListener("keydown", tecla);
    document.body.appendChild(veu);
    return { el: veu.querySelector(".modal"), fechar };
  }

  window.Solo = { icon, LOGO, api, toast, carregando, esc, iniciais, tempoRelativo, ceu, alternarTema, modal };
})();
