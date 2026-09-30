/* Topo comum do painel e do admin. Devolve a conta, ou manda para o login. */
Solo.topo = async function (ativo) {
  const { icon, LOGO, api, esc, iniciais } = Solo;
  Solo.ceu();
  document.querySelectorAll(".logo").forEach(el => el.innerHTML = LOGO);
  document.querySelectorAll("[data-i]").forEach(el => el.outerHTML = icon(el.dataset.i));
  document.querySelectorAll("[data-ic]").forEach(el => el.innerHTML = icon(el.dataset.ic));

  let conta;
  try { conta = await api("/api/auth/eu"); }
  catch (e) { location.replace("/entrar?proximo=" + encodeURIComponent(location.pathname + location.search)); throw e; }

  const nav = document.getElementById("nav");
  nav.innerHTML = `<a href="/painel" class="${ativo === "painel" ? "ativo" : ""}">Painel</a>` +
    (conta.admin ? `<a href="/admin" class="${ativo === "admin" ? "ativo" : ""}">Administração</a>` : "");
  document.getElementById("quem").innerHTML =
    `<span class="avatar">${esc(iniciais(conta.nome))}</span><span class="nome">${esc(conta.nome)}</span>`;

  const sair = document.getElementById("sair");
  sair.innerHTML = icon("logout");
  sair.onclick = async () => { await api("/api/auth/sair", { method: "POST" }); location.replace("/entrar"); };

  const tema = document.getElementById("tema");
  const pintar = () => {
    const claro = document.documentElement.dataset.theme === "light" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: light)").matches);
    tema.innerHTML = icon(claro ? "moon" : "sun");
  };
  tema.onclick = () => { Solo.alternarTema(); pintar(); };
  pintar();
  return conta;
};
