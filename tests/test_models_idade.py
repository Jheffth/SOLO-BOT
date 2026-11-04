"""Idade vem da ficha atual, mesmo quando a IA ou o histórico repetem um erro."""
import pytest

from nucleo import models, grok
from test_models import remoto, IDENT


def ambiente(logado, monkeypatch):
    remoto(monkeypatch)
    logado.put('/api/conta/models', json={'modelo_id': IDENT})
    requisicao = models._requisicao
    ficha = {'identidade': {'nome': 'Bella', 'idade': 19, 'data_nascimento': '2007-03-25'}}
    gravacoes = []
    prompts = []

    def pedir(metodo, rota, conta=None, modelo_id=None, corpo=None):
        if metodo == 'POST' and rota.endswith('/registros'):
            gravacoes.append(corpo)
        resposta = requisicao(metodo, rota, conta, modelo_id, corpo)
        if rota.endswith('/pacote'):
            resposta['modelo'].update(idade=26, perfil_modelo=ficha)
        if rota.endswith('/contexto'):
            resposta['historico'] = [{'usuario': 'Sua idade?', 'texto': 'Tenho 26 anos.'}]
        return resposta

    monkeypatch.setattr(models, '_requisicao', pedir)
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: prompts.append(p) or 'Tenho 26 anos.')
    return ficha, gravacoes, prompts


@pytest.mark.parametrize('pergunta', [
    'Amor, qual é sua idade ?', 'bella qual é a sua idade?', 'Quantos anos você tem?',
    'Meu amor, você tem quantos anos?', 'Que idade você tem?', 'Qual sua idade?',
])
def test_idade_responde_cadastro_sem_repetir_erro_da_ia(logado, monkeypatch, pergunta):
    ficha, gravacoes, prompts = ambiente(logado, monkeypatch)
    resposta = models.responder(pergunta, 1)
    assert resposta == 'Tenho 19 anos.'
    assert resposta.voz_models['voice_id'] == 'voz-escolhida'
    assert not prompts
    assert gravacoes[-1]['texto'] == resposta and gravacoes[-1]['usuario'] == pergunta
    ficha['identidade']['idade'] = 20
    assert models.responder(pergunta, 1) == 'Tenho 20 anos.'


@pytest.mark.parametrize('pergunta', [
    'Qual a idade do Arquiteto?', 'Qual é sua idade e o que gosta de fazer?',
    'Quantos anos sua amiga tem?', 'Escreva uma história sobre idade.',
])
def test_outros_pedidos_continuam_na_conversa(logado, monkeypatch, pergunta):
    _, _, prompts = ambiente(logado, monkeypatch)
    models.responder(pergunta, 1)
    assert len(prompts) == 1
    assert 'FICHA FACTUAL ATUAL DA PERSONAGEM' in prompts[0]
    assert '"idade": 19' in prompts[0]
    assert prompts[0].index('FICHA FACTUAL ATUAL DA PERSONAGEM') > prompts[0].index('Memórias desta relação:')


def test_idade_desconhecida_nao_usa_indice_antigo(logado, monkeypatch):
    ficha, _, prompts = ambiente(logado, monkeypatch)
    ficha['identidade']['idade'] = None
    models.responder('Qual sua idade?', 1)
    assert prompts
