"""Escolha de modelos: catálogo vivo, conversa, voz e legado isolados."""
from database import SessionLocal,Conta,BellaArquivo,BellaMemoria
from nucleo import models,bella_conversa,roteador,fala
import pytest

IDENT='e5bd7992-24bf-42fe-b54c-abd355b8966c'


@pytest.fixture(autouse=True)
def limpar_escolha_apos_teste():
    yield
    from database import Configuracao
    db=SessionLocal()
    try:
        db.query(Configuracao).filter(Configuracao.chave.like('models_selecao:%')).delete(synchronize_session=False)
        db.commit()
    finally:db.close()

def remoto(monkeypatch,historico=None):
    chamadas=[]
    historico=[] if historico is None else historico
    itens=[{'id':IDENT,'nome':'Bella','descricao':'Personagem do Models','classificacao':'geral','versao':1}]
    voz={'provedor':'voicestudio','conta':'voicestudio','voice_id':'voz-escolhida','ativa':True,'principal':True}
    def pedir(metodo,rota,conta=None,modelo_id=None,corpo=None):
        chamadas.append((metodo,rota,corpo))
        if rota.endswith('/pacote'):return {'modelo':{**itens[0],'persona':'Persona própria do Models',
            'vozes_por_conta':[voz]}}
        if rota=='/api/servico/contexto/montar':
            assert metodo=='POST' and corpo['dono_id']=='solo-bot:conta:'+str(conta.id)
            assert corpo['modelo_id']==modelo_id
            return {'formato':1,'contexto_id':corpo['requisicao_id'],'perfil_modelo':{},'perfil_pessoa':{'nome':'Pessoa fictícia'},
                'historico':list(historico),'blocos':[{'tipo':'persona','texto':'Persona própria do Models'},
                    {'tipo':'episodios','texto':'Gosto de chuva'}],
                'memorias_usadas':['episodio-chuva'],'estado':{'temperatura':0,'bloco':''},
                'construtivo':{'ligado':False,'modo':'automatico'},'orcamento':{'limite':8000,'usado':14}}
        if rota.endswith('/episodios'):
            return {'id':'episodio'} if metodo=='POST' else []
        if rota.endswith('/registros'):
            if metodo=='POST' and corpo['tipo']=='turno':
                historico.append({'usuario':corpo['usuario'],'texto':corpo['texto']})
            return {'id':'registro'} if metodo=='POST' else []
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


def test_deepseek_recebe_papeis_validos_em_conversa_com_historico(logado,monkeypatch):
    import httpx
    import config
    from nucleo import grok,llm_provedores
    historico=[{'usuario':'Quero lembrar do marcador azul.','texto':'Vou lembrar do marcador azul.'}]
    remoto(monkeypatch,historico)
    logado.put('/api/conta/models',json={'modelo_id':IDENT})
    corpos=[]
    class Cliente:
        def __init__(self,**k):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,url,**k):
            corpo=k['json'];corpos.append(corpo)
            if any(m['role'] not in ('system','user','assistant') for m in corpo['messages']):
                return httpx.Response(400,json={'error':{'message':'invalid role'}})
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop',
                'message':{'content':'Resposta '+str(len(corpos))}}]})
    monkeypatch.setattr(grok,'provedor_ativo',lambda:'deepseek')
    monkeypatch.setattr(config,'DEEPSEEK_API_KEY','chave-ficticia')
    monkeypatch.setattr(config,'LLM_FALLBACK',[])
    monkeypatch.setattr(llm_provedores.httpx,'Client',Cliente)
    for pergunta in ['Oi?','O que acabamos de conversar?','Continue']:
        assert isinstance(models.responder(pergunta,1),models.TextoModels)
    assert len(corpos)==3
    for i,corpo in enumerate(corpos):
        assert [m['role'] for m in corpo['messages']]==['system']+['user','assistant']*(i+1)+['user']
        assert corpo['messages'][1]['content']=='Quero lembrar do marcador azul.'
    assert corpos[-1]['messages'][-2]['content']=='Resposta 2'


def test_cumprimento_na_conversa_models_nao_abre_menu(logado,monkeypatch):
    from database import CanalVinculo
    remoto(monkeypatch)
    db=SessionLocal();db.add(CanalVinculo(conta_id=1,canal='whatsapp',origem='111'));db.commit()
    logado.put('/api/conta/models',json={'modelo_id':IDENT})
    perguntas=[]
    monkeypatch.setattr(models,'responder',lambda texto,conta_id:perguntas.append(texto) or 'Resposta Models')
    for texto in ['Oi?','Oi ?','Olá','Bom dia']:
        r=roteador.atender_texto(db,'whatsapp','111',texto)
        assert r.mensagens[0]['texto']=='Resposta Models'
        assert roteador._modo_valido(roteador.sessao_de(db,'whatsapp','111'))==roteador.MODO_BELLA
        assert models.selecionado(1)==IDENT
    assert perguntas==['Oi?','Oi ?','Olá','Bom dia']
    r=roteador.atender_texto(db,'whatsapp','111','/menu')
    assert 'Com qual sistema' in r.mensagens[0]['texto'] or r.mensagens[0]['opcoes']
    assert roteador._modo_valido(roteador.sessao_de(db,'whatsapp','111')) is None
    assert models.selecionado(1)==IDENT
    db.close()
