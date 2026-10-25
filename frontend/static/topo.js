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

  // O painel tem duas vistas na mesma página (#inicio e #config); o admin é outra página.
  const nav = document.getElementById("nav");
  const itens = [["/painel#inicio", "inicio", "grid", "Início"], ["/painel#config", "config", "settings", "Configurações"]];
  if (conta.admin) itens.push(["/admin", "admin", "shield", "Administração"]);
  nav.innerHTML = `<span class="bolha" aria-hidden="true"></span>` + itens.map(([href, chave, ic, rotulo]) =>
    `<a href="${href}" data-nav="${chave}">${icon(ic)}<span>${rotulo}</span></a>`).join("");
  const bolha = nav.querySelector(".bolha");
  const marcar = chave => {
    nav.querySelectorAll("a").forEach(a => a.classList.toggle("ativo", a.dataset.nav === chave));
    const a = nav.querySelector(".ativo");
    if (a) { bolha.style.left = a.offsetLeft + "px"; bolha.style.width = a.offsetWidth + "px"; }
  };
  const vistas = document.querySelectorAll("[data-vista]");
  const mostrar = () => {
    if (ativo !== "painel" || !vistas.length) return marcar(ativo);
    const chave = location.hash === "#config" ? "config" : "inicio";
    const trocar = () => {
      vistas.forEach(v => { v.hidden = v.dataset.vista !== chave; });
      marcar(chave);
      scrollTo({ top: 0 });
    };
    const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.startViewTransition && !reduz && mostrar.pronto ? document.startViewTransition(trocar) : trocar();
    mostrar.pronto = true;
  };
  addEventListener("hashchange", mostrar);
  addEventListener("resize", () => marcar(nav.querySelector(".ativo")?.dataset.nav));
  mostrar();
  document.fonts?.ready.then(() => marcar(nav.querySelector(".ativo")?.dataset.nav));
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
