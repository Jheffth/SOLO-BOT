"""A IA consulta a ficha completa e responde livremente em todas as mensagens."""
import pytest

from nucleo import models, grok
from test_models import remoto, IDENT


def ambiente(logado, monkeypatch):
    remoto(monkeypatch)
    logado.put('/api/conta/models', json={'modelo_id': IDENT})
    requisicao = models._requisicao
    ficha = {'data_referencia': '2026-11-04',
        'identidade': {'nome': 'Bella', 'idade': 19, 'data_nascimento': '2007-03-25',
                       'local_nascimento': 'Cidade fictícia', 'idiomas': ['português', 'italiano']},
        'aparencia': {'olhos': 'verdes', 'cabelo': 'castanho'},
        'personalidade': {'gostos': 'astronomia', 'medos': 'tempestades'}}
    gravacoes = []
    prompts = []

    def pedir(metodo, rota, conta=None, modelo_id=None, corpo=None):
        if metodo == 'POST' and rota.endswith('/registros'):
            gravacoes.append(corpo)
        resposta = requisicao(metodo, rota, conta, modelo_id, corpo)
        if rota.endswith('/pacote'):
            resposta['modelo'].update(idade=26, perfil_modelo=ficha)
        if rota=='/api/servico/contexto/montar':
            resposta['historico'] = [{'usuario': 'Sua idade?', 'texto': 'Tenho 26 anos.'}]
            resposta['perfil_modelo'] = ficha
        return resposta

    monkeypatch.setattr(models, '_requisicao', pedir)
    def gerar(p, t, **kw):
        prompts.append({'instrucao': p, 'pergunta': t, **kw})
        return 'Uma resposta livre da IA, com a personalidade e o contexto desta conversa.'
    monkeypatch.setattr(grok, 'gerar', gerar)
    return ficha, gravacoes, prompts


@pytest.mark.parametrize('pergunta', [
    'Amor, qual é sua idade ?', 'bella qual é a sua idade?', 'Quantos anos você tem?',
    'Meu amor, você tem quantos anos?', 'Que idade você tem?', 'Qual sua idade?',
])
def test_idade_e_respondida_pela_ia_com_ficha_atual_e_historico(logado, monkeypatch, pergunta):
    ficha, gravacoes, prompts = ambiente(logado, monkeypatch)
    resposta = models.responder(pergunta, 1)
    assert resposta == 'Uma resposta livre da IA, com a personalidade e o contexto desta conversa.'
    assert resposta.voz_models['voice_id'] == 'voz-escolhida'
    assert len(prompts) == 1
    assert '"idade": 19' in prompts[-1]['pergunta']
    assert '2007-03-25' in prompts[-1]['pergunta']
    assert prompts[-1]['historico'] == [('user', 'Sua idade?'), ('assistant', 'Tenho 26 anos.')]
    assert gravacoes[-1]['texto'] == resposta and gravacoes[-1]['usuario'] == pergunta
    ficha['identidade']['idade'] = 20
    models.responder(pergunta, 1)
    assert '"idade": 20' in prompts[-1]['pergunta']
    assert '"idade": 19' not in prompts[-1]['pergunta']


@pytest.mark.parametrize('pergunta', [
    'Qual a idade do Arquiteto?', 'Qual é sua idade e o que gosta de fazer?',
    'Quantos anos sua amiga tem?', 'Escreva uma história sobre idade.',
    'Onde você nasceu?', 'Como são seus olhos?', 'O que gosta de fazer?',
    'Que idiomas fala?', 'Do que você tem medo?', 'Oi, como você está?',
])
def test_outros_pedidos_continuam_na_conversa(logado, monkeypatch, pergunta):
    ficha, gravacoes, prompts = ambiente(logado, monkeypatch)
    resposta = models.responder(pergunta, 1)
    assert len(prompts) == 1
    p = prompts[0]
    assert 'FICHA FACTUAL ATUAL DA PERSONAGEM' in p['instrucao']
    assert p['instrucao'].index('FICHA FACTUAL ATUAL DA PERSONAGEM') > p['instrucao'].index('Contexto autorizado desta relação')
    import json
    # A ficha completa vai uma vez no início; depois do histórico, só o lembrete curto da identidade (custo menor).
    assert json.dumps(ficha, ensure_ascii=False) in p['instrucao']
    assert json.dumps(ficha, ensure_ascii=False) not in p['pergunta']
    assert '"idade": 19' in p['pergunta'] and 'FATOS ATUAIS DA PERSONAGEM' in p['pergunta']
    assert 'Antes de elaborar cada resposta' in p['instrucao']
    assert 'Responda livremente' in p['instrucao']
    assert p['pergunta'].startswith(pergunta+'\n\n')
    assert gravacoes[-1]['usuario'] == pergunta
    assert gravacoes[-1]['texto'] == resposta
    assert 'CONTEXTO INTERNO' not in str(gravacoes)


def test_idade_desconhecida_nao_usa_indice_antigo(logado, monkeypatch):
    ficha, _, prompts = ambiente(logado, monkeypatch)
    ficha['identidade']['idade'] = None
    models.responder('Qual sua idade?', 1)
    assert '"idade": null' in prompts[0]['pergunta']
    assert 'Dados ausentes não foram informados: não os invente.' in prompts[0]['instrucao']
