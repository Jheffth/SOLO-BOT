/* Contatos persistentes e um envio explícito por clique; consultar nunca reenvia. */
(function () {
  "use strict";
  window.iniciarEnviosAudio = function (conta) {
    const { api, toast } = Solo;
    const $ = id => document.getElementById(id);
    const chave = "solo-audio-pedido:" + conta.id;
    const rotulos = {gerando:"Gerando áudio",enviando:"Enviando ao WhatsApp",enviado:"Aceito pelo WhatsApp",falhou:"Falhou",incerto:"Resultado não confirmado"};
    let contatos = [], config = null, pedido = null, trabalhando = false;
    try { pedido = sessionStorage.getItem(chave); } catch (_) {}
    function memorizar(id) { pedido = id; try { if (id) sessionStorage.setItem(chave,id); else sessionStorage.removeItem(chave); } catch (_) {} }
    function atualizar() {
      const bloqueado = trabalhando || !!pedido;
      $("audio-destinatario").disabled = bloqueado;
      $("audio-texto").disabled = bloqueado;
      $("audio-enviar").disabled = bloqueado || !config || !config.whatsapp_configurado || !config.voz_configurada || !$("audio-destinatario").value || !$("audio-texto").value.trim();
      $("audio-consultar").hidden = !pedido;
      $("audio-consultar").disabled = trabalhando;
      $("audio-novo").hidden = !pedido || trabalhando;
      const destino = contatos.find(c => String(c.id) === $("audio-destinatario").value);
      $("audio-destino").textContent = destino ? destino.nome + " · +" + destino.numero : "Escolha quem receberá o áudio.";
      $("audio-contagem").textContent = $("audio-texto").value.length;
    }
    function status(texto, estado) { $("audio-status").textContent = texto; $("audio-status").dataset.estado = estado || ""; }
    function resultado(r) { status((rotulos[r.estado] || r.estado) + " · +" + r.numero + ". " + (r.detalhe || ""), r.estado); }
    function renderizar(d) {
      config = d; contatos = d.contatos;
      const selecionado = $("audio-destinatario").value;
      $("audio-contatos").replaceChildren(); $("audio-destinatario").replaceChildren();
      const padrao = document.createElement("option"); padrao.value = ""; padrao.textContent = "Selecione um contato"; $("audio-destinatario").appendChild(padrao);
      contatos.forEach(c => {
        const opcao = document.createElement("option"); opcao.value = c.id; opcao.textContent = c.nome + " · +" + c.numero; $("audio-destinatario").appendChild(opcao);
        const li = document.createElement("li"), dados = document.createElement("div"), nome = document.createElement("b"), numero = document.createElement("small"), remover = document.createElement("button");
        nome.textContent = c.nome; numero.textContent = "+" + c.numero; dados.append(nome,numero);
        remover.type = "button"; remover.className = "btn pequeno fantasma"; remover.textContent = "Remover"; remover.disabled = trabalhando;
        remover.onclick = async () => { remover.disabled = true; try { await api("/api/admin/audios/contatos/" + c.id,{method:"DELETE"}); await carregar(); } catch(e) { toast(e.message,"erro"); remover.disabled = false; } };
        li.append(dados,remover); $("audio-contatos").appendChild(li);
      });
      if (!contatos.length) { const vazio = document.createElement("li"); vazio.className = "muted pequeno"; vazio.textContent = "Salve seu primeiro contato acima."; $("audio-contatos").appendChild(vazio); }
      $("audio-destinatario").value = selecionado;
      $("audio-historico").replaceChildren();
      d.envios.forEach(e => { const li=document.createElement("li"), dados=document.createElement("div"), nome=document.createElement("b"), detalhe=document.createElement("small"); nome.textContent=e.nome+" · +"+e.numero; detalhe.textContent=(rotulos[e.estado]||e.estado)+" · "+new Date(e.criado_em+"Z").toLocaleString("pt-BR"); dados.append(nome,detalhe); li.appendChild(dados); $("audio-historico").appendChild(li); });
      if (!d.envios.length) { const vazio=document.createElement("li"); vazio.className="muted pequeno"; vazio.textContent="Nenhum envio registrado."; $("audio-historico").appendChild(vazio); }
      atualizar();
    }
    async function carregar() { renderizar(await api("/api/admin/audios")); }
    async function consultar() {
      if (!pedido || trabalhando) return;
      trabalhando = true; atualizar();
      try { resultado(await api("/api/admin/audios/envios/"+pedido)); }
      catch(e) { status(e.message + " Nenhum reenvio foi feito.","incerto"); }
      finally { trabalhando=false; atualizar(); }
    }
    $("audio-contato-form").onsubmit = async e => {
      e.preventDefault(); const botao=$("audio-contato-salvar"); botao.disabled=true;
      try { const c=await api("/api/admin/audios/contatos",{method:"POST",body:{nome:$("audio-contato-nome").value.trim(),numero:$("audio-contato-numero").value.trim()}}); $("audio-contato-form").reset(); await carregar(); if(!pedido) $("audio-destinatario").value=String(c.id); atualizar(); toast("Contato salvo."); }
      catch(e) { toast(e.message,"erro"); } finally {botao.disabled=false;}
    };
    $("audio-envio-form").onsubmit = async e => {
      e.preventDefault();
      if(trabalhando || pedido || $("audio-enviar").disabled) return;
      const contato=contatos.find(c=>String(c.id)===$("audio-destinatario").value), texto=$("audio-texto").value.trim();
      if(!contato || !texto) return;
      memorizar(crypto.randomUUID()); trabalhando=true; atualizar();
      status("Gerando áudio para "+contato.nome+" · +"+contato.numero+". Aguarde; o pedido será enviado uma única vez.","gerando");
      const idAtual=pedido;
      let finalizado=false, consultando=false;
      const progresso=setInterval(async()=>{
        if(finalizado || consultando) return;
        consultando=true;
        try { const r=await api("/api/admin/audios/envios/"+idAtual); if(!finalizado && pedido===idAtual) resultado(r); }
        catch(_) { /* O POST mantém o resultado; consultar nunca provoca reenvio. */ }
        finally {consultando=false;}
      },2500);
      try {
        const r=await api("/api/admin/audios/enviar",{method:"POST",body:{pedido_id:pedido,contato_id:contato.id,texto}});
        finalizado=true; resultado(r); await carregar().catch(()=>{});
      } catch(e) {
        finalizado=true;
        if([400,401,403,404,409,422,429].includes(e.status)) {memorizar(null); status(e.message,"falhou");}
        else status(e.message+" Consulte o envio antes de criar outro pedido.","incerto");
      } finally {finalizado=true; clearInterval(progresso); trabalhando=false; atualizar();}
    };
    $("audio-destinatario").onchange=atualizar; $("audio-texto").oninput=atualizar;
    $("audio-consultar").onclick=consultar;
    $("audio-novo").onclick=()=>{memorizar(null); $("audio-texto").value=""; status("Escreva uma nova mensagem e confira o destinatário."); atualizar();};
    carregar().then(()=>{ if(pedido) return consultar(); status(!config.whatsapp_configurado ? "Conecte o WhatsApp em Conexões." : !config.voz_configurada ? "Configure o motor de voz acima." : "Pronto. Selecione o contato e escreva a mensagem."); }).catch(e=>status(e.message,"falhou"));
    return {consultar,carregar};
  };
})();
