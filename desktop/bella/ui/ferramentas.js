/* Bella — painel lateral: atalhos de comandos e montagem do pedido com opções clicáveis.
   Usa window.FERRAMENTAS_GRUPOS (ferramentas-dados.js) e window.bellaApi (bella.js). */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const GRUPOS = window.FERRAMENTAS_GRUPOS || [];
  const COMANDOS = [
    { cmd: "/prompt", nome: "Prompt", dica: "Foto realista sensual" },
    { cmd: "/promptmodelo", nome: "Modelo", dica: "Cria a modelo (use com imagem de referência)" },
    { cmd: "/promptroupa", nome: "Roupa", dica: "Veste uma roupa em uma imagem de referência" },
    { cmd: "/posehot", nome: "Pose", dica: "Pose sensual" },
    { cmd: "/promptcriativo", nome: "Criativo", dica: "Ideia nova, fora da biblioteca" }
  ];
  const LIMITE = 1500;      // o servidor aceita 2000 caracteres por pedido
  let comando = COMANDOS[0].cmd;
  const itens = [];
  let abertos = {};

  const el = (tag, cls, texto) => { const e = document.createElement(tag); if (cls) e.className = cls; if (texto != null) e.textContent = texto; return e; };
  const sortear = lista => lista[Math.floor(Math.random() * lista.length)];
  const aviso = t => { if (window.bellaApi) window.bellaApi.aviso(t); };

  function texto() {
    const extra = $("montar-extra").value.trim();
    return itens.concat(extra ? [extra] : []).join(", ");
  }
  function atualizarResumo() {
    const caixa = $("montar-itens"); caixa.textContent = "";
    if (!itens.length) caixa.appendChild(el("span", "vazio", "Nada escolhido ainda. Toque nas opções abaixo."));
    itens.forEach((t, i) => {
      const tag = el("span", "etiqueta", t);
      const x = el("button", "etiqueta-x", "×"); x.type = "button"; x.setAttribute("aria-label", "Tirar: " + t);
      x.onclick = () => { itens.splice(i, 1); atualizarResumo(); marcarChips(); };
      tag.appendChild(x); caixa.appendChild(tag);
    });
    const n = texto().length;
    $("montar-conta").textContent = itens.length + " item(ns) · " + n + "/" + LIMITE;
    $("montar-conta").classList.toggle("estouro", n > LIMITE);
  }
  function marcarChips() {
    document.querySelectorAll("#montar-grupos .chip").forEach(c => c.classList.toggle("on", itens.indexOf(c.dataset.t) >= 0));
  }
  function alternar(t) {
    const i = itens.indexOf(t);
    if (i >= 0) itens.splice(i, 1); else itens.push(t);
    atualizarResumo(); marcarChips();
  }
  function adicionar(t) { if (t && itens.indexOf(t) < 0) { itens.push(t); atualizarResumo(); marcarChips(); } }

  function montarCombo(c) {
    const caixa = el("div", "combo");
    caixa.appendChild(el("b", "combo-nome", c.nome));
    const linha = el("div", "combo-linha");
    const mk = lado => {
      const s = document.createElement("select"); s.setAttribute("aria-label", c.nome + " — " + lado.rotulo);
      lado.itens.forEach(t => { const o = document.createElement("option"); o.value = t; o.textContent = t; s.appendChild(o); });
      return s;
    };
    const a = mk(c.a), b = mk(c.b);
    linha.appendChild(el("label", null, c.a.rotulo)); linha.appendChild(a);
    linha.appendChild(el("label", null, c.b.rotulo)); linha.appendChild(b);
    caixa.appendChild(linha);
    const acoes = el("div", "combo-acoes");
    const frase = () => c.modelo.replace("{a}", a.value).replace("{b}", b.value).replace(/\s+/g, " ").trim();
    const prev = el("small", "combo-previa"); const atual = () => { prev.textContent = frase(); };
    a.onchange = atual; b.onchange = atual; atual();
    const add = el("button", "btn mini", "Adicionar"); add.type = "button"; add.onclick = () => adicionar(frase());
    const dado = el("button", "btn mini", "🎲 Sortear"); dado.type = "button";
    dado.onclick = () => { a.selectedIndex = Math.floor(Math.random() * a.options.length); b.selectedIndex = Math.floor(Math.random() * b.options.length); atual(); adicionar(frase()); };
    acoes.appendChild(add); acoes.appendChild(dado);
    caixa.appendChild(prev); caixa.appendChild(acoes);
    return caixa;
  }
  function corpoGrupo(g, corpo) {
    corpo.textContent = "";
    (g.combos || []).forEach(c => corpo.appendChild(montarCombo(c)));
    if (g.chips && g.chips.length) {
      const topo = el("div", "chips-topo");
      const dado = el("button", "btn mini", "🎲 Uma ao acaso"); dado.type = "button"; dado.onclick = () => adicionar(sortear(g.chips));
      topo.appendChild(el("small", null, g.chips.length + " opções")); topo.appendChild(dado);
      corpo.appendChild(topo);
      const lista = el("div", "chips");
      g.chips.forEach(t => {
        const b = el("button", "chip", t); b.type = "button"; b.dataset.t = t;
        if (itens.indexOf(t) >= 0) b.classList.add("on");
        b.onclick = () => alternar(t); lista.appendChild(b);
      });
      corpo.appendChild(lista);
    }
  }
  function montarGrupos() {
    const raiz = $("montar-grupos"); raiz.textContent = "";
    GRUPOS.forEach(g => {
      const d = document.createElement("details"); d.className = "grupo"; d.dataset.id = g.id;
      const total = (g.chips || []).length + (g.combos || []).reduce((n, c) => n + c.a.itens.length * c.b.itens.length, 0);
      d.appendChild(el("summary", null, g.icone + " " + g.titulo + " · " + total));
      const corpo = el("div", "grupo-corpo"); d.appendChild(corpo);
      const abrir = () => { if (!corpo.childNodes.length) corpoGrupo(g, corpo); };
      d.addEventListener("toggle", () => { abertos[g.id] = d.open; if (d.open) abrir(); });
      raiz.appendChild(d);
    });
  }
  function filtrar() {
    const q = $("montar-busca").value.trim().toLowerCase();
    const raiz = $("montar-grupos");
    if (!q) { montarGrupos(); return; }
    raiz.textContent = "";
    const achados = el("div", "chips");
    GRUPOS.forEach(g => (g.chips || []).forEach(t => {
      if (t.toLowerCase().indexOf(q) < 0) return;
      const b = el("button", "chip", t); b.type = "button"; b.dataset.t = t; if (itens.indexOf(t) >= 0) b.classList.add("on");
      b.title = g.titulo; b.onclick = () => alternar(t); achados.appendChild(b);
    }));
    GRUPOS.forEach(g => (g.combos || []).forEach(c => {
      const casa = lado => lado.itens.some(t => t.toLowerCase().indexOf(q) >= 0);
      if (c.nome.toLowerCase().indexOf(q) >= 0 || g.titulo.toLowerCase().indexOf(q) >= 0 || casa(c.a) || casa(c.b)) {
        const caixa = montarCombo(c);
        caixa.querySelectorAll("select").forEach(sel => {      // já deixa selecionada a opção que a busca achou
          for (let i = 0; i < sel.options.length; i++) if (sel.options[i].value.toLowerCase().indexOf(q) >= 0) { sel.selectedIndex = i; sel.dispatchEvent(new Event("change")); break; }
        });
        raiz.appendChild(caixa);
      }
    }));
    if (achados.childNodes.length) raiz.appendChild(achados); else if (!raiz.childNodes.length) raiz.appendChild(el("p", "vazio", "Nenhuma opção com esse nome. Escreva no campo \"Mais detalhes\"."));
  }
  function surpresa() {
    const cand = GRUPOS.filter(g => ["idade", "corpo", "cabelo", "make", "tattoo", "marcas", "pierc", "roupa", "cenario", "luz", "pose", "camera", "momento"].indexOf(g.id) >= 0);
    const escolhidos = cand.slice().sort(() => Math.random() - .5).slice(0, 5 + Math.floor(Math.random() * 3));
    escolhidos.forEach(g => {
      const pool = [];
      (g.chips || []).forEach(t => pool.push(() => t));
      (g.combos || []).forEach(c => { for (let k = 0; k < 8; k++) pool.push(() => c.modelo.replace("{a}", sortear(c.a.itens)).replace("{b}", sortear(c.b.itens)).replace(/\s+/g, " ").trim()); });
      adicionar(sortear(pool)());
    });
  }
  function enviar(cmd, corpo) {
    const api = window.bellaApi; if (!api) return;
    if (api.ocupada()) return aviso("Espere eu terminar o pedido anterior.");
    const t = (cmd + (corpo ? " " + corpo : "")).trim();
    if (t.length > LIMITE + 40) return aviso("O pedido ficou muito grande. Tire alguns itens.");
    api.fechar(); api.enviar(t);
  }

  function iniciar() {
    if (!$("montar-grupos")) return;
    const atalhos = $("atalhos");
    COMANDOS.forEach(c => {
      const b = el("button", "btn atalho", c.cmd); b.type = "button"; b.title = c.dica + " — envia agora ao chat";
      b.onclick = () => enviar(c.cmd, ""); atalhos.appendChild(b);
    });
    const seg = $("montar-cmd");
    COMANDOS.forEach(c => {
      const b = el("button", "seg-bt", c.nome); b.type = "button"; b.title = c.cmd + " — " + c.dica; b.dataset.cmd = c.cmd;
      b.setAttribute("aria-pressed", String(c.cmd === comando)); if (c.cmd === comando) b.classList.add("on");
      b.onclick = () => {
        comando = c.cmd;
        seg.querySelectorAll(".seg-bt").forEach(x => { const on = x.dataset.cmd === comando; x.classList.toggle("on", on); x.setAttribute("aria-pressed", String(on)); });
        $("montar-dica").textContent = c.cmd + " — " + c.dica;
      };
      seg.appendChild(b);
    });
    $("montar-dica").textContent = COMANDOS[0].cmd + " — " + COMANDOS[0].dica;
    $("montar-enviar").onclick = () => enviar(comando, texto());
    $("montar-campo").onclick = () => { if (window.bellaApi) { window.bellaApi.inserir((comando + " " + texto()).trim()); window.bellaApi.fechar(); } };
    $("montar-limpar").onclick = () => { itens.length = 0; $("montar-extra").value = ""; atualizarResumo(); marcarChips(); };
    $("montar-sorte").onclick = surpresa;
    $("montar-extra").addEventListener("input", atualizarResumo);
    $("montar-busca").addEventListener("input", filtrar);
    montarGrupos(); atualizarResumo();
  }
  iniciar();
})();
