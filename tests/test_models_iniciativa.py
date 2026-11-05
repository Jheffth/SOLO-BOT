"""Iniciativa da modelo ativa usa só seu mundo e exige consentimento nas duas pontas."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

import database
from database import SessionLocal, Conta, CanalVinculo, Atividade
from nucleo import models, bella_iniciativa as iniciativa, bella_conversa, bella_historia, bella_estado, bella_galeria, grok, roteador
from test_models import remoto, IDENT


def ambiente(logado, monkeypatch, ativa=True, ligada=True, bom_dia=True):
    remoto(monkeypatch)
    logado.put('/api/conta/models', json={'modelo_id': IDENT})
    with SessionLocal() as db:
        conta = db.get(Conta, 1)
        conta.admin = True
        conta.avisos_voz = 'sempre'
        db.add(CanalVinculo(conta_id=1, canal='whatsapp', origem='iniciativa-models', avisos=True))
        db.commit()
    iniciativa.configurar(1, ligada=ligada, bom_dia=bom_dia)
    original = models._requisicao
    pedidos = []
    capturas = []
    entregas = []

    def pedir(metodo, rota, conta=None, modelo_id=None, corpo=None):
        pedidos.append((metodo, rota, corpo))
        r = original(metodo, rota, conta, modelo_id, corpo)
        if rota.endswith('/pacote'):
            r['modelo']['iniciativa'] = {'ativa': ativa}
            r['modelo']['persona'] = 'PERSONA BRUTA QUE NÃO PODE SER LIDA'
        if rota == '/api/servico/contexto/montar':
            r['perfil_modelo'] = {'identidade': {'nome': 'Aurora', 'idade': 28}, 'personalidade': {'gostos': 'astronomia'}}
            r['blocos'] = [{'tipo': 'persona', 'texto': 'PERSONA AUTORIZADA DA MODELO ATIVA'},
                {'tipo': 'datas', 'texto': 'Hoje é uma data importante no cartão autorizado da pessoa.'}]
        return r

    def gerar(sistema, texto, **kw):
        capturas.append((sistema, texto, kw))
        return 'Pensei em você. Como está o trabalho hoje?'

    def proibido(*a, **kw): raise AssertionError('Leitura ou geração legada na iniciativa Models')
    monkeypatch.setattr(models, '_requisicao', pedir)
    monkeypatch.setattr(grok, 'gerar', gerar)
    for alvo, nome in [(iniciativa, '_gerar'), (iniciativa, 'escolher_tipo'),
        (iniciativa, 'buscar_noticia'), (iniciativa, 'intensidade_bom_dia'),
        (bella_conversa, '_lembrar'), (bella_conversa, 'prompt'),
        (bella_conversa, '_historico'), (bella_historia, 'gravar'),
        (bella_estado, 'situacao'), (bella_galeria, 'escolher')]:
        monkeypatch.setattr(alvo, nome, proibido)
    monkeypatch.setattr(iniciativa, 'PROVEDORES_MIDIA', [proibido])
    monkeypatch.setattr('canais.entrega.entregar', lambda db, canal, origem, resposta, **kw:
        entregas.append((canal, origem, resposta, kw)))
    return pedidos, capturas, entregas


@pytest.mark.parametrize('tipo', [None, 'bom_dia', 'video', 'noticia'])
def test_iniciativa_ativa_tem_contexto_voz_e_origem_models_sem_legacy(logado, monkeypatch, tipo):
    pedidos, capturas, entregas = ambiente(logado, monkeypatch)
    with SessionLocal() as db:
        d = iniciativa.carregar(1)
        d['recentes'] = ['Texto reservado ao legado, que não entra na conversa Models.']
        texto = iniciativa.enviar_agora(db, db.get(Conta, 1), d, tipo)
        assert texto == 'Pensei em você. Como está o trabalho hoje?'
        assert d['recentes'] == ['Texto reservado ao legado, que não entra na conversa Models.']
    assert len(entregas) == 1 and len(capturas) == 1
    m = entregas[0][2].mensagens[0]
    assert m['modelo_voz']['voice_id'] == 'voz-escolhida' and 'midia' not in m
    assert entregas[0][3]['falar'] is True
    assert 'PERSONA AUTORIZADA DA MODELO ATIVA' in capturas[0][0]
    assert 'PERSONA BRUTA' not in capturas[0][0]
    assert 'Texto reservado ao legado' not in capturas[0][0] + capturas[0][1]
    montagem = next(p for p in pedidos if p[1] == '/api/servico/contexto/montar')
    turno = next(p for p in pedidos if p[1].endswith('/registros'))
    assert montagem[2]['origem'] == turno[2]['origem'] == 'iniciativa'
    assert turno[2]['usuario'] == '[Iniciativa da personagem]'
    assert turno[2]['texto'] == texto and turno[2]['memorias_usadas'] == ['episodio-chuva']
    assert turno[2]['contexto_id'] == montagem[2]['requisicao_id']
    assert 'como foi seu dia' not in montagem[2]['mensagem'].casefold()
    assert 'sem uma deixa da pessoa' in capturas[0][0]


@pytest.mark.parametrize('ativa,ligada,bom_dia,tipo', [
    (False, True, True, None), (False, True, True, 'bom_dia'),
    (True, False, True, None), (True, True, False, 'bom_dia'),
])
def test_sem_ativa_ou_optin_nao_envia_nem_recua_ao_legado(logado, monkeypatch, ativa, ligada, bom_dia, tipo):
    pedidos, capturas, entregas = ambiente(logado, monkeypatch, ativa, ligada, bom_dia)
    with SessionLocal() as db:
        assert iniciativa.enviar_agora(db, db.get(Conta, 1), iniciativa.carregar(1), tipo) is None
    assert not entregas and not capturas
    assert not any(p[1] == '/api/servico/contexto/montar' or p[1].endswith('/registros') for p in pedidos)


def test_falha_de_selecao_nao_gera_com_persona_legada(logado, monkeypatch):
    _, capturas, entregas = ambiente(logado, monkeypatch)
    def indisponivel(*a): raise models.ErroModels('Sem acesso à seleção')
    monkeypatch.setattr(models, 'selecionado', indisponivel)
    with SessionLocal() as db:
        assert iniciativa.enviar_agora(db, db.get(Conta, 1), iniciativa.carregar(1)) is None
    assert not entregas and not capturas


def test_bom_dia_tem_optin_proprio_sem_exigir_iniciativa_regular(logado, monkeypatch):
    _, _, entregas = ambiente(logado, monkeypatch, ativa=True, ligada=False, bom_dia=True)
    with SessionLocal() as db:
        assert iniciativa.enviar_agora(db, db.get(Conta, 1), iniciativa.carregar(1), 'bom_dia')
    assert len(entregas) == 1


def test_modelo_ativa_usa_metadados_de_conversa_sem_ler_estado_legado(logado, monkeypatch):
    ambiente(logado, monkeypatch)
    agora = datetime(2026, 11, 4, 15)
    with SessionLocal() as db:
        db.add(Atividade(conta_id=1, canal='whatsapp', app=None, tipo='bella', resumo='conversa',
            criado_em=agora - timedelta(minutes=2)))
        db.commit()
    def verificar(conn, cursor, sql, parametros, contexto, multiplos):
        assert 'bella_estados' not in sql.casefold()
    event.listen(database.engine, 'before_cursor_execute', verificar)
    try:
        assert iniciativa._em_conversa(1, agora)
        assert iniciativa._respondeu_depois(1, {'ultimo_envio': (agora - timedelta(hours=1)).isoformat()})
    finally:event.remove(database.engine, 'before_cursor_execute', verificar)


def test_comando_optin_global_continua_disponivel_com_models_selecionado(logado, monkeypatch):
    ambiente(logado, monkeypatch, ligada=False)
    with SessionLocal() as db:
        r = roteador.atender_texto(db, 'whatsapp', 'iniciativa-models', '/iniciativa ligar')
        assert 'vou puxar assunto' in r.mensagens[0]['texto']
    assert iniciativa.carregar(1)['ligada']
