// Extrator de frames de vídeo (Ferramentas). Tudo roda aqui, no WebView2: <video> + <canvas>. Nada sai do computador.
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  if (!$("fr-video")) return;
  var MAX = 80;                       // quadros guardados na galeria
  var v = $("fr-video"), url = null, fps = 30, nome = "video", quadros = [], marcaIni = null, marcaFim = null, ocupado = false;

  function aviso(t, erro) { if (window.bellaApi && window.bellaApi.aviso) window.bellaApi.aviso(t, erro); }
  function pad(n, k) { n = String(Math.floor(n)); while (n.length < k) n = "0" + n; return n; }
  function tempo(s) {
    if (!isFinite(s) || s < 0) s = 0;
    var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), seg = Math.floor(s % 60), ms = Math.round((s - Math.floor(s)) * 1000);
    if (ms === 1000) { ms = 0; seg++; }
    return (h ? pad(h, 2) + ":" : "") + pad(m, 2) + ":" + pad(seg, 2) + "." + pad(ms, 3);
  }
  function duracao() { return isFinite(v.duration) ? v.duration : 0; }
  function passo() { return 1 / (fps || 30); }
  function limitar(t) { var d = duracao(); return Math.max(0, Math.min(t, d ? Math.max(0, d - 0.0005) : t)); }
  function quadroAtual() { return Math.round(v.currentTime * fps); }

  function atualizar() {
    var tem = !!url;
    $("fr-controles").hidden = !tem;
    $("fr-vazio").hidden = tem;
    v.hidden = !tem;
    $("fr-tirar").hidden = !tem;
    if (!tem) return;
    var d = duracao();
    $("fr-pos").value = d ? Math.round(v.currentTime / d * 10000) : 0;
    $("fr-tempo").textContent = tempo(v.currentTime) + " / " + tempo(d);
    $("fr-num").textContent = "quadro ≈ " + quadroAtual() + " de " + Math.round(d * fps) + " (" + (Math.round(fps * 100) / 100) + " fps)";
    $("fr-marcas").textContent = (marcaIni === null ? "início: —" : "início " + tempo(marcaIni)) + "  ·  " + (marcaFim === null ? "fim: —" : "fim " + tempo(marcaFim));
    $("fr-n").textContent = quadros.length ? quadros.length + " quadro" + (quadros.length > 1 ? "s" : "") + " na galeria" : "";
    $("fr-galeria-acoes").hidden = !quadros.length;
  }

  function ir(t) {
    return new Promise(function (ok) {
      t = limitar(t);
      var fim = function () { v.removeEventListener("seeked", fim); atualizar(); ok(); };
      v.addEventListener("seeked", fim);
      v.currentTime = t;
      setTimeout(function () { v.removeEventListener("seeked", fim); ok(); }, 4000);   // segurança se o seek não disparar
    });
  }

  function estimarFps() {
    if (!v.requestVideoFrameCallback) return;
    var ultimo = null, deltas = [];
    var anterior = v.muted, volume = v.volume;
    v.muted = true;
    var cb = function (_, meta) {
      if (ultimo !== null && meta.mediaTime > ultimo) deltas.push(meta.mediaTime - ultimo);
      ultimo = meta.mediaTime;
      if (deltas.length < 8) v.requestVideoFrameCallback(cb);
      else {
        v.pause();
        deltas.sort(function (a, b) { return a - b; });
        var med = deltas[deltas.length >> 1];
        if (med > 0.004 && med < 0.5) fps = 1 / med;
        v.muted = anterior; v.volume = volume;
        ir(0);
      }
    };
    v.requestVideoFrameCallback(cb);
    var p = v.play(); if (p && p.catch) p.catch(function () { });
    setTimeout(function () { if (!v.paused) { v.pause(); v.muted = anterior; v.volume = volume; ir(0); } }, 2500);
  }

  function abrir(f) {
    if (!f) return;
    if (!/^video\//.test(f.type) && !/\.(mp4|webm|mov|m4v|mkv|avi|ogv)$/i.test(f.name)) return aviso("Escolha um arquivo de vídeo (MP4, WebM, MOV…).", true);
    limpar(true);
    nome = f.name.replace(/\.[^.]+$/, "").replace(/[^\w\-]+/g, "_").slice(0, 40) || "video";
    url = URL.createObjectURL(f);
    v.onerror = function () { aviso("O Windows não conseguiu abrir esse vídeo (formato sem suporte). Tente MP4 (H.264) ou WebM.", true); limpar(false); };
    v.onloadedmetadata = function () { fps = 30; marcaIni = marcaFim = null; atualizar(); };
    v.onloadeddata = function () { ir(0).then(estimarFps); };
    v.src = url;
    atualizar();
  }

  function limpar(manterGaleria) {
    try { v.pause(); } catch (e) { }
    if (url) { URL.revokeObjectURL(url); url = null; }
    v.removeAttribute("src"); try { v.load(); } catch (e) { }
    marcaIni = marcaFim = null;
    if (!manterGaleria) esvaziar();
    atualizar();
  }
  function esvaziar() { quadros.forEach(function (q) { URL.revokeObjectURL(q.url); }); quadros = []; desenharGaleria(); atualizar(); }

  function formato() { return $("fr-formato").value === "jpg" ? { mime: "image/jpeg", ext: "jpg", q: 0.92 } : { mime: "image/png", ext: "png" }; }

  function capturar() {
    return new Promise(function (ok, falha) {
      var w = v.videoWidth, h = v.videoHeight;
      if (!w || !h) return falha(new Error("sem imagem"));
      var c = document.createElement("canvas"); c.width = w; c.height = h;
      c.getContext("2d").drawImage(v, 0, 0, w, h);
      var f = formato();
      c.toBlob(function (b) { b ? ok({ blob: b, t: v.currentTime, w: w, h: h, ext: f.ext }) : falha(new Error("falha")); }, f.mime, f.q);
    });
  }
  function guardar(q) {
    if (quadros.length >= MAX) { aviso("A galeria tem no máximo " + MAX + " quadros. Remova alguns.", true); return false; }
    q.url = URL.createObjectURL(q.blob); q.id = Date.now() + "_" + Math.random().toString(36).slice(2, 6);
    quadros.push(q); return true;
  }
  function pegar() {
    return capturar().then(function (q) { if (guardar(q)) { desenharGaleria(); atualizar(); } })
      .catch(function () { aviso("Não consegui capturar esse quadro.", true); });
  }

  function nomeQuadro(q) { return nome + "_" + tempo(q.t).replace(/[:.]/g, "-") + "." + q.ext; }
  function baixar(q) {
    var a = document.createElement("a"); a.href = q.url; a.download = nomeQuadro(q);
    document.body.appendChild(a); a.click(); a.remove();
  }
  function comoReferencia(q) {
    if (!window.bellaApi || !window.bellaApi.anexar) return;
    var r = new FileReader();
    r.onload = function () { window.bellaApi.anexar(r.result); };
    r.readAsDataURL(q.blob);
  }

  function desenharGaleria() {
    var g = $("fr-galeria"); g.textContent = "";
    quadros.forEach(function (q) {
      var cel = document.createElement("figure"); cel.className = "fr-cel";
      var img = document.createElement("img"); img.src = q.url; img.alt = "Quadro em " + tempo(q.t); img.title = "Clique para ir a esse instante";
      img.onclick = function () { ir(q.t); };
      var leg = document.createElement("figcaption"); leg.textContent = tempo(q.t);
      var bs = document.createElement("div"); bs.className = "fr-cel-bt";
      [["Ref.", "Usar como imagem de referência", function () { comoReferencia(q); }],
       ["Salvar", "Salvar este quadro", function () { baixar(q); }],
       ["✕", "Remover da galeria", function () { URL.revokeObjectURL(q.url); quadros = quadros.filter(function (x) { return x !== q; }); desenharGaleria(); atualizar(); }]
      ].forEach(function (d) {
        var b = document.createElement("button"); b.type = "button"; b.className = "btn mini"; b.textContent = d[0]; b.title = d[1]; b.onclick = d[2]; bs.appendChild(b);
      });
      cel.appendChild(img); cel.appendChild(leg); cel.appendChild(bs); g.appendChild(cel);
    });
  }

  function trava(sim) { ocupado = sim; var bs = $("ferr-frames").querySelectorAll("button, input, select"); for (var i = 0; i < bs.length; i++) if (bs[i].id !== "fr-parar") bs[i].disabled = sim; $("fr-parar").hidden = !sim; }
  var parar = false;
  function extrair(tempos) {
    if (ocupado || !tempos.length) return Promise.resolve();
    if (tempos.length + quadros.length > MAX) { tempos = tempos.slice(0, Math.max(0, MAX - quadros.length)); aviso("Limite de " + MAX + " quadros: vou extrair só " + tempos.length + "."); }
    if (!tempos.length) return Promise.resolve();
    var volta = v.currentTime, i = 0; parar = false; v.pause(); trava(true);
    var passo1 = function () {
      if (parar || i >= tempos.length) return Promise.resolve();
      $("fr-n").textContent = "Extraindo " + (i + 1) + " de " + tempos.length + "…";
      return ir(tempos[i++]).then(capturar).then(function (q) { guardar(q); }).then(passo1);
    };
    return passo1().catch(function () { aviso("A extração parou: não consegui ler um dos quadros.", true); })
      .then(function () { trava(false); return ir(volta); }).then(function () { desenharGaleria(); atualizar(); });
  }

  function lista() {
    var d = duracao(), ini = $("fr-modo").value === "marcas" && marcaIni !== null ? marcaIni : v.currentTime;
    var n = Math.max(1, Math.min(MAX, parseInt($("fr-qtd").value, 10) || 1)), ms = Math.max(1, parseFloat($("fr-ms").value) || 100), t = [], i;
    if ($("fr-modo").value === "marcas") {
      var fim = marcaFim !== null ? marcaFim : d;
      if (fim <= ini) { aviso("O fim marcado precisa vir depois do início.", true); return []; }
      for (i = 0; i < n; i++) t.push(n === 1 ? ini : ini + (fim - ini) * i / (n - 1));
      if (n > 1) t[n - 1] = Math.min(t[n - 1], fim - 0.0005 > ini ? fim - 0.0005 : fim);
    } else if ($("fr-modo").value === "uniforme") {
      for (i = 0; i < n; i++) t.push(n === 1 ? 0 : (d - 0.0005) * i / (n - 1));
    } else {
      for (i = 0; i < n; i++) t.push(ini + i * ms / 1000);
    }
    return t.filter(function (x) { return x <= d + 0.001; });
  }

  function modoMudou() {
    var m = $("fr-modo").value;
    $("fr-ms-linha").hidden = m !== "intervalo";
    $("fr-dica-modo").textContent = m === "intervalo" ? "Parte do quadro atual e anda pelo intervalo escolhido."
      : m === "uniforme" ? "Distribui os quadros do primeiro ao último do vídeo todo."
      : "Distribui os quadros entre o início e o fim que você marcou (sem marca, usa o quadro atual e o fim do vídeo).";
  }

  function ligar() {
    $("fr-anexar").onclick = function () { $("fr-arquivo").click(); };
    $("fr-arquivo").onchange = function (e) { var f = e.target.files[0]; e.target.value = ""; abrir(f); };
    $("fr-tirar").onclick = function () { limpar(false); };
    var area = $("fr-area");
    ["dragover", "dragenter"].forEach(function (n) { area.addEventListener(n, function (e) { if (e.dataTransfer && [].some.call(e.dataTransfer.types || [], function (t) { return t === "Files"; })) { e.preventDefault(); e.stopPropagation(); area.classList.add("sobre"); } }); });
    area.addEventListener("dragleave", function () { area.classList.remove("sobre"); });
    area.addEventListener("drop", function (e) { area.classList.remove("sobre"); var f = e.dataTransfer && e.dataTransfer.files[0]; if (f && /^video\/|\.(mp4|webm|mov|m4v|mkv|avi|ogv)$/i.test(f.type + f.name)) { e.preventDefault(); e.stopPropagation(); abrir(f); } });

    $("fr-pos").oninput = function () { v.pause(); var d = duracao(); if (d) ir($("fr-pos").value / 10000 * d); };
    v.ontimeupdate = atualizar; v.onseeked = atualizar; v.onpause = atualizar;
    var passos = { "fr-m10": -10, "fr-m1": -1, "fr-p1": 1, "fr-p10": 10 };
    Object.keys(passos).forEach(function (id) { $(id).onclick = function () { v.pause(); ir(v.currentTime + passos[id]); }; });
    $("fr-q-1").onclick = function () { v.pause(); ir(v.currentTime - passo()); };
    $("fr-q1").onclick = function () { v.pause(); ir(v.currentTime + passo()); };
    $("fr-primeiro").onclick = function () { v.pause(); ir(0); };
    $("fr-ultimo").onclick = function () { v.pause(); ir(duracao() - passo() / 2); };
    $("fr-play").onclick = function () { if (v.paused) { var p = v.play(); if (p && p.catch) p.catch(function () { }); } else v.pause(); };
    v.onplay = function () { $("fr-play").textContent = "⏸ Pausar"; };
    v.onpause = function () { $("fr-play").textContent = "▶ Tocar"; atualizar(); };
    $("fr-ir").onclick = function () {
      var txt = $("fr-tempo-in").value.trim().replace(",", "."), t;
      if (!txt) return;
      if (/^\d+q$/i.test(txt)) t = parseInt(txt, 10) / fps;            // ex.: 120q = quadro 120
      else if (txt.indexOf(":") >= 0) { t = txt.split(":").reduce(function (a, p) { return a * 60 + (parseFloat(p) || 0); }, 0); }
      else t = parseFloat(txt);
      if (!isFinite(t)) return aviso("Digite o tempo em segundos (12.5), em min:seg (1:02.5) ou o quadro (120q).", true);
      v.pause(); ir(t);
    };
    $("fr-tempo-in").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); $("fr-ir").click(); } });
    $("fr-marcar-ini").onclick = function () { marcaIni = v.currentTime; atualizar(); };
    $("fr-marcar-fim").onclick = function () { marcaFim = v.currentTime; atualizar(); };
    $("fr-limpar-marcas").onclick = function () { marcaIni = marcaFim = null; atualizar(); };
    $("fr-pegar").onclick = function () { v.pause(); pegar(); };
    $("fr-pegar-ultimo").onclick = function () { v.pause(); ir(duracao() - passo() / 2).then(pegar); };
    $("fr-pegar-primeiro").onclick = function () { v.pause(); ir(0).then(pegar); };
    $("fr-extrair").onclick = function () { extrair(lista()); };
    $("fr-parar").onclick = function () { parar = true; };
    $("fr-modo").onchange = modoMudou; modoMudou();
    $("fr-salvar-todos").onclick = function () { quadros.forEach(function (q, i) { setTimeout(function () { baixar(q); }, i * 250); }); };
    $("fr-limpar-galeria").onclick = esvaziar;
    atualizar();
  }
  ligar();
})();
