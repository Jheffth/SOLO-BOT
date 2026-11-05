"""A referência do Models prevalece, com atualizações pela mesma bio da conta."""
import json
from database import SessionLocal,Conta,Configuracao
from nucleo import models,bella_bio as B
from test_models import remoto,IDENT

def test_bio_vinculada_le_e_edita_perfil_central(logado,monkeypatch):
    db=SessionLocal();c=db.get(Conta,1);c.admin=True
    db.add(Configuracao(chave='perfil_models:1',valor=json.dumps({'modelo_id':IDENT})));db.commit();db.close()
    p={'nome':'Autor fictício','nascimento':'1990-01-01','bio':['Profissão: Inventor'],'versao':1}
    chamadas=[]
    def pedir(metodo,rota,conta=None,modelo_id=None,corpo=None):
        assert conta.id==1 and modelo_id==IDENT and rota.endswith('/perfil-pessoa')
        chamadas.append(metodo)
        if metodo=='PUT':p.update(corpo);p['versao']+=1
        return dict(p)
    monkeypatch.setattr(models,'_requisicao',pedir)
    assert B.listar(1)==['Profissão: Inventor']
    assert B.adicionar(1,'Gostos: Música')[0]
    assert 'Gostos: Música' in p['bio'] and chamadas.count('PUT')==1
    assert B.listar(2)==[]

def test_prompt_prefere_perfil_central_do_contexto(logado,monkeypatch):
    remoto(monkeypatch);logado.put('/api/conta/models',json={'modelo_id':IDENT})
    original=models._requisicao
    def pedir(metodo,rota,*args,**kwargs):
        r=original(metodo,rota,*args,**kwargs)
        if rota=='/api/servico/contexto/montar':r['perfil_pessoa']={'nome':'ARQUITETO CENTRAL','bio':['Gostos: PERFIL CENTRAL']}
        return r
    monkeypatch.setattr(models,'_requisicao',pedir)
    from nucleo import grok
    prompts=[];monkeypatch.setattr(grok,'gerar',lambda p,t,**k:prompts.append(p) or 'Resposta')
    assert models.responder('Olá',1)=='Resposta'
    assert 'PERFIL CENTRAL' in prompts[0]


def test_legado_preserva_bio_local_quando_models_indisponivel(logado,monkeypatch):
    db=SessionLocal();c=db.get(Conta,1);c.admin=True
    db.add(Configuracao(chave='perfil_models:1',valor=json.dumps({'modelo_id':IDENT})))
    db.add(Configuracao(chave='bella_bio:1',valor=json.dumps(['Cidade: COPIA LOCAL DA CONTA'])))
    db.commit();db.close()
    def indisponivel(*a,**k):raise models.ErroModels('Serviço indisponível')
    monkeypatch.setattr(models,'_requisicao',indisponivel)
    assert 'COPIA LOCAL DA CONTA' in B.bloco_prompt(1)
