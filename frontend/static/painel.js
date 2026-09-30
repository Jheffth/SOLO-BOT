/* Painel da Conta Solo */
(async function () {
  "use strict";
  const { icon, api, esc, toast, tempoRelativo, modal, carregando } = Solo;

  const CANAIS = {
    telegram: { nome: "Telegram", cor: "#229ed9", icone: "telegram", verbo: "Abrir no Telegram",
                texto: "Um toque no link e o chat já chega vinculado. Nada para digitar." },
    whatsapp: { nome: "WhatsApp", cor: "#1faa59", icone: "whatsapp", verbo: "Abrir no WhatsApp",
                texto: "A mensagem com o código já vai pronta. É só enviar." },
  };

  await Solo.topo("painel");
  let dados;

  // ── Saudação ──
  const h = new Date().getHours();
  const periodo = h < 5 ? "Boa noite" : h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
  document.getElementById("data").textContent = new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });

  async function carregar() {
    dados = await api("/api/conta");
    render();
    return dados;
  }

  function render() {
    const c = dados.conta;
    document.getElementById("ola").innerHTML = `${periodo}, <span class="grad">${esc(c.nome.split(" ")[0])}</span>`;
    const nCanais = dados.canais.filter(x => x.conectado).length;
    const nSist = dados.sistemas.filter(x => x.conectado).length;
    document.getElementById("ola-sub").textContent =
      nCanais && nSist ? `${nSist} ${nSist === 1 ? "sistema" : "sistemas"} respondendo por ${nCanais === 2 ? "Telegram e WhatsApp" : dados.canais.find(x => x.conectado).canal === "telegram" ? "Telegram" : "WhatsApp"}.`
      : "Faltam poucos passos para o bot falar por você.";
    document.getElementById("nome").value = document.activeElement.id === "nome" ? document.getElementById("nome").value : c.nome;
    document.getElementById("email").value = c.usuario ? c.usuario + (c.email ? `  ·  ${c.email}` : "") : (c.email || "");
    renderProgresso(nCanais > 0, nSist > 0);
    renderCanais();
    document.querySelectorAll("#voz-opcoes [data-voz]").forEach(b =>
      b.setAttribute("aria-checked", String(b.dataset.voz === (c.voz || "audio"))));
    renderSistemas();
    renderAtividade();
    renderComandos();
  }

  // Os comandos vêm do manifesto de cada sistema: comando novo lá aparece aqui sozinho.
  function renderComandos() {
    const alvo = document.getElementById("cmds-sistemas");
    const blocos = dados.sistemas.filter(s => s.conectado && (s.comandos || []).length).map(s => {
      const cmds = s.comandos.filter(c => c.comando !== "/ajuda").slice(0, 6);
      return `<div class="cmds-sis"><b class="${s.chave === "fin" ? "fin" : "rot"}">${esc(s.emoji)} ${esc(s.nome.replace("Solo ", ""))}</b>
        <ul class="comandos">${cmds.map(c => `<li><code>/${esc(s.chave)} ${esc(c.comando.slice(1))}</code><span>${esc(c.descricao)}</span></li>`).join("")}</ul></div>`;
    });
    alvo.innerHTML = blocos.join("");
  }

  function renderProgresso(canal, sistema) {
    const feitos = 1 + canal + sistema;
    const circ = 2 * Math.PI * 24;
    const passo = (ok, t) => `<span class="${ok ? "feito" : ""}">${icon(ok ? "check" : "clock")}${t}</span>`;
    document.getElementById("progresso").innerHTML = `
      <div class="anel"><svg viewBox="0 0 58 58"><defs><linearGradient id="anel-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a78bfa"/><stop offset=".5" stop-color="#22d3ee"/><stop offset="1" stop-color="#34d399"/></linearGradient></defs>
        <circle class="fundo" cx="29" cy="29" r="24"/><circle class="frente" cx="29" cy="29" r="24" stroke-dasharray="${circ}" stroke-dashoffset="${circ}"/></svg><b>${feitos}/3</b></div>
      <div class="passos">${passo(true, "Conta Solo criada")}${passo(canal, "Um canal conectado")}${passo(sistema, "Um sistema conectado")}</div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const f = document.querySelector(".anel .frente"); if (f) f.style.strokeDashoffset = circ * (1 - feitos / 3);
    }));
  }

  function renderCanais() {
    document.getElementById("canais").innerHTML = dados.canais.map(x => {
      const m = CANAIS[x.canal];
      const estado = x.conectado ? `<span class="chip ok"><span class="ponto"></span>Conectado</span>`
        : x.disponivel ? `<span class="chip off">Não conectado</span>` : `<span class="chip aguarda">Indisponível</span>`;
      const corpo = x.conectado
        ? `<p class="muted pequeno">${x.rotulo ? `Como <b style="color:var(--text)">${esc(x.rotulo)}</b> · ` : ""}desde ${new Date(x.desde + "Z").toLocaleDateString("pt-BR")}</p>
           <div class="avisos-linha"><button class="chave" role="switch" aria-checked="${x.avisos}" data-avisos="${x.canal}" aria-label="Receber avisos por ${m.nome}"></button>Receber avisos por aqui</div>`
        : `<p class="muted pequeno">${x.disponivel ? m.texto : "O servidor ainda não foi configurado para este canal."}</p>`;
      const acoes = x.conectado
        ? `<button class="btn pequeno fantasma perigo" data-sair-canal="${x.canal}">${icon("unlink")}Desconectar</button>`
        : `<button class="btn pequeno primario" data-ligar="${x.canal}" ${x.disponivel ? "" : "disabled"}>${icon("link")}Conectar</button>`;
      return `<article class="cartao vidro canal" style="--c:${m.cor}">
        <div class="linha entre"><span class="marca-canal">${icon(m.icone)}</span>${estado}</div>
        <div><h3>${m.nome}</h3></div>${corpo}<div class="rodape">${acoes}</div></article>`;
    }).join("");
  }

  function renderSistemas() {
    document.getElementById("sistemas").innerHTML = dados.sistemas.map(s => {
      const estado = s.conectado ? `<span class="chip ok"><span class="ponto"></span>Conectado</span>` : `<span class="chip off">Não conectado</span>`;
      const corpo = s.conectado
        ? `<div class="id-remoto">${icon("user")}<span>Lá você é <b>${esc(s.nome_remoto || "—")}</b></span></div>`
        : `<div class="como"><ol><li>Abra o ${esc(s.nome)}</li><li>Vá em <b>Bots</b></li><li>Toque em <b>Conectar ao Solo Bot</b></li></ol></div>`;
      const acoes = [
        s.painel ? `<a class="btn pequeno" href="${esc(s.painel)}" target="_blank" rel="noopener">${icon("external")}Abrir ${esc(s.nome.replace("Solo ", ""))}</a>` : "",
        s.conectado ? `<button class="btn pequeno fantasma perigo" data-sair-sistema="${s.chave}">${icon("unlink")}Desconectar</button>` : "",
      ].join("");
      return `<article class="cartao vidro sistema ${s.conectado ? "conectado" : ""}" style="--c:${esc(s.cor)}">
        <div class="linha entre"><span class="emblema">${esc(s.emoji)}</span>${estado}</div>
        <div><h3 class="linha" style="gap:.5rem">${esc(s.nome)}${s.conectado ? `<code>/${esc(s.chave)}</code>` : ""}</h3><p class="muted pequeno" style="margin-top:4px">${esc(s.descricao)}</p></div>
        ${corpo}<div class="rodape">${acoes}</div></article>`;
    }).join("");
  }

  const ICONE_ATIV = { comando: "chat", aviso: "bell", vinculo: "link", canal: "spark", conta: "user" };
  function renderAtividade() {
    const lista = dados.atividade;
    document.getElementById("ativ-conta").textContent = lista.length ? `${lista.length} recentes` : "vazio";
    const emoji = app => (dados.sistemas.find(s => s.chave === app) || {}).emoji;
    document.getElementById("atividade").innerHTML = lista.length ? lista.map(a => {
      const titulo = a.tipo === "comando" ? (a.resumo === "mensagem" ? "Mensagem" : a.resumo === "toque" ? "Toque num botão" : `Comando ${a.resumo}`) : a.resumo;
      const onde = [a.app && dados.sistemas.find(s => s.chave === a.app)?.nome.replace("Solo ", ""), a.canal && CANAIS[a.canal]?.nome].filter(Boolean).join(" · ");
      return `<li><span class="ic">${a.app && a.tipo !== "vinculo" ? emoji(a.app) : icon(ICONE_ATIV[a.tipo] || "activity")}</span>
        <div><b>${esc(titulo)}</b><small>${onde ? esc(onde) + " · " : ""}${tempoRelativo(a.em)}</small></div></li>`;
    }).join("") : `<li class="vazio" style="display:block">Nada por aqui ainda. Mande um “oi” para o bot.</li>`;
  }

  // ── Conectar um canal ──
  async function ligar(canal) {
    const m = CANAIS[canal];
    let r;
    try { r = await api(`/api/conta/canais/${canal}/codigo`, { method: "POST" }); }
    catch (e) { return toast(e.message, "erro"); }

    const qr = qrcode(0, "M"); qr.addData(r.link); qr.make();
    const expira = new Date(r.expira_em).getTime();
    const { el, fechar } = modal(`
      <div class="conexao" style="--c:${m.cor}">
        <span class="icone-caixa" style="background:${m.cor};border:0;color:#fff">${icon(m.icone)}</span>
        <h2>Conectar ${m.nome}</h2>
        <p class="passo">${canal === "telegram" ? "No celular, aponte a câmera para o código. No computador, use o botão." : "Aponte a câmera ou use o botão: a mensagem abre pronta no WhatsApp."}</p>
        <div class="qr">${qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true })}</div>
        ${r.mensagem ? `<div class="codigo-grande"><span>${esc(r.mensagem)}</span><button class="btn fantasma pequeno" id="copiar" aria-label="Copiar">${icon("copy")}</button></div>` : ""}
        <a class="btn ${canal} bloco" href="${esc(r.link)}" target="_blank" rel="noopener">${icon(m.icone)}${m.verbo}</a>
        <div class="espera"><span class="radar"></span><span id="relogio">Esperando você…</span></div>
      </div>`, () => clearInterval(laco));
    const copiar = el.querySelector("#copiar");
    if (copiar) copiar.onclick = () => navigator.clipboard.writeText(r.mensagem).then(() => toast("Copiado."));

    const relogio = el.querySelector("#relogio");
    let n = 0;
    const laco = setInterval(async () => {
      const resta = Math.max(0, Math.round((expira - Date.now()) / 1000));
      relogio.textContent = resta ? `Esperando você… ${Math.floor(resta / 60)}:${String(resta % 60).padStart(2, "0")}` : "O código expirou. Feche e gere outro.";
      if (!resta) return clearInterval(laco);
      if (++n % 3) return;
      try {
        const d = await api("/api/conta");
        if (d.canais.find(x => x.canal === canal && x.conectado)) {
          clearInterval(laco);
          dados = d; render();
          el.querySelector(".conexao").innerHTML = `<div class="sucesso"><div class="selo-ok">${icon("check")}</div>
            <h2>${m.nome} conectado</h2><p class="passo">O bot já te mandou o cartão inicial. Diga “oi” quando quiser.</p>
            <button class="btn primario bloco" id="ok">Perfeito</button></div>`;
          el.querySelector("#ok").onclick = fechar;
        }
      } catch (e) { /* tenta de novo no próximo ciclo */ }
    }, 1000);
  }

  function confirmar(titulo, texto, verbo) {
    return new Promise(res => {
      const { el, fechar } = modal(`<h2 style="font-size:1.25rem;margin:0 0 8px">${titulo}</h2><p class="muted" style="margin:0 0 22px">${texto}</p>
        <div class="linha" style="justify-content:flex-end"><button class="btn fantasma" id="nao">Cancelar</button><button class="btn perigo" id="sim">${verbo}</button></div>`, () => res(false));
      el.querySelector("#nao").onclick = () => { fechar(); };
      el.querySelector("#sim").onclick = () => { res(true); fechar(); };
    });
  }

  document.addEventListener("click", async e => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.ligar) return ligar(b.dataset.ligar);
    if (b.dataset.sairCanal) {
      const m = CANAIS[b.dataset.sairCanal];
      if (!(await confirmar(`Desconectar ${m.nome}?`, "O bot para de responder e de avisar por lá. Dá para conectar de novo quando quiser.", "Desconectar"))) return;
      await api(`/api/conta/canais/${b.dataset.sairCanal}`, { method: "DELETE" });
      toast(`${m.nome} desconectado.`); carregar();
    }
    if (b.dataset.sairSistema) {
      const s = dados.sistemas.find(x => x.chave === b.dataset.sairSistema);
      if (!(await confirmar(`Desconectar ${s.nome}?`, `O bot deixa de falar pelo ${s.nome}. Nada lá dentro é apagado.`, "Desconectar"))) return;
      await api(`/api/conta/sistemas/${s.chave}`, { method: "DELETE" });
      toast(`${s.nome} desconectado.`); carregar();
    }
    if (b.dataset.voz) {
      try {
        dados.conta = await api("/api/conta", { method: "PATCH", body: { voz: b.dataset.voz } });
        document.querySelectorAll("#voz-opcoes [data-voz]").forEach(x => x.setAttribute("aria-checked", String(x === b)));
        toast({ audio: "Vou falar quando você mandar áudio.", sempre: "Vou responder sempre falando.", nunca: "Só por escrito, então." }[b.dataset.voz]);
      } catch (err) { toast(err.message, "erro"); }
      return;
    }
    if (b.dataset.avisos) {
      const novo = b.getAttribute("aria-checked") !== "true";
      b.setAttribute("aria-checked", String(novo));
      try { await api(`/api/conta/canais/${b.dataset.avisos}`, { method: "PATCH", body: { avisos: novo } }); toast(novo ? "Avisos ligados." : "Avisos desligados."); }
      catch (err) { b.setAttribute("aria-checked", String(!novo)); toast(err.message, "erro"); }
    }
  });

  document.getElementById("form-nome").addEventListener("submit", async e => {
    e.preventDefault();
    const btn = e.target.querySelector("button"); carregando(btn, true);
    try { await api("/api/conta", { method: "PATCH", body: { nome: document.getElementById("nome").value.trim() } }); toast("Nome salvo."); await carregar(); document.querySelector("#quem .nome").textContent = dados.conta.nome; }
    catch (err) { toast(err.message, "erro"); }
    carregando(btn, false);
  });
  document.getElementById("form-senha").addEventListener("submit", async e => {
    e.preventDefault();
    const btn = e.target.querySelector("button"); carregando(btn, true);
    try { await api("/api/conta/senha", { method: "POST", body: { atual: document.getElementById("atual").value, nova: document.getElementById("nova").value } }); toast("Senha trocada."); e.target.reset(); }
    catch (err) { toast(err.message, "erro"); }
    carregando(btn, false);
  });

  await carregar();
  setInterval(() => { if (!document.hidden && !document.querySelector(".veu")) carregar().catch(() => {}); }, 30000);
})();
