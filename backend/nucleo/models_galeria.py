"""Fotos e vídeos da modelo selecionada; nunca consulta a galeria legada."""
import base64
import json
import random
import re
from urllib.parse import quote
from uuid import UUID

import httpx
from canais import midia as canal_midia
from database import Configuracao, SessionLocal, gravar_config
from nucleo import bella_galeria, models, modulos


def detectar(texto):
    from nucleo.bella_emocoes import _norm
    t=_norm(texto)
    if re.search(r'\bnao (?:me )?(?:manda|mande|envia|envie|quero|mostra|mostre)\b',t):return None
    direto=re.match(r'^\s*/(foto|selfie|imagem|v[ií]deo)\b',texto,re.I) or re.fullmatch(r'\s*(foto|selfie|imagem|v[ií]deo)[!?.,\s]*',texto,re.I)
    if direto:return 'video' if direto[1].lower() in ('video','vídeo') else 'foto'
    if re.search(r'\b(?:quero|gostaria de) (?:uma? )?(?:foto|selfie|imagem|video)\b',t):
        return 'video' if re.search(r'\bvideo\b',t) else 'foto'
    return bella_galeria.detectar_pedido(texto)


def catalogo(conta,perfil,tipo=None):
    # O envio padrão fica no nível 0. Níveis íntimos exigem sua própria autorização.
    rota='/api/servico/modelos/'+quote(perfil['id'],safe='')+'/midias?nivel_max=0'
    if tipo:rota+='&tipo='+tipo
    itens=models._requisicao('GET',rota,conta,perfil['id'])
    if not isinstance(itens,list):raise models.ErroModels('Não consegui consultar a galeria desta modelo.')
    return [v for v in itens if isinstance(v,dict) and type(v.get('nivel')) is int and v['nivel']==0
            and v.get('tipo') in ('imagem','video') and (not tipo or v['tipo']==tipo)]


def baixar(ident,tipo):
    """Lê apenas o arquivo autenticado do serviço, com limite durante a transferência."""
    try:
        if str(UUID(ident))!=ident:raise ValueError()
    except (ValueError,TypeError,AttributeError):
        raise models.ErroModels('O identificador da mídia foi recusado.') from None
    mod=modulos.por_chave('models')
    if not mod or not mod.token:raise models.ErroModels('O Solo Models ainda não está configurado.')
    limite=canal_midia.VIDEO_MAX if tipo=='video' else canal_midia.IMAGEM_MAX
    try:
        with httpx.Client(timeout=httpx.Timeout(30,connect=4),follow_redirects=False) as c:
            with c.stream('GET',mod.url+'/api/servico/midias/'+ident+'/arquivo',headers={'X-Solo-Token':mod.token}) as r:
                r.raise_for_status()
                mime=r.headers.get('content-type','').split(';')[0].strip().lower()
                permitidos=canal_midia.MIMES_VIDEO if tipo=='video' else canal_midia.MIMES_IMAGEM
                if mime not in permitidos:raise ValueError()
                tamanho=r.headers.get('content-length')
                if tamanho and int(tamanho)>limite:raise ValueError()
                partes=[];total=0
                for bloco in r.iter_bytes(chunk_size=65536):
                    total+=len(bloco)
                    if total>limite:raise ValueError()
                    partes.append(bloco)
        midia=canal_midia.validar({'base64':base64.b64encode(b''.join(partes)).decode(),'mime':mime})
        if not midia:raise ValueError()
        return midia
    except (httpx.HTTPError,ValueError):
        raise models.ErroModels('Não consegui carregar essa mídia agora. Tente novamente.') from None


def escolher(conta,perfil,pedido):
    tipo='video' if pedido=='video' else 'imagem'
    itens=catalogo(conta,perfil,tipo)
    if not itens:return None
    chave=f"mg:{conta.id}:{perfil['id']}"
    db=SessionLocal()
    try:
        cfg=db.get(Configuracao,chave)
        usadas=json.loads(cfg.valor) if cfg and cfg.valor else []
        novos=[v for v in itens if v['id'] not in usadas] or itens
        random.shuffle(novos)
        for item in novos[:5]:
            try:midia=baixar(item['id'],tipo)
            except models.ErroModels:continue
            gravar_config(db,chave,json.dumps((usadas+[item['id']])[-30:]))
            return midia
        raise models.ErroModels('Não consegui carregar as mídias desta galeria agora. Tente novamente.')
    finally:db.close()


def galeria(conta,resto):
    from nucleo.roteador import Resposta
    try:
        ident=models.selecionado(conta.id)
        perfil=models.pacote(conta,ident)
        partes=resto.lower().split()
        if partes and partes[0] in ('ver','testar'):
            nivel=partes[1] if len(partes)>1 else 'normal'
            if nivel not in ('0','normal','bom_dia','foto','video','vídeo'):
                return Resposta().diz('Esse nível não está liberado para envio nesta conversa.')
            pedido='video' if nivel in ('video','vídeo') else 'foto'
            midia=escolher(conta,perfil,pedido)
            texto=('Aqui está um vídeo da minha galeria.' if pedido=='video' else 'Aqui está uma foto da minha galeria.') if midia else 'Ainda não há essa mídia disponível na minha galeria.'
            return Resposta().diz(texto,midia=midia)
        itens=catalogo(conta,perfil)
        fotos=sum(v['tipo']=='imagem' for v in itens);videos=sum(v['tipo']=='video' for v in itens)
        return Resposta().diz(f"🖼️ Galeria de {perfil['nome']} · Models\n{fotos} foto(s) e {videos} vídeo(s) disponíveis.\n/galeria ver normal · /galeria ver video")
    except models.ErroModels as e:return Resposta().diz(str(e))
