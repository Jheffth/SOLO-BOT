"""Galeria Models: anexos reais no contrato, IDs isolados e transferência limitada."""
import base64
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from database import SessionLocal,Conta,Configuracao,CanalVinculo,BellaArquivo,BellaMemoria
from canais import entrega,evolution,telegram,midia as M
from nucleo import models,models_galeria as G,roteador,grok,bella_galeria

JPEG=b'\xff\xd8\xff\xe0'+b'0'*64
VIDEO=b'\x00\x00\x00\x18ftypmp42'+b'0'*64


def preparar(logado,monkeypatch):
    ident=str(uuid4());foto1=str(uuid4());foto2=str(uuid4());video=str(uuid4())
    itens=[{'id':foto1,'nivel':0,'tipo':'imagem'},{'id':foto2,'nivel':0,'tipo':'imagem'},
           {'id':video,'nivel':0,'tipo':'video'}]
    chamadas=[];downloads=[]
    def pedir(metodo,rota,conta=None,modelo_id=None,corpo=None):
        chamadas.append((metodo,rota,corpo))
        if rota.endswith('/pacote'):
            return {'modelo':{'id':rota.split('/')[-2],'nome':'Modelo própria','classificacao':'geral',
                'vozes_por_conta':[{'provedor':'voicestudio','ativa':True,'principal':True,'voice_id':'voz-propria'}]}}
        if '/midias?' in rota:
            assert f'/modelos/{modelo_id}/midias?' in rota and 'nivel_max=0' in rota
            return list(itens)
        if rota.endswith('/registros'):return {'id':str(uuid4())}
        raise AssertionError(rota)
    def baixar(ident,tipo):
        downloads.append((ident,tipo))
        return M.validar({'base64':base64.b64encode(VIDEO if tipo=='video' else JPEG).decode(),
            'mime':'video/mp4' if tipo=='video' else 'image/jpeg'})
    monkeypatch.setattr(models,'_requisicao',pedir)
    monkeypatch.setattr(G,'baixar',baixar)
    def proibido(*a,**k):raise AssertionError('Não deve usar a IA nem a galeria legada')
    monkeypatch.setattr(grok,'gerar',proibido)
    monkeypatch.setattr(bella_galeria,'escolher',proibido)
    db=SessionLocal();db.add(Configuracao(chave='models_selecao:1',valor=ident));db.commit();db.close()
    return ident,itens,chamadas,downloads


@pytest.mark.parametrize('canal',['whatsapp','telegram'])
def test_pedido_entrega_foto_com_voz_models_e_sem_memoria_legada(logado,monkeypatch,canal):
    ident,itens,chamadas,downloads=preparar(logado,monkeypatch)
    db=SessionLocal();conta=db.get(Conta,1)
    db.add(CanalVinculo(conta_id=1,canal=canal,origem='foto-teste'));db.commit()
    r=roteador._bella_responder(db,conta,canal,'me manda uma foto sua')
    assert r.mensagens[0]['midia']['tipo']=='imagem'
    assert r.mensagens[0]['modelo_voz']['voice_id']=='voz-propria'
    assert downloads[0][0] in [v['id'] for v in itens if v['tipo']=='imagem']
    assert db.query(BellaArquivo).count()==0 and db.query(BellaMemoria).count()==0
    gravados=[c for c in chamadas if c[0]=='POST']
    assert len(gravados)==1 and f'/{ident}/registros' in gravados[0][1]
    enviadas=[]
    monkeypatch.setattr(telegram,'enviar',lambda *a,**k:None)
    monkeypatch.setattr(evolution,'enviar',lambda *a,**k:None)
    monkeypatch.setattr(telegram,'enviar_midia',lambda *a,**k:enviadas.append(a[1]) or True)
    monkeypatch.setattr(evolution,'enviar_midia',lambda *a,**k:enviadas.append(base64.b64decode(a[1]['base64'])) or {'key':{'id':'teste'}})
    entrega.entregar(db,canal,'foto-teste',r,falar=False)
    assert enviadas==[JPEG]
    db.close()


