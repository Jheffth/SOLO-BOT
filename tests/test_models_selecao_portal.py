"""Ponte do Models: conta assinada, limite real, conflito de abas e conversa sem IA."""
import time
from uuid import UUID
from jose import jwt
import pytest
import config
from database import Conta,Configuracao,SessionLocal
from nucleo import models,modulos

ROTA='/interno/models/portal/selecao'
IDS=[str(UUID(int=i+10)) for i in range(4)]


@pytest.fixture
def ponte(logado,monkeypatch):
    antigos=modulos.todos();modulos.recarregar([{'chave':'models','nome':'Models','url':'http://models','token':'token-models'}])
    monkeypatch.setattr(config,'MODELS_CONTEXTO_KEY','chave-de-contexto-de-teste-'*3)
    with SessionLocal() as db:
        db.get(Conta,1).admin=True
        db.add(Conta(id=2,nome='Outra conta',senha_hash='hash-sintetico',ativo=True,admin=False));db.commit()
    cenas={};pedidos=[]
    def remoto(metodo,rota,conta=None,modelo_id=None,corpo=None):
        pedidos.append((metodo,rota,conta.id if conta else None,corpo))
        atual=cenas.setdefault(conta.id,[]) if conta else []
        if rota.endswith('/pacote'):
            ident=rota.split('/')[-2]
            return {'modelo':{'id':ident,'nome':'Modelo '+str(IDS.index(ident)),'classificacao':'geral',
                'vozes_por_conta':[{'principal':True,'ativa':True}]}}
        if rota.endswith('/cena/adicionar'):
            if not atual:atual.append(modelo_id)
            atual.append(corpo['outra_modelo_id']);return {}
        if rota.endswith('/cena/remover'):
            cenas[conta.id]=[i for i in atual if i!=corpo['outra_modelo_id']];return {}
        if rota.endswith('/cena/encerrar'):cenas[conta.id]=[];return {}
        if rota.endswith('/cena'):return {'ativa':len(atual)>1,'presentes':[{'modelo_id':i} for i in atual]}
        raise AssertionError(rota)
    monkeypatch.setattr(models,'_requisicao',remoto)
    yield logado,cenas,pedidos
    modulos.recarregar([m.__dict__ for m in antigos])


def cabecalho(metodo='GET',dono='solo-bot:conta:1',**extra):
    agora=int(time.time())
    d={'dono_id':dono,'metodo':metodo,'rota':ROTA,'iss':'solo-models','aud':'solo-bot-selecao','iat':agora,'exp':agora+90,**extra}
    return {'X-Solo-Token':'token-models','X-Solo-Contexto':jwt.encode(d,config.MODELS_CONTEXTO_KEY,algorithm='HS256')}


def mudar(c,ident,ligada=True,dono='solo-bot:conta:1',revisao=None):
    rev=revisao or c.get(ROTA,headers=cabecalho(dono=dono)).json()['revisao']
    return c.put(ROTA,headers=cabecalho('PUT',dono),json={'modelo_id':ident,'ligada':ligada,'revisao':rev})


def test_ligar_tres_rejeitar_quarta_desligar_e_voltar_legado(ponte):
    c,cenas,pedidos=ponte
    for i,ident in enumerate(IDS[:3],1):
        r=mudar(c,ident);assert r.status_code==200,r.text
        assert len(r.json()['presentes'])==i
    assert mudar(c,IDS[3]).status_code==422
    assert c.get(ROTA,headers=cabecalho()).json()['presentes']==IDS[:3]
    assert mudar(c,IDS[1],False).json()['presentes']==[IDS[0],IDS[2]]
    assert mudar(c,IDS[2],False).json()['presentes']==[IDS[0]]
    assert mudar(c,IDS[0],False).json()['origem']=='legado'
    assert models.selecionado(1) is None
    assert not any('/mensagem' in p[1] or '/rodada' in p[1] for p in pedidos)


def test_revisao_impede_outra_aba_de_sobrescrever(ponte):
    c,_,_=ponte;antiga=c.get(ROTA,headers=cabecalho()).json()['revisao']
    assert mudar(c,IDS[0]).status_code==200
    assert mudar(c,IDS[1],revisao=antiga).status_code==409
    assert c.get(ROTA,headers=cabecalho()).json()['presentes']==[IDS[0]]


def test_assinatura_expiracao_metodo_e_dono(ponte):
    c,_,_=ponte
    assert c.get(ROTA).status_code==403
    assert c.get(ROTA,headers={'X-Solo-Token':'token-models'}).status_code==403
    for h in [cabecalho(exp=int(time.time())-1),cabecalho(aud='solo-models-relacoes'),
              cabecalho('PUT'),cabecalho(dono='solo-bot:conta:999'),cabecalho(dono='conta:1')]:
        assert c.get(ROTA,headers=h).status_code==403
    r=c.get(ROTA,headers=cabecalho());assert r.status_code==200
    assert c.put(ROTA,headers=cabecalho('PUT'),json={'modelo_id':IDS[0],'ligada':True,'revisao':r.json()['revisao'],'dono_id':'solo-bot:conta:2'}).status_code==422


def test_conta_comum_isolada_e_sem_cena(ponte):
    c,_,_=ponte
    assert mudar(c,IDS[0]).status_code==200
    dono='solo-bot:conta:2'
    assert mudar(c,IDS[1],dono=dono).json()['maximo']==1
    assert mudar(c,IDS[2],dono=dono).json()['presentes']==[IDS[2]]
    assert models.selecionado(1)==IDS[0] and models.selecionado(2)==IDS[2]


def test_falha_ao_ler_cena_nao_parece_selecao_vazia(ponte,monkeypatch):
    c,_,_=ponte;assert mudar(c,IDS[0]).status_code==200
    def falha(*a,**k):raise models.ErroModels('Não foi possível consultar a cena.')
    monkeypatch.setattr(models,'_requisicao',falha)
    assert c.get(ROTA,headers=cabecalho()).status_code==503
    assert models.selecionado(1)==IDS[0]
