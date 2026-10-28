/* Bella — a tela. Quem ouve, fala e guarda a chave é o C# (BellaApp.cs);
   aqui só se desenha e se pedem ações pela ponte do WebView2.

   C# → tela  {tipo: "config" | "estado" | "nivel" | "msg" | "aviso" | "foto_original" | "erro_salvar" | "salvo"}
   tela → C#  {acao: "pronto" | "escuta" | "falar" | "parar_voz" | "enviar" | "salvar" | "preferencias"
                     | "foto" | "foto_original" | "abrir_painel" | "abrir" | "sair"}
   Fora do aplicativo (abrindo o arquivo no navegador) entra o modo demonstração. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const MINI = new URLSearchParams(location.search).has("mini");
  const ponteReal = !!(window.chrome && window.chrome.webview);

  let config = { temChave: false, servidor: "", chaveFinal: "", iniciar: false, mini: true, sensibilidade: 220, aparencia: "foto", foto: null, frasesAtivacao: ["Olá Bella", "Oi Bella", "E aí Bella"] };
  let estado = { modo: "pausada", escutando: false, ocupada: false, segurando: false, restante: 0 };
  let escolhendoTecla = false;
  let primeiraMensagem = true;
  let gerandoImagem = false;
  let ultimoOuvido = "", ultimaResposta = "";
  let comandoEmEdicao = null;
  let buscaAtual = null;

  // ── Ponte ──────────────────────────────────────────────────
  function enviar(acao, dados) {
    const msg = Object.assign({ acao: acao }, dados || {});
    if (ponteReal) window.chrome.webview.postMessage(msg);
    else demo.acao(msg);
  }
  function receber(m) {
    if (!m || typeof m !== "object") return;
    switch (m.tipo) {
      case "config": aplicarConfig(m); break;
      case "estado": aplicarEstado(m); break;
      case "nivel": aplicarNivel(m.v, m.limiar); break;
      case "busca": progressoBusca(m); break;
      case "msg": mensagem(m); break;
      case "aviso": aviso(m.texto, m.erro); break;
      case "toast": toast(m.texto, m.erro); break;
      case "imagens": if (!MINI) renderizarImagens(m); break;
      case "imagem_estado": if (!MINI) estadoImagem(m); break;
      case "salvo": toast(m.texto || "Salvo."); break;
      case "erro_salvar": erroSalvar(m.texto); break;
      case "comando_caminho": $("comando-caminho").value = m.caminho; break;
      case "comando_salvo": if (!m.removido) limparComando(); toast(m.removido ? "Comando removido." : "Comando salvo. Já pode falar a frase cadastrada."); break;
      case "captura": if (!MINI) abrirCaptura(m); break;
      case "foto_original": if (m.dataUrl) abrirRecorte(m.dataUrl); else toast("A foto original não está mais aqui. Escolha a foto de novo.", true); break;
    }
  }
  if (ponteReal) window.chrome.webview.addEventListener("message", e => receber(e.data));

  function abrirImagens(consultar) {
    $("galeria-imagens").hidden = false;
    $("btn-imagens").setAttribute("aria-expanded", "true");
    if (consultar) enviar("imagens_abrir");
  }
  function fecharImagens() {
    $("galeria-imagens").hidden = true;
    $("btn-imagens").setAttribute("aria-expanded", "false");
    $("btn-imagens").focus();
  }
  function estadoImagem(m) {
    gerandoImagem = !!m.gerando;
    const status = $("imagens-status");
    status.classList.toggle("gerando", gerandoImagem);
    status.classList.toggle("erro", !!m.erro);
    status.textContent = gerandoImagem ? "Gerando no Grok… você pode recolher este painel enquanto aguarda." : m.erro || "Geração encerrada. As imagens recebidas aparecem abaixo.";
    $("imagem-gerar").disabled = gerandoImagem || !!estado.ocupada;
    if (gerandoImagem) abrirImagens(false);
  }
  function renderizarImagens(m) {
    const lista = $("imagens-lista"); lista.replaceChildren();
    const itens = (m.imagens || []).slice(0, 6);
    if (!itens.length) { const vazio = document.createElement("p"); vazio.className = "ajuda"; vazio.textContent = "Sua galeria ainda está vazia."; lista.appendChild(vazio); }
    itens.forEach((item, i) => {
      if (!/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(item.Previa || "")) return;
      const card = document.createElement("figure"); card.className = "imagem-card";
      const img = document.createElement("img"); img.src = item.Previa; img.alt = "Imagem gerada " + (i + 1); img.loading = "lazy"; img.decoding = "async";
      const legenda = document.createElement("figcaption");
      const data = document.createElement("span"); data.textContent = item.Criada;
      const salvar = document.createElement("button"); salvar.type = "button"; salvar.className = "btn"; salvar.textContent = "Salvar original"; salvar.onclick = () => enviar("imagem_salvar", { id: item.Id });
      legenda.append(data, salvar); card.append(img, legenda); lista.appendChild(card);
    });
    if (m.abrir) { abrirImagens(false); $("imagens-status").textContent = "Imagem pronta. Salve o original para guardar fora da galeria."; }
  }

  // ── Escalas do microfone (energia RMS 50…4000, logarítmica) ──
  const MIN = 50, MAX = 4000, L = Math.log(MAX / MIN);
  const paraPct = e => Math.max(0, Math.min(100, 100 * Math.log(Math.max(e, MIN) / MIN) / L));
  const deSlider = p => Math.round(MIN * Math.exp(L * p / 100));

  // ── Config ─────────────────────────────────────────────────
  function aplicarAvatar() {
    const comFoto = !!config.foto && config.aparencia === "foto";
    document.body.classList.toggle("sem-foto", !comFoto);
    document.querySelectorAll("[data-avatar]").forEach(el => {
      el.style.backgroundImage = comFoto ? 'url("' + config.foto + '")' : "";
      el.classList.toggle("orbe", !comFoto);
    });
    // a prévia nas configurações mostra a foto mesmo em "Só orbe"
    document.querySelectorAll(".soltar [data-avatar]").forEach(el => {
      el.style.backgroundImage = config.foto ? 'url("' + config.foto + '")' : "";
      el.classList.toggle("orbe", !config.foto);
    });
  }
  function aplicarConfig(c) {
    config = Object.assign(config, c);
    aplicarAvatar();
    const vazio = document.querySelector(".vazio");
    if (vazio) vazio.textContent = config.apertarParaFalar ? "Segure a tecla configurada para falar, ou escreva aqui embaixo." : "Diga “" + config.frasesAtivacao[0] + "”" + (config.ativacaoRapida ? ", faça uma pausa e depois o pedido." : " e aguarde a saudação.") + " Também dá para escrever aqui embaixo.";
    if (MINI) { aplicarEstado({}); return; }
    $("btn-recortar").disabled = !config.foto;
    $("btn-remover").disabled = !config.foto;
    document.querySelectorAll("[data-aparencia]").forEach(b => b.setAttribute("aria-checked", String(b.dataset.aparencia === config.aparencia)));
    $("cfg-iniciar").checked = !!config.iniciar;
    $("cfg-mini").checked = !!config.mini;
    $("cfg-apertar").checked = !!config.apertarParaFalar;
    $("cfg-rapida").checked = !!config.ativacaoRapida;
    $("cfg-safada").checked = !!config.modoSafada;
    $("modo-conversa").hidden = !config.modoSafada;
    $("cfg-safada").disabled = !!estado.ocupada;
    for (let i = 0; i < 3; i++) $("cfg-frase-" + (i + 1)).value = (config.frasesAtivacao || [])[i] || "";
    $("btn-chamadas").disabled = false;
    $("cfg-atalho-fala").hidden = !config.apertarParaFalar;
    $("cfg-espera-fala").value = config.esperaFalar || 5;
    if (!escolhendoTecla) $("cfg-tecla-fala").textContent = (config.nomeTeclaFalar || "F8") + " · trocar tecla";
    $("entrada").placeholder = config.apertarParaFalar ? "Escreva uma mensagem…" : "Escreva ou diga “" + config.frasesAtivacao[0] + "”…";
    document.querySelector(".compositor .tecla").textContent = config.apertarParaFalar ? (config.nomeTeclaFalar || "F8") : "Ctrl Alt B";
    $("cfg-iniciar").closest("label").querySelector("small").textContent = config.apertarParaFalar ? "Abre escondida, aguardando a tecla." : "Abre escondida, já ouvindo.";
    $("atalho-voz-dica").textContent = config.apertarParaFalar ? "desativada neste modo" : "chama por voz";
    $("atalho-voz-frase").textContent = "“" + config.frasesAtivacao[0] + "”";
    $("atalho-fala-tecla").textContent = config.apertarParaFalar ? (config.nomeTeclaFalar || "F8") : "Ctrl + Alt + B";
    $("atalho-fala-dica").textContent = config.apertarParaFalar ? "segure por " + (config.esperaFalar || 5) + " s; solte para enviar" : "fala sem dizer o nome";
    document.querySelector(".rodape").lastChild.textContent = config.apertarParaFalar ? "Microfone fechado até ativar pela tecla" : "A escuta de espera fica no seu computador";
    aplicarEstado({});
    const p = paraPct(config.sensibilidade || 220);
    $("cfg-sens").value = p; $("cfg-sens").style.setProperty("--p", p + "%");
    $("medidor-marca").style.left = p + "%";
    $("cfg-servidor").value = config.servidor || "";
    $("cfg-chave").value = "";
    $("cfg-chave").placeholder = config.temChave ? "Chave salva · termina em " + (config.chaveFinal || "…") : "bella_…";
    const pastas = $("cfg-pastas"); pastas.textContent = "";
    (config.pastasArquivos || []).forEach((p, i) => {
      const linha = document.createElement("div"); linha.className = "pasta-arquivos";
      const nome = document.createElement("span"); nome.textContent = p; nome.title = p;
      const remover = document.createElement("button"); remover.className = "btn"; remover.type = "button";
      remover.textContent = "Remover acesso"; remover.onclick = () => enviar("pasta_arquivos", { remover: i });
      linha.appendChild(nome); linha.appendChild(remover); pastas.appendChild(linha);
    });
    if (!(config.pastasArquivos || []).length) pastas.textContent = "Nenhuma pasta escolhida.";
    desenharComandos();
    const naBoasVindas = !config.temChave;
    $("boas-vindas").hidden = !naBoasVindas;
    $("app").hidden = naBoasVindas;
    if (naBoasVindas) setTimeout(() => $("bv-chave").focus(), 50);
  }

  function limparComando() {
    comandoEmEdicao = null; $("form-comando").reset();
    $("btn-comando-salvar").textContent = "Salvar comando"; $("btn-comando-cancelar").hidden = true;
    tipoComando();
  }
  function tipoComando() {
    const tipo = $("comando-tipo").value, pasta = tipo === "pasta", site = tipo === "site", programa = tipo === "programa", word = tipo === "word", pesquisa = ["google", "youtube", "maps"].includes(tipo);
    const variavel = $("comando-variavel").checked;
    $("campo-comando-caminho").hidden = pesquisa || word; $("comando-caminho").required = pasta || site || programa;
    $("campo-comando-programa").hidden = !programa;
    $("campo-comando-pasta").hidden = !pasta; $("campo-comando-pesquisa").hidden = !pesquisa;
    $("campo-comando-termo").hidden = !pesquisa || variavel; $("comando-termo").required = pesquisa && !variavel;
    $("rotulo-comando-caminho").textContent = pasta ? "Caminho da pasta" : programa ? "Programa instalado (.exe)" : "Endereço do site";
    $("comando-caminho").placeholder = pasta ? "C:\\JEFFERSON\\PROJETOS" : "https://mail.google.com";
    $("ajuda-comando").textContent = pasta ? "O comando abre somente a pasta cadastrada. Para buscar ou alterar arquivos nela, adicione também o acesso nas Configurações." : site ? "O site abre no seu navegador padrão." : variavel ? "Use {assunto} na frase, como Pesquisar sobre {assunto}. Na hora, diga Pesquisar sobre escrita criativa. Os resultados abrem no navegador padrão." : "Este comando sempre pesquisa o assunto fixo que você definir. Os resultados abrem no navegador padrão.";
    if (word) $("ajuda-comando").textContent = "Usa o Microsoft Word instalado. Exemplos: Abrir Word, Escreva {pedido}, Faça {pedido} ou No Word {pedido}. Interpreta abrir, ditar ou criar texto; reutiliza o documento aberto sem apagar a seleção. Não salva nem fecha o documento.";
    if (programa) { $("comando-caminho").placeholder = "Selecione o arquivo .exe do programa"; $("ajuda-comando").textContent = "Abre o programa cadastrado ou traz a janela existente para a frente. Escolha o executável instalado, sem argumentos. A escrita automática está disponível no tipo Microsoft Word."; }
  }
  function preencherComando(c, editar) {
    comandoEmEdicao = editar ? c.Id : null;
    $("comando-tipo").value = c.Tipo || "pasta"; $("comando-frase").value = c.Frase;
    $("comando-caminho").value = c.Caminho || ""; $("comando-termo").value = c.Termo || "";
    $("comando-variavel").checked = (c.Frase || "").includes("{assunto}");
    $("btn-comando-salvar").textContent = editar ? "Salvar alterações" : "Salvar comando";
    $("btn-comando-cancelar").hidden = !editar; tipoComando(); $("comando-frase").focus();
  }
  function desenharComandos() {
    const lista = $("lista-comandos"); lista.textContent = "";
    const comandos = config.comandosPastas || [];
    if (comandoEmEdicao && !comandos.some(c => c.Id === comandoEmEdicao)) limparComando();
    if (!comandos.length) { const p = document.createElement("p"); p.className = "ajuda"; p.textContent = "Nenhum comando salvo. Escolha um modelo ou cadastre sua primeira automação."; lista.appendChild(p); }
    const modelos = $("modelos-comandos"); modelos.textContent = "";
    (config.modelosComandos || []).forEach(c => { const b = document.createElement("button"); b.type = "button"; b.className = "btn"; b.textContent = c.Titulo; b.onclick = () => preencherComando(c, false); modelos.appendChild(b); });
    comandos.forEach(c => {
      const card = document.createElement("div"); card.className = "comando-salvo";
      const frase = document.createElement("b"); frase.textContent = c.Frase;
      const nomes = { pasta: "Pasta", site: "Site", google: "Google", youtube: "YouTube", maps: "Maps", word: "Microsoft Word", programa: "Programa" };
      const caminho = document.createElement("p"); caminho.textContent = (nomes[c.Tipo || "pasta"] || "Ação") + " · " + (c.Caminho || c.Termo || (c.Tipo === "word" ? "Usa o documento aberto" : "Assunto informado por voz ou texto"));
      const acoes = document.createElement("div"); acoes.className = "botoes";
      const botao = (rotulo, acao) => { const b = document.createElement("button"); b.type = "button"; b.className = "btn"; b.textContent = rotulo; b.onclick = acao; acoes.appendChild(b); };
      botao("Testar", () => { if (estado.ocupada) return toast("Espere o pedido atual terminar.", true); $("btn-fechar-config").click(); enviar("enviar", { texto: "/arquivos comando " + c.Id, exibir: c.Frase.replace("{assunto}", "…") }); });
      botao("Editar", () => preencherComando(c, true));
      botao("Remover", () => enviar("comando_pasta", { id: c.Id, remover: true }));
      card.appendChild(frase); card.appendChild(caminho); card.appendChild(acoes); lista.appendChild(card);
    });
  }

  // ── Estado (o que a Bella está fazendo) ────────────────────
  const TEXTOS = {
    pausada: ["Escuta pausada", "Ctrl + Alt + B para falar"],
    espera: ["Esperando sua chamada", "a escuta fica no seu computador"],
    saudando: ["Respondendo à chamada…", ""],
    ouvindo: ["Pode falar", "eu paro quando você fizer uma pausa"],
    pensando: ["Pensando…", ""],
    falando: ["Respondendo", ""]
  };
  function textosEstado() {
    if (buscaAtual) return ["Procurando pasta…", buscaAtual.consultadas.toLocaleString("pt-BR") + " pastas consultadas"];
    if (!config.apertarParaFalar && estado.modo === "espera") return ["Esperando sua chamada", "diga “" + config.frasesAtivacao[0] + "”" + (config.ativacaoRapida ? ", pause e faça o pedido" : " e aguarde")];
    if (config.apertarParaFalar && !estado.escutando) return ["Apertar para falar pausado", "ative a escuta no botão acima"];
    if (config.apertarParaFalar && estado.escutando) {
      const tecla = config.nomeTeclaFalar || "F8";
      if (estado.segurando) return ["Segure " + tecla, estado.restante + " s para abrir o microfone"];
      if (estado.modo === "espera") return ["Apertar para falar", "segure " + tecla + " por " + (config.esperaFalar || 5) + " s"];
      if (estado.modo === "ouvindo") return ["Pode falar", "solte " + tecla + " para enviar"];
    }
    return TEXTOS[estado.modo] || TEXTOS.pausada;
  }
  function aplicarEstado(s) {
    estado = Object.assign(estado, s);
    if (!MINI) {
      const tempos = Object.entries(estado.tempos || {}).map(([nome, ms]) => nome + ": " + (ms / 1000).toFixed(1) + " s");
      if (estado.tempoChamada > 0) tempos.unshift("Chamada: " + (estado.tempoChamada / 1000).toFixed(1) + " s");
      if (tempos.length) $("cfg-tempos").textContent = "Tempo das etapas · " + tempos.join(" · ");
    }
    const modo = estado.modo;
    if (MINI) { $("mini").dataset.modo = modo; atualizarMini(); return; }
    $("presenca").dataset.modo = modo;
    const t = textosEstado();
    const el = $("estado"); el.textContent = "";
    const b = document.createElement("b"); b.textContent = t[0]; el.appendChild(b);
    if (t[1]) el.appendChild(document.createTextNode(" · " + t[1]));
    const onda = $("onda");
    onda.classList.toggle("ativa", modo === "falando" || modo === "saudando" || modo === "ouvindo");
    onda.classList.toggle("falando", modo === "falando" || modo === "saudando");
    if (modo !== "ouvindo") document.documentElement.style.setProperty("--nivel", 0);
    const chip = $("chip-escuta");
    chip.classList.toggle("ativa", !!estado.escutando);
    $("chip-texto").textContent = estado.escutando ? (config.apertarParaFalar ? "Apertar para falar" : "Esperando chamada") : "Escuta pausada";
    chip.title = estado.escutando ? "Pausar a escuta e liberar o microfone" : "Ligar a escuta";
    $("btn-parar").hidden = !(estado.esperandoVoz || modo === "falando" || modo === "saudando");
    $("btn-parar").title = estado.esperandoVoz ? "Cancelar espera pela voz" : "Interromper voz";
    $("btn-falar").disabled = !!estado.ocupada && modo !== "ouvindo";
    $("btn-falar").classList.toggle("gravando", modo === "ouvindo");
    $("btn-falar").title = config.apertarParaFalar ? "Segure " + (config.nomeTeclaFalar || "F8") + " por " + (config.esperaFalar || 5) + " s" : "Falar agora (Ctrl + Alt + B)";
    $("btn-enviar").disabled = !!estado.ocupada;
    $("imagem-gerar").disabled = !!estado.ocupada || gerandoImagem;
    $("cfg-safada").disabled = !!estado.ocupada;
    digitando(modo === "pensando" && !buscaAtual);
  }

  function progressoBusca(m) {
    buscaAtual = m.ativa ? { consultadas: Math.max(0, Number(m.consultadas) || 0) } : null;
    if (MINI) { atualizarMini(); return; }
    let el = $("progresso-busca");
    if (!buscaAtual) { if (el) el.remove(); aplicarEstado({}); return; }
    if (!el) {
      el = document.createElement("div"); el.id = "progresso-busca"; el.className = "busca-progresso";
      el.setAttribute("role", "status");
      const texto = document.createElement("span"); texto.className = "busca-detalhe";
      const cancelar = document.createElement("button"); cancelar.type = "button"; cancelar.className = "btn";
      cancelar.textContent = "Cancelar busca"; cancelar.onclick = () => {
        cancelar.disabled = true; cancelar.textContent = "Cancelando…"; enviar("cancelar_busca");
      };
      el.append(texto, cancelar); prepararConversa().appendChild(el); rolar();
    }
    el.querySelector(".busca-detalhe").textContent = "Procurando pasta… " + buscaAtual.consultadas.toLocaleString("pt-BR") + " pastas consultadas. O resultado aparecerá aqui automaticamente.";
    aplicarEstado({});
  }

  let ultimaOnda = 0;
  function aplicarNivel(v, limiar) {
    const lim = limiar || config.sensibilidade || 220;
    if (!MINI && $("gaveta").classList.contains("aberta")) $("medidor-nivel").style.width = paraPct(v) + "%";
    if (estado.modo !== "ouvindo") return;
    // 0 = bem abaixo do limiar, 1 = voz forte
    const n = Math.max(0, Math.min(1, (Math.log(Math.max(v, 1)) - Math.log(lim * .5)) / (Math.log(lim * 6) - Math.log(lim * .5))));
    document.documentElement.style.setProperty("--nivel", n.toFixed(3));
    if (MINI) return;
    const agora = performance.now();
    if (agora - ultimaOnda > 70) {
      ultimaOnda = agora;
      document.querySelectorAll("#onda span").forEach((s, i) => {
        const k = .25 + n * (.55 + .45 * Math.abs(Math.sin(agora / 140 + i * 1.3)));
        s.style.transform = "scaleY(" + Math.min(1, k).toFixed(2) + ")";
      });
    }
  }

  // ── Conversa ───────────────────────────────────────────────
  const RE_SELO = /^(\p{Extended_Pictographic}[️‍\p{Extended_Pictographic}]*)\s+([A-ZÀ-Ú][\wÀ-ú]{2,20})$/u;
  const RE_ITEM = /^\*?\d+\.\*?\s/;
  const CLASSE = { Finances: "fin", Rotinas: "rot" };

  function hora() { return new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); }
  function rolar() { const c = $("conversa"); requestAnimationFrame(() => { c.scrollTop = c.scrollHeight; }); }
  function prepararConversa() {
    const c = $("conversa");
    const vazio = c.querySelector(".vazio"); if (vazio) vazio.remove();
    if (primeiraMensagem) {
      primeiraMensagem = false;
      const d = document.createElement("div"); d.className = "dia"; d.textContent = "Hoje · " + hora(); c.appendChild(d);
    }
    return c;
  }
  function digitando(sim) {
    if (MINI) return;
    const c = $("conversa"); let el = c.querySelector(".digitando");
    if (sim && !el) {
      prepararConversa();
      el = document.createElement("div"); el.className = "digitando";
      el.innerHTML = '<div class="rosto av" data-avatar="pequeno"></div><div class="pontos"><i></i><i></i><i></i></div>';
      el.querySelector(".av").style.cssText = "width:28px;height:28px;border-radius:50%;border:1.5px solid rgba(167,139,250,.55)";
      c.appendChild(el); aplicarAvatar(); rolar();
    } else if (!sim && el) el.remove();
  }

  function mensagem(m) {
    if (m.de === "eu") ultimoOuvido = m.texto || ""; else if (m.de === "bella") ultimaResposta = resumoDe(m.texto || "");
    if (MINI) { atualizarMini(); return; }
    digitando(false);
    const c = prepararConversa();
    if (m.de === "eu") {
      const b = document.createElement("div"); b.className = "eu"; b.textContent = m.texto || "";
      if (m.via === "voz") { const s = document.createElement("small"); s.textContent = "🎤 por voz"; b.appendChild(s); }
      c.appendChild(b);
    } else {
      const linha = document.createElement("div"); linha.className = "fala-ela";
      const av = document.createElement("div"); av.className = "rosto av"; av.setAttribute("data-avatar", "pequeno");
      const bolha = document.createElement("div"); bolha.className = "ela";
      if (ehPrompt(m.texto)) montarPrompt(bolha, m.texto); else montarResposta(bolha, m.texto || "", m.opcoes || []);
      linha.appendChild(av); linha.appendChild(bolha); c.appendChild(linha);
      aplicarAvatar();
    }
    rolar();
  }

  // ── Prompt de imagem: caixa com rolagem e um clique para copiar ──
  const RE_PROMPT = /^\s*(?:Use a imagem da nova modelo como refer[êe]ncia|Crie uma modelo original com as seguintes|Vista a pessoa da imagem de refer[êe]ncia|Recrie a pessoa da imagem de refer[êe]ncia)/i;
  const MARCA_PROMPT = "[[prompt]]";
  function ehPrompt(texto) {
    // o servidor marca todo prompt (de qualquer categoria, inclusive as futuras) com [[prompt]] no começo
    if (typeof texto === "string" && texto.trimStart().startsWith(MARCA_PROMPT)) return true;
    // pelo começo fixo do modelo, ou pelo conteúdo (o Grok às vezes muda a primeira linha)
    return typeof texto === "string" && texto.length > 600 &&
      (RE_PROMPT.test(texto) || (/9:16/.test(texto) && /n[ãa]o cruzar as pernas/i.test(texto)));
  }
  function copiarTexto(caixa, texto) {
    const manual = () => { caixa.focus(); caixa.select(); try { return document.execCommand("copy"); } catch (e) { return false; } };
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(texto).then(() => true, () => manual());
    return Promise.resolve(manual());
  }
  function montarPrompt(bolha, texto) {
    texto = String(texto).replace(/^\s*\[\[prompt\]\]\s*/, "");
    bolha.classList.add("prompt");
    const topo = document.createElement("div"); topo.className = "prompt-topo";
    const titulo = document.createElement("span"); titulo.className = "prompt-titulo"; titulo.textContent = "🖼️ Prompt pronto";
    const botao = document.createElement("button"); botao.type = "button"; botao.className = "prompt-copiar"; botao.textContent = "Copiar prompt";
    topo.appendChild(titulo); topo.appendChild(botao);
    const caixa = document.createElement("textarea"); caixa.className = "prompt-caixa"; caixa.readOnly = true;
    caixa.spellcheck = false; caixa.value = texto.trim(); caixa.setAttribute("aria-label", "Prompt para copiar");
    caixa.onfocus = () => caixa.select();
    const dica = document.createElement("small"); dica.className = "prompt-dica"; dica.textContent = "Cole no Grok Imagine junto da imagem de referência.";
    botao.onclick = () => copiarTexto(caixa, caixa.value).then(ok => {
      botao.textContent = ok ? "Copiado ✓" : "Selecione e use Ctrl+C";
      botao.classList.toggle("ok", !!ok);
      setTimeout(() => { botao.textContent = "Copiar prompt"; botao.classList.remove("ok"); }, 2200);
    });
    bolha.appendChild(topo); bolha.appendChild(caixa); bolha.appendChild(dica);
  }

  function montarResposta(bolha, texto, opcoes) {
    let corpo = [];
    const fecharCorpo = () => {
      const t = corpo.join("\n").replace(/\n{3,}/g, "\n\n").trim();
      if (t) { const p = document.createElement("div"); p.className = "corpo"; p.textContent = t; bolha.appendChild(p); }
      corpo = [];
    };
    texto.split(/\r?\n/).forEach(l => {
      const s = l.trim();
      const selo = s.match(RE_SELO);
      if (selo && !s.includes(":")) {
        fecharCorpo();
        const chip = document.createElement("span"); chip.className = "selo " + (CLASSE[selo[2]] || "");
        chip.textContent = selo[1] + " " + selo[2]; bolha.appendChild(chip); bolha.appendChild(document.createElement("br"));
        return;
      }
      if (s.startsWith("🧭")) {
        fecharCorpo();
        const n = document.createElement("span"); n.className = "nota"; n.textContent = s; bolha.appendChild(n);
        return;
      }
      if (opcoes.length && RE_ITEM.test(s)) return;      // a lista vira botões
      corpo.push(l);
    });
    fecharCorpo();
    // tira o <br> sobrando no fim
    if (bolha.lastChild && bolha.lastChild.nodeName === "BR") bolha.removeChild(bolha.lastChild);
    if (opcoes.length) {
      const ops = document.createElement("div"); ops.className = "ops";
      opcoes.forEach(o => {
        const b = document.createElement("button"); b.type = "button";
        const n = document.createElement("b"); n.textContent = o.numero;
        b.appendChild(n); b.appendChild(document.createTextNode([o.rotulo, o.titulo].filter(Boolean).join(" ")));
        b.title = "Escolher " + o.numero;
        b.onclick = () => {
          if (estado.ocupada) return toast("Espere eu terminar o pedido anterior.");
          ops.querySelectorAll("button").forEach(x => x.disabled = true);
          enviar("enviar", { texto: o.comando || String(o.numero), exibir: [o.rotulo, o.titulo].filter(Boolean).join(" ") });
        };
        ops.appendChild(b);
      });
      bolha.appendChild(ops);
    }
  }
  function resumoDe(texto) {
    return texto.split(/\r?\n/).map(s => s.trim())
      .filter(s => s && !RE_SELO.test(s) && !s.startsWith("🧭") && !RE_ITEM.test(s)).join(" ").slice(0, 220);
  }

  function aviso(texto, erro) {
    if (MINI) return;
    digitando(false);
    const c = prepararConversa();
    const d = document.createElement("div"); d.className = "sistema-linha" + (erro ? " erro" : ""); d.textContent = texto;
    c.appendChild(d); rolar();
  }
  function toast(texto, erro) {
    if (MINI) return;
    const t = document.createElement("div"); t.className = "toast" + (erro ? " erro" : ""); t.textContent = texto;
    $("toasts").appendChild(t);
    setTimeout(() => { t.classList.add("sai"); setTimeout(() => t.remove(), 350); }, 3200);
  }

  // ── Mini-Bella ─────────────────────────────────────────────
  function atualizarMini() {
    if (buscaAtual) {
      $("mini-resposta").textContent = "Procurando pasta… " + buscaAtual.consultadas.toLocaleString("pt-BR") + " pastas consultadas";
      return;
    }
    const t = textosEstado();
    const resposta = !estado.segurando && (estado.modo === "falando" || (estado.modo === "espera" && !config.apertarParaFalar) || estado.modo === "pausada") && ultimaResposta ? ultimaResposta : t[0] + (t[1] ? " · " + t[1] : "");
    $("mini-ouvido").textContent = ultimoOuvido ? "“" + ultimoOuvido + "”" : "Bella";
    $("mini-resposta").textContent = resposta;
  }

  // ── Ações da janela ────────────────────────────────────────
  function ligarJanela() {
    $("chip-escuta").onclick = () => enviar("escuta");
    $("btn-falar").onclick = () => enviar("falar");
    $("btn-parar").onclick = () => enviar("parar_voz");
    $("compositor").onsubmit = e => {
      e.preventDefault();
      let t = $("entrada").value.trim(); if (!t && !anexo) return;
      if (estado.ocupada) return toast("Espere eu terminar o pedido anterior.");
      if (anexo) {
        // com referência anexa, o texto é o pedido do prompt (vazio = prompt aleatório com as roupas da imagem)
        const img = anexo; if (!t) t = "crie um prompt com essa referência";
        $("entrada").value = ""; tirarAnexo();
        return enviar("enviar", { texto: t, exibir: "🖼️ " + t, imagem: img });
      }
      $("entrada").value = ""; enviar("enviar", { texto: t });
    };
    // Ferramentas laterais: recolhível; a primeira é o "Criativo" (prompt fora da biblioteca)
    const lateral = (abrir) => {
      $("lateral").classList.toggle("aberta", abrir); $("lateral").setAttribute("aria-hidden", String(!abrir));
      $("lateral-aba").setAttribute("aria-expanded", String(abrir)); document.body.classList.toggle("lateral-aberta", abrir);
      try { localStorage.setItem("bella.lateral", abrir ? "1" : "0"); } catch (e) { }
    };
    $("lateral-aba").onclick = () => { lateral(true); $("criativo-tema").focus(); };
    $("lateral-fechar").onclick = () => lateral(false);
    document.addEventListener("keydown", e => { if (e.key === "Escape" && $("lateral").classList.contains("aberta")) lateral(false); });
    const criarCriativo = () => {
      if (estado.ocupada) return toast("Espere eu terminar o pedido anterior.");
      const tema = $("criativo-tema").value.trim(); $("criativo-tema").value = "";
      lateral(false);
      enviar("enviar", { texto: "/promptcriativo" + (tema ? " " + tema : ""), exibir: "✨ Prompt criativo" + (tema ? ": " + tema : "") });
    };
    $("criativo-ir").onclick = criarCriativo;
    // ponte para o painel de ferramentas (ferramentas.js): enviar ao chat reaproveita o envio normal do campo de texto
    window.bellaApi = {
      ocupada: () => estado.ocupada,
      aviso: t => toast(t, true),
      temAnexo: () => !!anexo,
      anexar: url => { anexo = url; mostrarAnexo(url); toast("Quadro anexado como referência."); },
      fechar: () => lateral(false),
      enviar: t => { $("entrada").value = t; $("compositor").dispatchEvent(new Event("submit", { cancelable: true })); },
      inserir: t => { $("entrada").value = t; $("entrada").focus(); }
    };
    $("criativo-tema").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); criarCriativo(); } });
    try { if (localStorage.getItem("bella.lateral") === "1") lateral(true); } catch (e) { }
    // Referência de roupa para o prompt: botão, Ctrl+V ou arrastar a imagem para a janela
    // Recorte de tela: quem recorta é o Windows (CapturaTela.cs); a prévia volta como "captura"
    $("btn-recortar-tela").onclick = () => enviar("recortar_tela");
    $("ref-recortar").onclick = () => enviar("recortar_tela");
    $("captura-fechar").onclick = () => fecharCaptura();
    $("captura-prompt").onclick = () => {
      if (!captura) return;
      if (estado.ocupada) return toast("Espere eu terminar o pedido anterior.", true);
      const t = $("captura-pedido").value.trim() || "crie um prompt com essa referência";
      const img = captura; fecharCaptura();
      enviar("enviar", { texto: t, exibir: "✂️ " + t, imagem: img });
    };
    $("captura-pedido").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); $("captura-prompt").click(); } });
    $("captura-anexar").onclick = () => {
      if (!captura) return;
      anexo = captura; mostrarAnexo(captura); fecharCaptura();
      toast("Recorte anexado. Escreva o pedido ou só envie para criar o prompt."); $("entrada").focus();
    };
    $("captura-copiar").onclick = () => enviar("captura_copiar");
    $("captura-salvar").onclick = () => enviar("captura_salvar");
    $("captura-novo").onclick = () => { fecharCaptura(); enviar("recortar_tela"); };
    $("btn-anexo").onclick = () => $("anexo-arquivo").click();
    $("btn-video").onclick = () => { lateral(true); setTimeout(() => { const s = $("ferr-frames"); if (s) s.scrollIntoView({ block: "start", behavior: "smooth" }); }, 80); };
    $("anexo-arquivo").onchange = e => { const f = e.target.files[0]; e.target.value = ""; if (f) anexar(f); };
    $("anexo-x").onclick = () => { tirarAnexo(); $("entrada").focus(); };
    // Ctrl + V com imagem funciona em qualquer lugar da tela (campo de texto, painel de ferramentas…)
    document.addEventListener("paste", e => {
      const itens = (e.clipboardData && e.clipboardData.items) || [];
      for (const it of itens) if (it.kind === "file" && /^image\//.test(it.type)) { e.preventDefault(); const f = it.getAsFile(); if (f) anexar(f); return; }
    });
    // painel de ferramentas: anexar, colar, tirar e soltar a imagem
    $("ref-anexar").onclick = () => $("ref-arquivo").click();
    $("ref-arquivo").onchange = e => { const f = e.target.files[0]; e.target.value = ""; if (f) anexar(f); };
    $("ref-tirar").onclick = () => tirarAnexo();
    $("ref-colar").onclick = async () => {
      try {
        const itens = await navigator.clipboard.read();
        for (const it of itens) { const tipo = it.types.find(t => /^image\/(png|jpeg|webp)$/.test(t)); if (tipo) { const blob = await it.getType(tipo); return anexar(new File([blob], "colada", { type: tipo })); } }
        toast("Não há imagem copiada na área de transferência.", true);
      } catch (e) { toast("Não consegui ler a área de transferência. Use Ctrl + V.", true); }
    };
    ["dragover", "dragleave", "drop"].forEach(n => $("ref-area").addEventListener(n, e => { e.preventDefault(); $("ref-area").classList.toggle("sobre", n === "dragover"); }));
    document.addEventListener("drop", e => {
      if (e.target.closest && e.target.closest("#soltar")) return;
      if (!$("gaveta") || $("gaveta").classList.contains("aberta")) return;
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f && /^image\//.test(f.type)) anexar(f);
    });
    // Configurações
    const aba = nome => {
      $("cfg-geral").hidden = nome !== "geral"; $("cfg-comandos").hidden = nome !== "comandos";
      $("gaveta-titulo").textContent = nome === "comandos" ? "Comandos" : "Configurações";
      document.querySelectorAll("[data-aba]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.aba === nome)));
      enviar("medidor", { ligado: nome === "geral" });
    };
    const abrir = (nome = "geral") => { aba(nome); $("veu").hidden = false; $("gaveta").classList.add("aberta"); $("gaveta").setAttribute("aria-hidden", "false"); };
    const fechar = () => { $("gaveta").classList.remove("aberta"); $("gaveta").setAttribute("aria-hidden", "true"); setTimeout(() => $("veu").hidden = true, 250); enviar("medidor", { ligado: false }); };
    $("btn-imagens").onclick = () => abrirImagens(true);
    $("imagens-fechar").onclick = fecharImagens;
    $("imagens-form").onsubmit = e => {
      e.preventDefault();
      const prompt = $("imagem-prompt").value.trim();
      if (!prompt || estado.ocupada || gerandoImagem) return;
      if (ponteReal) enviar("imagem_gerar", { prompt }); else toast("A geração de imagens funciona no aplicativo conectado ao Solo Bot.");
    };
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("galeria-imagens").hidden) fecharImagens(); });
    $("btn-config").onclick = () => abrir();
    $("btn-comandos").onclick = () => abrir("comandos");
    document.querySelectorAll("[data-aba]").forEach(b => b.onclick = () => { cancelarTecla(); aba(b.dataset.aba); });
    $("btn-fechar-config").onclick = fechar; $("veu").onclick = fechar;
    $("btn-trocar-foto").onclick = () => { abrir(); setTimeout(() => $("arquivo").click(), 320); };
    document.addEventListener("keydown", e => {
      if (e.key !== "Escape") return;
      if (!$("modal-captura").hidden) fecharCaptura();
      else if (!$("modal-recorte").hidden) fecharRecorte(); else if ($("gaveta").classList.contains("aberta")) fechar();
    });
    document.querySelectorAll("[data-aparencia]").forEach(b => b.onclick = () => {
      aplicarConfig({ aparencia: b.dataset.aparencia }); enviar("preferencias", { aparencia: b.dataset.aparencia });
    });
    $("cfg-safada").onchange = e => enviar("preferencias", { modoSafada: e.target.checked });
    $("cfg-iniciar").onchange = e => enviar("preferencias", { iniciar: e.target.checked });
    $("cfg-mini").onchange = e => enviar("preferencias", { mini: e.target.checked });
    $("cfg-chamadas").onsubmit = e => {
      e.preventDefault();
      const frases = [1, 2, 3].map(i => $("cfg-frase-" + i).value.trim()).filter(Boolean);
      if (!frases.length) return toast("Informe pelo menos uma frase de ativação.", true);
      $("btn-chamadas").disabled = true;
      enviar("chamadas", { frases });
    };
    $("cfg-rapida").onchange = e => enviar("preferencias", { ativacaoRapida: e.target.checked });
    $("cfg-apertar").onchange = e => enviar("preferencias", { apertarParaFalar: e.target.checked });
    $("cfg-espera-fala").onchange = e => {
      const segundos = Number(e.target.value);
      if (!Number.isInteger(segundos) || segundos < 1 || segundos > 30) {
        e.target.value = config.esperaFalar || 5; return toast("Escolha de 1 a 30 segundos.", true);
      }
      enviar("preferencias", { esperaFalar: segundos });
    };
    const cancelarTecla = () => {
      escolhendoTecla = false; $("cfg-tecla-fala").textContent = (config.nomeTeclaFalar || "F8") + " · trocar tecla";
    };
    $("cfg-tecla-fala").onclick = () => {
      escolhendoTecla = !escolhendoTecla;
      $("cfg-tecla-fala").textContent = escolhendoTecla ? "Pressione a nova tecla (Esc cancela)" : (config.nomeTeclaFalar || "F8") + " · trocar tecla";
    };
    document.addEventListener("keydown", e => {
      if (!escolhendoTecla) return;
      e.preventDefault(); e.stopImmediatePropagation();
      if (e.key === "Escape") return cancelarTecla();
      if (e.repeat || [16, 17, 18, 91, 92].includes(e.keyCode)) return;
      const tecla = e.keyCode;
      const valida = (tecla >= 48 && tecla <= 57) || (tecla >= 65 && tecla <= 90) || (tecla >= 96 && tecla <= 135)
        || [8, 13, 19, 20, 32, 33, 34, 35, 36, 37, 38, 39, 40, 45, 46, 145].includes(tecla)
        || (tecla >= 186 && tecla <= 192) || (tecla >= 219 && tecla <= 222);
      if (!valida || e.metaKey) return toast("Escolha outra tecla, como F8, opcionalmente com Ctrl, Alt ou Shift.", true);
      cancelarTecla();
      enviar("preferencias", { teclaFalar: tecla, modificadoresFalar: (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.shiftKey ? 4 : 0) });
    }, true);
    $("btn-fechar-config").addEventListener("click", cancelarTecla);
    $("veu").addEventListener("click", cancelarTecla);
    let espera;
    $("cfg-sens").oninput = e => {
      const p = +e.target.value; e.target.style.setProperty("--p", p + "%"); $("medidor-marca").style.left = p + "%";
      config.sensibilidade = deSlider(p);
      clearTimeout(espera); espera = setTimeout(() => enviar("preferencias", { sensibilidade: config.sensibilidade }), 350);
    };
    $("btn-salvar").onclick = () => {
      const chave = $("cfg-chave").value.trim();
      enviar("salvar", { servidor: $("cfg-servidor").value.trim(), chave: chave });
    };
    $("btn-painel").onclick = () => enviar("abrir_painel", { servidor: $("cfg-servidor").value.trim() });
    $("btn-sair").onclick = () => enviar("sair");
    $("btn-pasta").onclick = () => enviar("pasta_arquivos");
    $("btn-comando-programa").onclick = () => enviar("comando_escolher_programa");
    $("btn-comando-pasta").onclick = () => enviar("comando_escolher_pasta");
    $("btn-comando-cancelar").onclick = limparComando;
    $("comando-tipo").onchange = tipoComando; $("comando-variavel").onchange = tipoComando;
    $("form-comando").onsubmit = e => {
      e.preventDefault();
      const tipo = $("comando-tipo").value, pesquisa = ["google", "youtube", "maps"].includes(tipo);
      let frase = $("comando-frase").value.trim();
      if (pesquisa && $("comando-variavel").checked && !frase.includes("{assunto}")) frase += " {assunto}";
      if (pesquisa && !$("comando-variavel").checked && frase.includes("{assunto}")) return toast("Retire {assunto} da frase para usar um assunto fixo.", true);
      enviar("comando_pasta", { id: comandoEmEdicao, frase, tipo, termo: $("comando-termo").value.trim(), caminho: $("comando-caminho").value.trim() });
    };
    $("btn-arquivos-ajuda").onclick = () => { fechar(); enviar("enviar", { texto: "/arquivos ajuda" }); };
    // Foto
    $("btn-escolher").onclick = e => { e.preventDefault(); $("arquivo").click(); };
    $("soltar").onclick = e => { if (e.target === $("soltar") || e.target.closest(".soltar-prev")) $("arquivo").click(); };
    $("arquivo").onchange = e => { const f = e.target.files[0]; e.target.value = ""; if (f) lerArquivo(f); };
    $("btn-recortar").onclick = e => { e.preventDefault(); enviar("foto_original"); };
    $("btn-remover").onclick = e => { e.preventDefault(); enviar("foto", { dataUrl: null }); };
    const zona = $("soltar");
    ["dragenter", "dragover"].forEach(t => zona.addEventListener(t, e => { e.preventDefault(); zona.classList.add("sobre"); }));
    ["dragleave", "drop"].forEach(t => zona.addEventListener(t, e => { e.preventDefault(); zona.classList.remove("sobre"); }));
    zona.addEventListener("drop", e => { const f = e.dataTransfer.files[0]; if (f) lerArquivo(f); });
    // a janela inteira aceita soltar uma foto (sem o navegador "abrir" o arquivo)
    window.addEventListener("dragover", e => e.preventDefault());
    window.addEventListener("drop", e => e.preventDefault());
    // Boas-vindas
    $("bv-painel").onclick = () => enviar("abrir_painel", {});
    $("bv-salvar").onclick = () => {
      const chave = $("bv-chave").value.trim();
      if (!chave) return erroSalvar("Cole a chave gerada no painel.");
      $("bv-erro").hidden = true; enviar("salvar", { chave: chave, servidor: config.servidor });
    };
    $("bv-chave").addEventListener("keydown", e => { if (e.key === "Enter") $("bv-salvar").click(); });
  }
  function erroSalvar(texto) {
    if (!$("boas-vindas").hidden) { $("bv-erro").textContent = texto; $("bv-erro").hidden = false; }
    else toast(texto, true);
  }

  // ── Foto: ler, reduzir e recortar ──────────────────────────
  // ── Recorte de tela: a prévia ──
  // A imagem em tamanho real fica no C# (copiar/salvar); aqui chega a versão de envio (JPEG, até 1280 px).
  let captura = null;
  function abrirCaptura(m) {
    captura = m.url; $("captura-img").src = m.url;
    $("captura-medida").textContent = m.largura + " × " + m.altura + " px";
    $("captura-pedido").value = ""; $("modal-captura").hidden = false;
    setTimeout(() => $("captura-pedido").focus(), 60);
  }
  function fecharCaptura() {
    if ($("modal-captura").hidden) return;
    $("modal-captura").hidden = true; $("captura-img").removeAttribute("src"); captura = null;
    enviar("captura_descartar");
  }

  let anexo = null;
  // a mesma referência aparece no chat (#anexo) e no painel de ferramentas (#ref-img)
  function mostrarAnexo(url) {
    const tem = !!url;
    if (tem) { $("anexo-img").src = url; if ($("ref-img")) $("ref-img").src = url; }
    else { $("anexo-img").removeAttribute("src"); if ($("ref-img")) $("ref-img").removeAttribute("src"); }
    $("anexo").hidden = !tem;
    if ($("ref-img")) { $("ref-img").hidden = !tem; $("ref-vazio").hidden = tem; $("ref-tirar").hidden = !tem; }
  }
  function tirarAnexo() { anexo = null; mostrarAnexo(null); }
  function anexar(f) {
    if (!/^image\/(png|jpeg|webp)$/.test(f.type)) return toast("Use uma imagem JPG, PNG ou WEBP.", true);
    if (f.size > 25 * 1024 * 1024) return toast("Essa imagem é grande demais (máximo 25 MB).", true);
    const leitor = new FileReader();
    leitor.onload = () => reduzir(leitor.result, 1280, .85).then(url => {
      anexo = url; mostrarAnexo(url);
      toast("Referência anexada. Peça o prompt (ou só envie) para eu usar a imagem.");
      $("entrada").focus();
    }).catch(() => toast("Não consegui abrir essa imagem.", true));
    leitor.readAsDataURL(f);
  }
  function lerArquivo(f) {
    if (!/^image\/(png|jpeg|webp)$/.test(f.type)) return toast("Use uma imagem JPG, PNG ou WEBP.", true);
    if (f.size > 25 * 1024 * 1024) return toast("Essa imagem é grande demais (máximo 25 MB).", true);
    const leitor = new FileReader();
    leitor.onload = () => reduzir(leitor.result, 1600, .92).then(abrirRecorte).catch(() => toast("Não consegui abrir essa imagem.", true));
    leitor.readAsDataURL(f);
  }
  function carregar(src) {
    return new Promise((ok, falha) => { const i = new Image(); i.onload = () => ok(i); i.onerror = falha; i.src = src; });
  }
  function reduzir(src, lado, q) {
    return carregar(src).then(img => {
      const k = Math.min(1, lado / Math.max(img.naturalWidth, img.naturalHeight));
      const c = document.createElement("canvas"); c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      return c.toDataURL("image/jpeg", q);
    });
  }

  const rc = { img: null, x: 0, y: 0, base: 1, zoom: 1, lado: 0, original: null };
  function abrirRecorte(dataUrl) {
    rc.original = dataUrl;
    $("modal-recorte").hidden = false;
    carregar(dataUrl).then(img => {
      const el = $("recorte-img"); el.src = dataUrl;
      rc.img = img; rc.lado = $("recorte").clientWidth;
      rc.base = rc.lado / Math.min(img.naturalWidth, img.naturalHeight);
      rc.zoom = 1; $("recorte-zoom").value = 100; $("recorte-zoom").style.setProperty("--p", "0%");
      rc.x = (rc.lado - img.naturalWidth * rc.base) / 2;
      rc.y = (rc.lado - img.naturalHeight * rc.base) / 2 * .35;   // rostos costumam estar no alto
      desenharRecorte();
    });
  }
  function limitar() {
    const s = rc.base * rc.zoom, w = rc.img.naturalWidth * s, h = rc.img.naturalHeight * s;
    rc.x = Math.min(0, Math.max(rc.lado - w, rc.x)); rc.y = Math.min(0, Math.max(rc.lado - h, rc.y));
  }
  function desenharRecorte() {
    limitar();
    $("recorte-img").style.transform = "translate(" + rc.x + "px," + rc.y + "px) scale(" + (rc.base * rc.zoom) + ")";
  }
  function fecharRecorte() { $("modal-recorte").hidden = true; rc.img = null; }
  function ligarRecorte() {
    const area = $("recorte"); let arrasto = null;
    area.addEventListener("pointerdown", e => { if (!rc.img) return; arrasto = { x: e.clientX - rc.x, y: e.clientY - rc.y }; area.setPointerCapture(e.pointerId); });
    area.addEventListener("pointermove", e => { if (!arrasto) return; rc.x = e.clientX - arrasto.x; rc.y = e.clientY - arrasto.y; desenharRecorte(); });
    area.addEventListener("pointerup", () => arrasto = null);
    area.addEventListener("wheel", e => { e.preventDefault(); const z = $("recorte-zoom"); z.value = Math.max(100, Math.min(400, +z.value - Math.sign(e.deltaY) * 12)); z.oninput(); }, { passive: false });
    $("recorte-zoom").oninput = () => {
      if (!rc.img) return;
      const z = $("recorte-zoom"); const antes = rc.base * rc.zoom; rc.zoom = z.value / 100;
      z.style.setProperty("--p", ((z.value - 100) / 3) + "%");
      const depois = rc.base * rc.zoom, m = rc.lado / 2;           // aproxima pelo centro
      rc.x = m - (m - rc.x) * depois / antes; rc.y = m - (m - rc.y) * depois / antes;
      desenharRecorte();
    };
    $("btn-recorte-cancelar").onclick = fecharRecorte;
    $("btn-recorte-ok").onclick = () => {
      if (!rc.img) return;
      const s = rc.base * rc.zoom, c = document.createElement("canvas"); c.width = c.height = 512;
      const g = c.getContext("2d"); g.imageSmoothingQuality = "high";
      g.drawImage(rc.img, -rc.x / s, -rc.y / s, rc.lado / s, rc.lado / s, 0, 0, 512, 512);
      enviar("foto", { dataUrl: c.toDataURL("image/jpeg", .9), original: rc.original });
      fecharRecorte();
    };
  }

  // ── Modo demonstração (fora do aplicativo) ─────────────────
  const demo = {
    acao(m) {
      const r = x => setTimeout(() => receber(x), 0);
      if (m.acao === "salvar") { r({ tipo: "config", temChave: true, chaveFinal: (m.chave || "Zq4x").slice(-4) }); r({ tipo: "salvo", texto: "Acesso salvo neste usuário do Windows." }); demo.escutar(true); }
      if (m.acao === "escuta") demo.escutar(!estado.escutando);
      if (m.acao === "preferencias") r(Object.assign({ tipo: "config" }, m));
      if (m.acao === "chamadas") { r({ tipo: "config", frasesAtivacao: m.frases }); r({ tipo: "toast", texto: "Frases de ativação salvas." }); }
      if (m.acao === "foto") r({ tipo: "config", foto: m.dataUrl || null, aparencia: "foto" });
      if (m.acao === "foto_original") r({ tipo: "foto_original", dataUrl: config.foto });
      if (m.acao === "falar") demo.pedido("o que eu tenho para hoje", true);
      if (m.acao === "enviar") demo.pedido(m.texto, false);
      if (m.acao === "parar_voz") r({ tipo: "estado", modo: "espera", ocupada: false });
      if (m.acao === "recortar_tela") r({ tipo: "captura", url: config.foto || new URLSearchParams(location.search).get("foto"), largura: 1840, altura: 1035 });
      if (m.acao === "captura_copiar") r({ tipo: "toast", texto: "Recorte copiado. Cole com Ctrl + V." });
    },
    escutar(sim) { receber({ tipo: "estado", modo: sim ? "espera" : "pausada", escutando: sim, ocupada: false }); },
    pedido(texto, voz) {
      const passo = (ms, x) => setTimeout(() => receber(x), ms);
      if (voz) { passo(0, { tipo: "estado", modo: "ouvindo", ocupada: true, escutando: true }); }
      passo(voz ? 1400 : 0, { tipo: "msg", de: "eu", texto: texto, via: voz ? "voz" : "texto" });
      passo(voz ? 1400 : 0, { tipo: "estado", modo: "pensando", ocupada: true });
      passo(voz ? 2600 : 1200, { tipo: "msg", de: "bella", texto: "⚔️ Rotinas\nVocê tem 4 missões hoje. O treino já foi; faltam leitura, banho frio e a meta da noite.\n\n1. ✅ — Leitura\n2. ✅ — Banho frio\n3. 📈 — Meta noite\n\n🧭 Entendi: Rotinas · /hoje",
        opcoes: [{ numero: 1, rotulo: "✅", titulo: "Leitura" }, { numero: 2, rotulo: "✅", titulo: "Banho frio" }, { numero: 3, rotulo: "📈", titulo: "Meta noite" }] });
      passo(voz ? 2600 : 1200, { tipo: "estado", modo: "falando", ocupada: true });
      passo(voz ? 6200 : 4800, { tipo: "estado", modo: "espera", ocupada: false });
    },
    iniciar() {
      const q = new URLSearchParams(location.search), cena = q.get("demo") || "conversa";
      const foto = q.get("foto");
      receber({ tipo: "config", temChave: cena !== "boasvindas", chaveFinal: "Zq4x", servidor: "https://solobot.duckdns.org", iniciar: true, mini: true, sensibilidade: 260, aparencia: "foto", foto: foto || null });
      const modo = q.get("modo") || "falando";
      receber({ tipo: "estado", modo: modo, escutando: modo !== "pausada", ocupada: modo !== "espera" && modo !== "pausada" });
      if (cena === "conversa" || cena === "config" || cena === "mini") {
        receber({ tipo: "msg", de: "bella", texto: "Oi, Jefferson. Estou aqui. Pode falar." });
        receber({ tipo: "msg", de: "eu", texto: "Bella, o que eu tenho para hoje?", via: "voz" });
        receber({ tipo: "msg", de: "bella", texto: "⚔️ Rotinas\nVocê tem 4 missões hoje. O treino já foi; faltam leitura, banho frio e a meta da noite.\n\n1. ✅ — Leitura\n2. ✅ — Banho frio\n3. 📈 — Meta noite\n\n🧭 Entendi: Rotinas · /hoje",
          opcoes: [{ numero: 1, rotulo: "✅", titulo: "Leitura" }, { numero: 2, rotulo: "✅", titulo: "Banho frio" }, { numero: 3, rotulo: "📈", titulo: "Meta noite" }] });
        receber({ tipo: "msg", de: "eu", texto: "Recebi 92,60 na conta Uber", via: "voz" });
        receber({ tipo: "msg", de: "bella", texto: "💰 Finances\nReceita de R$ 92,60 lançada na conta Uber. Saldo da conta: R$ 418,30." });
        receber({ tipo: "msg", de: "eu", texto: "Concluí a leitura", via: "texto" });
        receber({ tipo: "msg", de: "bella", texto: "⚔️ Rotinas\nLeitura concluída. +40 XP · 🔥 12 dias" });
        if (modo === "pensando") receber({ tipo: "estado", modo: "pensando" });
      }
      if (cena === "imagens") abrirImagens(false);
      if (cena === "config") { $("btn-config").click(); let k = 0; setInterval(() => receber({ tipo: "nivel", v: 180 + 900 * Math.abs(Math.sin(k++ / 4)) }), 80); }
      if (cena === "ouvindo") { receber({ tipo: "msg", de: "bella", texto: "Oi, Jefferson. Pode falar." }); let k = 0; setInterval(() => receber({ tipo: "nivel", v: 300 + 1600 * Math.abs(Math.sin(k++ / 3)) }), 80); }
      if (cena === "recorte" && foto) abrirRecorte(foto);
      if (cena === "captura" && foto) receber({ tipo: "captura", url: foto, largura: 1840, altura: 1035 });
      if (cena === "erro") aviso("A conexão falhou. Confira no sistema se o pedido foi executado antes de repetir.", true);
    }
  };

  // ── Início ─────────────────────────────────────────────────
  if (MINI) {
    document.body.classList.add("modo-mini");
    $("mini").hidden = false;
    $("mini").onclick = () => enviar("abrir");
  } else {
    ligarJanela(); ligarRecorte();
    const v = document.createElement("div"); v.className = "vazio";
    v.textContent = "Diga “" + config.frasesAtivacao[0] + "” e aguarde a saudação. Também dá para escrever aqui embaixo.";
    $("conversa").appendChild(v);
  }
  if (ponteReal) enviar("pronto"); else demo.iniciar();
})();
