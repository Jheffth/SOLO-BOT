"""Escolha de modelos: catálogo vivo, conversa, voz e legado isolados."""
from database import SessionLocal,Conta,BellaArquivo,BellaMemoria
from nucleo import models,bella_conversa,roteador,fala

IDENT='e5bd7992-24bf-42fe-b54c-abd355b8966c'

def remoto(monkeypatch):
    chamadas=[]
    itens=[{'id':IDENT,'nome':'Bella','descricao':'Personagem do Models','classificacao':'geral','versao':1}]
    voz={'provedor':'voicestudio','conta':'voicestudio','voice_id':'voz-escolhida','ativa':True,'principal':True}
    def pedir(metodo,rota,conta=None,modelo_id=None,corpo=None):
        chamadas.append((metodo,rota,corpo))
        if rota.endswith('/pacote'):return {'modelo':{**itens[0],'persona':'Persona própria do Models',
            'vozes_por_conta':[voz]}}
        if rota.endswith('/contexto'):return {'historico':[],'memorias':[{'tipo':'bella_memorias','texto':'Gosto de chuva'}]}
        if rota.endswith('/registros'):return {'id':'registro'} if metodo=='POST' else []
        return list(itens)
    monkeypatch.setattr(models,'_requisicao',pedir)
    return itens,chamadas,voz

def test_catalogo_dinamico_escolha_e_volta_ao_legado(logado,monkeypatch):
    itens,_,_=remoto(monkeypatch)
    assert logado.get('/api/conta/models').json()['origem']=='legado'
    assert logado.put('/api/conta/models',json={'modelo_id':IDENT}).status_code==200
    from database import Sessao
    db=SessionLocal();assert db.query(Sessao).filter_by(canal='bella',origem='bella:1').one().modo=='bella';db.close()
    assert logado.get('/api/conta/models').json()['modelo_id']==IDENT
    itens.append({'id':'outro','nome':'Aurora','descricao':'Outra personagem','classificacao':'geral'})
    assert [m['nome'] for m in logado.get('/api/conta/models').json()['modelos']]==['Bella','Aurora']
    assert logado.put('/api/conta/models',json={'modelo_id':None}).status_code==200
    assert models.selecionado(1) is None

def test_conversa_models_nao_grava_no_legado(logado,monkeypatch):
    _,chamadas,voz=remoto(monkeypatch)
    logado.put('/api/conta/models',json={'modelo_id':IDENT})
    from nucleo import grok
    prompts=[]
    monkeypatch.setattr(grok,'gerar',lambda p,t,**k:prompts.append(p) or 'Resposta do Models')
    monkeypatch.setattr('nucleo.bella_estado.avancar',lambda *a:(_ for _ in ()).throw(AssertionError('Legado chamado')))
    resposta=bella_conversa.responder('Olá',1)
    assert resposta=='Resposta do Models' and resposta.voz_models==voz
    assert 'Persona própria' in prompts[0] and 'Gosto de chuva' in prompts[0]
    assert any(m=='POST' and r.endswith('/registros') for m,r,c in chamadas)
    db=SessionLocal();assert db.query(BellaArquivo).count()==0;assert db.query(BellaMemoria).count()==0;db.close()
    assert models.comando(type('C',(),{'id':1,'admin':False})(),'/lembrar','gosto de música')
    db=SessionLocal();assert db.query(BellaMemoria).count()==0;db.close()

def test_menu_e_voz_preservam_modelo(logado,monkeypatch):
    _,_,voz=remoto(monkeypatch)
    db=SessionLocal();conta=db.get(Conta,1)
    r=roteador.menu(db,conta)
    acoes=[a['rotulo'] for m in r.mensagens for g in m['opcoes'] for a in g['acoes']]
    assert 'Bella (Legado)' in acoes and 'Models' in acoes
    chamadas=[]
    monkeypatch.setattr(models,'sintetizar',lambda texto,canal,v:chamadas.append(v) or {'base64':'audio','mime':'audio/mpeg'})
    conta.voz='sempre'
    r=roteador.Resposta().diz(models.TextoModels('Olá',voz));r.mensagens[0]['literal']=True
    fala.falar_resposta(conta,'whatsapp',r,False)
    assert chamadas==[voz] and r.mensagens[0]['audio']['base64']=='audio'
    db.close()

def test_indisponibilidade_nao_troca_a_escolha(logado,monkeypatch):
    remoto(monkeypatch);logado.put('/api/conta/models',json={'modelo_id':IDENT})
    def falha(*a,**k):raise models.ErroModels('Indisponível')
    monkeypatch.setattr(models,'_requisicao',falha)
    r=logado.get('/api/conta/models').json()
    assert r['disponivel'] is False and r['modelo_id']==IDENT
    assert 'Indisponível' in bella_conversa.responder('Olá',1)
    assert logado.put('/api/conta/models',json={'modelo_id':None}).status_code==200


def test_atalhos_e_sessao_expirada_preservam_models(logado,monkeypatch):
    from datetime import datetime,timedelta
    from database import CanalVinculo
    remoto(monkeypatch)
    db=SessionLocal()
    db.add(CanalVinculo(conta_id=1,canal='telegram',origem='111'))
    db.commit()
    assert logado.put('/api/conta/models',json={'modelo_id':IDENT}).status_code==200
    for comando in ['/bella','/sair','/menu','/safada','/bella']:
        s=roteador.sessao_de(db,'telegram','111')
        s.modo_em=datetime.utcnow()-timedelta(minutes=31);db.commit()
        resposta=roteador.atender_texto(db,'telegram','111',comando)
        assert models.selecionado(1)==IDENT,comando
        if comando in ('/bella','/safada'):
            assert 'Models' in resposta.mensagens[0]['texto']
    db.close()
    # Reabrir a conexão ou reler a API também conserva a preferência persistida.
    assert logado.get('/api/conta/models').json()['modelo_id']==IDENT


def test_so_comando_explicito_legado_limpa_models(logado,monkeypatch):
    from database import CanalVinculo
    remoto(monkeypatch)
    db=SessionLocal();db.add(CanalVinculo(conta_id=1,canal='telegram',origem='111'));db.commit()
    logado.put('/api/conta/models',json={'modelo_id':IDENT})
    roteador.atender_texto(db,'telegram','111','/bella LEGADO')
    assert models.selecionado(1) is None
    assert logado.get('/api/conta/models').json()['origem']=='legado'
    db.close()


def test_falha_de_leitura_nao_finge_escolha_legado(logado,monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    import pytest
    class BancoIndisponivel:
        def get(self,*a):raise SQLAlchemyError('indisponível')
        def close(self):pass
    monkeypatch.setattr(models,'SessionLocal',BancoIndisponivel)
    with pytest.raises(models.ErroModels):models.selecionado(1)
    monkeypatch.setattr('nucleo.bella_estado.avancar',lambda *a:(_ for _ in ()).throw(AssertionError('Legado chamado')))
    assert 'não foi alterada' in bella_conversa.responder('Olá',1)
    r=logado.get('/api/conta/models')
    assert r.status_code==503 and 'origem' not in r.json()
