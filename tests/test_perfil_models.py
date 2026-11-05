"""Perfil da pessoa é comum; as experiências das modelos e de outros donos não são."""
from database import SessionLocal, Conta, Configuracao, CanalVinculo, BellaMemoria, BellaArquivo
from nucleo import bella_bio as B, models, grok, roteador


def ambiente(logado, monkeypatch):
    db=SessionLocal()
    conta=db.get(Conta,1);conta.admin=True
    db.add(Conta(id=2,nome='Outra pessoa',usuario='outra',senha_hash='teste'))
    db.add(Configuracao(chave='models_selecao:1',valor='modelo-a'))
    db.commit();db.close()
    B.definir(1,'Cidade: CIDADE DO DONO\nEstado civil: Casado\nNascimento: 01/01/1990')
    B.definir(2,'Cidade: SEGREDO DE OUTRA CONTA')
    chamadas=[];prompts=[]
    def pedir(metodo,rota,conta=None,modelo_id=None,corpo=None):
        chamadas.append((metodo,rota,corpo))
        if rota.endswith('/pacote'):
            modelo_id=rota.split('/')[-2]
            return {'modelo':{'id':modelo_id,'nome':modelo_id,'persona':'PERSONA '+modelo_id,
                'classificacao':'geral','vozes_por_conta':[{'ativa':True,'principal':True,'provedor':'voicestudio'}]}}
        if rota=='/api/servico/contexto/montar':
            return {'formato':1,'perfil_modelo':{},'perfil_pessoa':B.perfil_compartilhado(conta),
                'blocos':[{'tipo':'episodios','texto':'MEMORIA PRIVADA '+modelo_id}],
                'historico':[],'memorias_usadas':['episodio-'+modelo_id],
                'estado':{'temperatura':0,'bloco':''},'construtivo':{'ligado':False,'modo':'automatico'},
                'orcamento':{'limite':8000,'usado':50}}
        if metodo=='POST' and rota.endswith('/registros'):return {'id':'registro-novo'}
        raise AssertionError(rota)
    monkeypatch.setattr(models,'_requisicao',pedir)
    monkeypatch.setattr(grok,'gerar',lambda p,t,**k:prompts.append(p) or 'Resposta fictícia')
    return chamadas,prompts


def test_perfil_em_todas_modelos_atualizado_sem_copiar_memorias(logado,monkeypatch):
    chamadas,prompts=ambiente(logado,monkeypatch)
    assert models.responder('Olá',1)=='Resposta fictícia'
    assert 'CIDADE DO DONO' in prompts[-1] and 'Arquiteto' in prompts[-1] and 'Jefferson Costa' in prompts[-1]
    assert 'SEGREDO DE OUTRA CONTA' not in prompts[-1]
    assert B.POSTURA_CASADO.strip() not in prompts[-1]
    assert 'MEMORIA PRIVADA modelo-a' in prompts[-1]
    db=SessionLocal();cfg=db.get(Configuracao,'models_selecao:1');cfg.valor='modelo-b';db.commit();db.close()
    B.adicionar(1,'Cidade: PERFIL ATUALIZADO')
    assert models.responder('Olá de novo',1)=='Resposta fictícia'
    assert 'PERFIL ATUALIZADO' in prompts[-1] and 'CIDADE DO DONO' not in prompts[-1]
    assert 'MEMORIA PRIVADA modelo-b' in prompts[-1] and 'MEMORIA PRIVADA modelo-a' not in prompts[-1]
    gravacoes=[c for c in chamadas if c[0]=='POST' and c[1].endswith('/registros')]
    assert len(gravacoes)==2 and all(c[2]['tipo']=='turno' for c in gravacoes)
    assert '/modelo-a/' in gravacoes[0][1] and '/modelo-b/' in gravacoes[1][1]
    assert all('bio' not in c[2] for c in gravacoes)
    db=SessionLocal();assert db.query(BellaMemoria).count()==0 and db.query(BellaArquivo).count()==0;db.close()


def test_perfil_sem_bio_identifica_somente_a_propria_pessoa(logado):
    db=SessionLocal();conta=db.get(Conta,1)
    assert B.perfil_compartilhado(conta)=={'nome':'Jefferson Costa','bio':[]}
    db.close()


def test_editar_perfil_com_models_ativo_sem_mudar_memorias(logado,monkeypatch):
    _,prompts=ambiente(logado,monkeypatch)
    db=SessionLocal();db.add(CanalVinculo(conta_id=1,canal='whatsapp',origem='perfil-teste'));db.commit()
    for cmd in ('/perfil','/bio'):
        r=roteador.atender_texto(db,'whatsapp','perfil-teste',cmd)
        assert 'CIDADE DO DONO' in r.mensagens[0]['texto']
    r=roteador.atender_texto(db,'whatsapp','perfil-teste','/perfil add Hobby: Astronomia')
    assert 'Guardei' in r.mensagens[0]['texto'] and 'Hobby: Astronomia' in B.listar(1)
    assert models.selecionado(1)=='modelo-a' and not prompts
    assert db.query(BellaMemoria).count()==0 and db.query(BellaArquivo).count()==0
    db.close()
