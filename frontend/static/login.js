/* Solo Bot — login e cadastro, sem dependências. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const root = document.documentElement;
  const themeQuery = matchMedia("(prefers-color-scheme: light)");
  const themeButton = byId("tema");
  const themeKey = "solo-tema";
  try {
    const saved = localStorage.getItem(themeKey);
    if (saved === "dark" || saved === "light") root.dataset.theme = saved;
  } catch (_) { /* A página também funciona sem armazenamento local. */ }
  function updateThemeLabel() {
    const light = root.dataset.theme ? root.dataset.theme === "light" : themeQuery.matches;
    themeButton.setAttribute("aria-label", light ? "Ativar tema escuro" : "Ativar tema claro");
  }
  themeButton.addEventListener("click", () => {
    const light = root.dataset.theme ? root.dataset.theme === "light" : themeQuery.matches;
    root.dataset.theme = light ? "dark" : "light";
    try { localStorage.setItem(themeKey, root.dataset.theme); } catch (_) { /* Opcional. */ }
    updateThemeLabel();
  });
  themeQuery.addEventListener("change", updateThemeLabel);
  updateThemeLabel();

  const params = new URLSearchParams(location.search);
  const hosted = location.protocol === "http:" || location.protocol === "https:";
  const requestedNext = params.get("proximo") || "/painel";
  let next = "/painel";
  if (hosted && requestedNext.startsWith("/") && !requestedNext.startsWith("//")) {
    try {
      const candidate = new URL(requestedNext, location.origin);
      if (candidate.origin === location.origin) next = candidate.pathname + candidate.search + candidate.hash;
    } catch (_) { /* Destinos inválidos voltam ao painel. */ }
  }
  if (next.split("?")[0] === "/conectar") {
    byId("contexto").textContent = "Entre ou crie sua Conta Solo para concluir a conexão.";
    byId("contexto").classList.remove("oculto");
  }

  const form = byId("form");
  const password = byId("senha");
  const error = byId("erro");
  const submit = byId("enviar");
  const tabs = [...byId("abas").querySelectorAll(".aba")];
  const loginFields = [byId("login")];
  const registrationFields = [byId("nome"), byId("usuario"), byId("email")];
  let mode = "entrar";
  let submitting = false;
  const submitArrow = submit.querySelector("svg");

  function showField(id, visible) { byId(id).classList.toggle("oculto", !visible); }
  function strength() {
    const value = password.value;
    const level = value ? Math.min(4, Number(value.length >= 8) + Number(value.length >= 12)
      + Number(/[A-Z]/.test(value) && /[a-z]/.test(value))
      + Number(/\d/.test(value) && /\W/.test(value))) : 0;
    byId("forca").dataset.strength = String(level);
    byId("forca").setAttribute("aria-label", `Força da senha: ${level} de 4`);
  }
  function changeMode(newMode, updateUrl = true) {
    if (submitting) return;
    mode = newMode === "cadastro" ? "cadastro" : "entrar";
    const registering = mode === "cadastro";
    byId("abas").dataset.aba = mode;
    tabs.forEach(tab => {
      const active = tab.dataset.aba === mode;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    showField("campo-login", !registering);
    ["campo-nome", "campo-usuario", "campo-email", "forca"].forEach(id => showField(id, registering));
    loginFields.forEach(field => { field.disabled = registering; field.required = !registering; });
    registrationFields.forEach(field => { field.disabled = !registering; field.required = registering && field.id !== "email"; });
    form.setAttribute("aria-labelledby", registering ? "aba-cadastro" : "aba-entrar");
    byId("titulo").textContent = registering ? "Crie sua Conta Solo" : "Bem-vindo de volta";
    byId("sub").textContent = registering ? "Uma conta para todos os seus sistemas." : "Entre na sua Conta Solo.";
    password.autocomplete = registering ? "new-password" : "current-password";
    password.placeholder = registering ? "Mínimo de 8 caracteres" : "••••••••";
    password.minLength = registering ? 8 : 0;
    submit.replaceChildren(document.createTextNode(registering ? "Criar conta " : "Entrar "), submitArrow);
    error.textContent = "";
    strength();
    if (updateUrl) {
      try {
        const url = new URL(location.href);
        if (hosted && ["/", "/entrar", "/cadastro"].includes(url.pathname)) {
          url.pathname = registering ? "/cadastro" : "/entrar";
          url.searchParams.delete("aba");
        } else {
          url.searchParams.set("aba", mode);
        }
        history.replaceState(null, "", url.href);
      } catch (_) { /* A prévia local não depende de history.replaceState. */ }
    }
  }
  tabs.forEach(tab => tab.addEventListener("click", () => changeMode(tab.dataset.aba)));
  byId("abas").addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || submitting) return;
    event.preventDefault();
    const activeIndex = tabs.findIndex(tab => tab.dataset.aba === mode);
    const target = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (activeIndex + 1) % tabs.length;
    changeMode(tabs[target].dataset.aba);
    tabs[target].focus();
  });
  changeMode(location.pathname === "/cadastro" || params.get("aba") === "cadastro" ? "cadastro" : "entrar", false);

  byId("olho").addEventListener("click", () => {
    const reveal = password.type === "password";
    password.type = reveal ? "text" : "password";
    byId("olho").setAttribute("aria-pressed", String(reveal));
    byId("olho").setAttribute("aria-label", reveal ? "Ocultar senha" : "Mostrar senha");
  });
  password.addEventListener("input", strength);

  async function api(path, body) {
    let response;
    try {
      response = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        credentials: "same-origin",
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch (_) { throw new Error("Sem conexão com o servidor. Tente novamente."); }
    let data;
    try { data = await response.json(); } catch (_) { data = null; }
    if (!response.ok) {
      const detail = data && data.detail;
      throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? "Confira os campos informados." : `Não foi possível concluir o acesso (${response.status}).`);
    }
    if (!data || typeof data !== "object") throw new Error("O servidor não confirmou o acesso. Tente novamente.");
    return data;
  }
  function reject(message, field) {
    error.textContent = message;
    if (field) field.focus();
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (submitting) return;
    const value = id => byId(id).value.trim();
    let body;
    if (mode === "cadastro") {
      body = { nome: value("nome"), usuario: value("usuario"), email: value("email") || null, senha: password.value };
      if (body.nome.length < 2) return reject("Diga como quer ser chamado.", byId("nome"));
      if (!/^[A-Za-z0-9_.-]{3,30}$/.test(body.usuario)) return reject("Usuário: 3 a 30 letras, números, ponto, hífen ou sublinhado.", byId("usuario"));
      if (body.email && !byId("email").validity.valid) return reject("Confira o e-mail, ou deixe em branco.", byId("email"));
      if (body.senha.length < 8) return reject("A senha precisa de pelo menos 8 caracteres.", password);
    } else {
      body = { login: value("login"), senha: password.value };
      if (!body.login) return reject("Digite seu usuário ou e-mail.", byId("login"));
      if (!body.senha) return reject("Digite sua senha.", password);
    }
    if (!hosted) return reject("Abra esta página pelo Solo Bot para acessar sua conta.");
    error.textContent = "";
    submitting = true;
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    submit.textContent = mode === "cadastro" ? "Criando conta…" : "Entrando…";
    tabs.forEach(tab => { tab.disabled = true; });
    try {
      await api(mode === "cadastro" ? "/api/auth/cadastro" : "/api/auth/entrar", body);
      location.replace(next);
    } catch (err) {
      reject(err.message);
    } finally {
      submitting = false;
      submit.disabled = false;
      submit.removeAttribute("aria-busy");
      tabs.forEach(tab => { tab.disabled = false; });
      submit.replaceChildren(document.createTextNode(mode === "cadastro" ? "Criar conta " : "Entrar "), submitArrow);
    }
  });
  if (hosted) api("/api/auth/eu").then(() => { if (!submitting) location.replace(next); }).catch(() => {});

  // Cartão de acesso: luz que segue o cursor e uma leve inclinação 3D.
  const card = byId("acesso");
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  card.addEventListener("pointermove", event => {
    const box = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${event.clientX - box.left}px`);
    card.style.setProperty("--my", `${event.clientY - box.top}px`);
    if (calm || event.pointerType !== "mouse") return;
    const x = (event.clientX - box.left) / box.width - .5, y = (event.clientY - box.top) / box.height - .5;
    card.style.transform = `perspective(1000px) rotateY(${x * 6}deg) rotateX(${-y * 6}deg)`;
  });
  card.addEventListener("pointerleave", () => {
    card.style.removeProperty("--mx"); card.style.removeProperty("--my"); card.style.transform = "";
  });
})();