def test_video_nao_vira_foto_e_galeria_nao_consulta_legado(logado,monkeypatch):
    ident,itens,_,downloads=preparar(logado,monkeypatch)
    db=SessionLocal();conta=db.get(Conta,1)
    r=roteador._bella_responder(db,conta,'whatsapp','quero um video')
    assert r.mensagens[0]['midia']['tipo']=='video' and downloads[-1]==(itens[2]['id'],'video')
    r=roteador._cmd_galeria(conta,'')
    assert 'Models' in r.mensagens[0]['texto'] and '2 foto(s)' in r.mensagens[0]['texto']
    assert roteador._cmd_galeria(conta,'ver normal').mensagens[0]['midia']['tipo']=='imagem'
    assert 'midia' not in roteador._cmd_galeria(conta,'ver topless').mensagens[0]
    db.close()


def test_vazio_e_falha_nao_prometem_anexo_nem_usam_fotos_de_outra_modelo(logado,monkeypatch):
    ident,itens,chamadas,_=preparar(logado,monkeypatch)
    itens.clear();saida=[]
    assert 'não tenho' in models.responder('manda uma foto',1,saida_midia=saida) and saida==[]
    itens.append({'id':str(uuid4()),'nivel':2,'tipo':'imagem'})
    assert 'não tenho' in models.responder('manda uma foto',1,saida_midia=saida) and saida==[]
    itens[0]['nivel']=0
    monkeypatch.setattr(G,'baixar',lambda *a:(_ for _ in ()).throw(models.ErroModels('Falha de teste')))
    assert 'Não consegui carregar' in models.responder('manda uma foto',1,saida_midia=saida) and saida==[]
    db=SessionLocal();conta=db.get(Conta,1);cfg=db.get(Configuracao,'models_selecao:1');cfg.valor=str(uuid4());db.commit()
    itens.clear()
    assert 'não tenho' in models.responder('manda uma foto',1,saida_midia=saida)
    assert cfg.valor in chamadas[-2][1] and models.selecionado(1)==cfg.valor
    db.close()


def test_evitar_repeticao_e_isolado_por_dono_e_modelo(logado,monkeypatch):
    ident,itens,_,downloads=preparar(logado,monkeypatch)
    perfil={'id':ident};conta=SimpleNamespace(id=1)
    G.escolher(conta,perfil,'foto');G.escolher(conta,perfil,'foto')
    assert downloads[0][0]!=downloads[1][0]
    G.escolher(SimpleNamespace(id=2),perfil,'foto')
    db=SessionLocal();assert db.get(Configuracao,f'mg:1:{ident}') and db.get(Configuracao,f'mg:2:{ident}');db.close()


@pytest.mark.parametrize('texto,tipo',[
    ('manda uma foto','foto'),('quero uma foto sua','foto'),('/foto','foto'),('selfie!','foto'),
    ('/video','video'),('me envie um vídeo','video'),('foto ficou linda',None),('não manda foto',None)])
def test_detectar_pedido_sem_confundir_comentario_ou_negacao(texto,tipo):
    assert G.detectar(texto)==tipo


def test_download_autenticado_valida_tipo_e_tamanho(monkeypatch):
    cliente=httpx.Client;pedidos=[]
    monkeypatch.setattr(G.modulos,'por_chave',lambda k:SimpleNamespace(url='http://models',token='servico-teste'))
    def usar(conteudo,mime='image/jpeg'):
        def responder(r):
            pedidos.append(r)
            return httpx.Response(200,content=conteudo,headers={'content-type':mime})
        monkeypatch.setattr(G.httpx,'Client',lambda **kw:cliente(transport=httpx.MockTransport(responder),**kw))
    ident=str(uuid4());usar(JPEG)
    assert G.baixar(ident,'imagem')['mime']=='image/jpeg'
    assert pedidos[0].headers['x-solo-token']=='servico-teste'
    assert str(pedidos[0].url)==f'http://models/api/servico/midias/{ident}/arquivo'
    usar(b'MZ-nao-e-foto')
    with pytest.raises(models.ErroModels):G.baixar(ident,'imagem')
    usar(JPEG,'application/pdf')
    with pytest.raises(models.ErroModels):G.baixar(ident,'imagem')
    usar(JPEG);monkeypatch.setattr(M,'IMAGEM_MAX',8)
    with pytest.raises(models.ErroModels):G.baixar(ident,'imagem')
    antes=len(pedidos)
    with pytest.raises(models.ErroModels):G.baixar('https://outro/arquivo','imagem')
    assert len(pedidos)==antes
