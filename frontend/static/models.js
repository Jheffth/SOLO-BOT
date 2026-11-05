/* A seleção das modelos fica no Models. Aqui permanece somente a Bella Legado. */
(function () {
  "use strict";
  const alvo=document.querySelector('#models-escolha');if(!alvo)return;
  let ocupado=false,revisao=0;
  async function carregar(){
    if(ocupado)return;
    const pedido=++revisao;
    try{
      const d=await Solo.api('/api/conta/models/estado');if(ocupado||pedido!==revisao)return;
      alvo.replaceChildren();
      const b=document.createElement('button');b.type='button';b.className='btn '+(d.origem==='legado'?'primario':'pequeno');
      b.textContent=d.origem==='legado'?'Bella Legado · Em uso':'Usar Bella Legado';b.setAttribute('aria-pressed',String(d.origem==='legado'));
      b.onclick=async()=>{ocupado=true;++revisao;b.disabled=true;try{
        await Solo.api('/api/conta/models',{method:'PUT',body:{modelo_id:null}});Solo.toast('Bella Legado selecionada.');
      }catch(e){Solo.toast(e.message);}finally{ocupado=false;await carregar();}};
      alvo.append(b);
      if(d.origem==='models'){const p=document.createElement('p');p.className='muted pequeno';p.textContent='Sua conversa está usando as modelos selecionadas no Models.';alvo.append(p);}
    }catch{if(!ocupado)alvo.textContent='Não foi possível consultar sua conversa. Tente novamente em instantes.';}
  }
  carregar();setInterval(()=>{if(!document.hidden)carregar();},30000);
})();
