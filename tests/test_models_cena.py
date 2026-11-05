"""Cena com várias modelos: /addmodel com chegada narrada, cada uma falando por si, voz por fala."""
import pytest

from database import SessionLocal, Conta
from nucleo import models, models_cena, grok, roteador, fala

BELLA, KELLEN = 'id-bella-0001', 'id-kellen-0002'
VOZES = {BELLA: {'voice_id': 'voz-bella', 'ativa': True, 'principal': True},
         KELLEN: {'voice_id': 'voz-kellen', 'ativa': True, 'principal': True}}
NOMES = {BELLA: 'Bella', KELLEN: 'Kellen'}


@pytest.fixture(autouse=True)
def limpar():
    yield
    from database import Configuracao
    with SessionLocal() as db:
        db.query(Configuracao).filter(Configuracao.chave.like('models_selecao:%')).delete(synchronize_session=False)
        db.commit()


def ambiente(logado, monkeypatch, admin=True, cena_inicial=False):
    with SessionLocal() as db:
        conta = db.get(Conta, 1); conta.admin = admin
        from database import Configuracao
        db.merge(Configuracao(chave='models_selecao:1', valor=BELLA)); db.commit()
    estado = {'presentes': [{'modelo_id': BELLA, 'nome': 'Bella', 'anfitria': True}] +
              ([{'modelo_id': KELLEN, 'nome': 'Kellen'}] if cena_inicial else [])}
    pedidos, montagens = [], []

    def pedir(metodo, rota, conta=None, modelo_id=None, corpo=None):
        pedidos.append((metodo, rota, corpo))
        if rota.endswith('/pacote'):
            ident = rota.split('/')[-2]
            return {'modelo': {'id': ident, 'nome': NOMES[ident], 'classificacao': 'adulto', 'conteudo_adulto_habilitado': True,
                               'vozes_por_conta': [VOZES[ident]]}}
        if rota.endswith('/cena/adicionar'):
            if not conta.admin:
                raise models.ErroModels('só o Arquiteto')
            estado['presentes'].append({'modelo_id': KELLEN, 'nome': 'Kellen'})
            return {'ativa': True, 'presentes': estado['presentes'], 'limite_falas': 2}
        if rota.endswith('/cena/remover'):
            estado['presentes'] = [p for p in estado['presentes'] if p['modelo_id'] != corpo['outra_modelo_id']]
            return {'ativa': len(estado['presentes']) > 1, 'presentes': estado['presentes'],
                    'restante': estado['presentes'][0]['modelo_id'] if len(estado['presentes']) == 1 else None}
        if rota.endswith('/cena/rodada'):
            return {'ativa': True}
        if rota.endswith('/cena'):
            return {'ativa': len(estado['presentes']) > 1, 'presentes': estado['presentes'], 'limite_falas': 2}
        if rota == '/api/servico/contexto/montar':
            montagens.append(corpo)
            return {'formato': 1, 'contexto_id': corpo['requisicao_id'], 'perfil_modelo': {}, 'perfil_pessoa': {},
                    'historico': [{'usuario': 'Bella, chama a Kellen pra cá', 'texto': 'Vou ligar pra ela!'}],
                    'blocos': [{'tipo': 'cena', 'texto': 'cena'}], 'memorias_usadas': [], 'estado': {'temperatura': 0, 'bloco': ''}}
        return []
    monkeypatch.setattr(models, '_requisicao', pedir)
    return pedidos, montagens, estado


def _quem_fala(prompt):
    return 'Kellen' if prompt.startswith('Você é Kellen') else 'Bella' if prompt.startswith('Você é Bella') else 'Narrador'


def test_addmodel_narra_chegada_e_cada_uma_fala_por_si(logado, monkeypatch):
    pedidos, montagens, _ = ambiente(logado, monkeypatch)
    vistos = []

    def gerar(prompt, pergunta, **kw):
        quem = _quem_fala(prompt); vistos.append((quem, pergunta))
        return {'Narrador': 'A Bella liga para a Kellen, que toca a campainha minutos depois.',
                'Kellen': 'Kellen: Cheguei! Bella: (isso não pode aparecer)', 'Bella': 'Até que enfim, preguiçosa.'}[quem]
    monkeypatch.setattr(grok, 'gerar', gerar)
    with SessionLocal() as db:
        r = models.comando(db.get(Conta, 1), '/addmodel', 'Kellen')
    assert [f['nome'] for f in r.falas] == ['', 'Kellen', 'Bella']
    assert r.falas[0]['voz'] is None and r.falas[0]['texto'].startswith('🎬 A Bella liga')
    assert r.falas[1]['texto'] == 'Cheguei!' and r.falas[1]['voz']['voice_id'] == 'voz-kellen'
    assert 'Bella, chama a Kellen' in vistos[0][1]          # a narração usa o contexto ("chama a Kellen")
    rodada = next(c for m, rota, c in pedidos if rota.endswith('/cena/rodada'))
    assert rodada['narracao'].startswith('A Bella liga') and [f['modelo_id'] for f in rodada['falas']] == [KELLEN, BELLA]
    assert all(set(m['elenco']['presentes']) == {BELLA, KELLEN} for m in montagens)


def test_rodada_chamada_pelo_nome_e_conversa_entre_elas_com_limite(logado, monkeypatch):
    pedidos, montagens, _ = ambiente(logado, monkeypatch, cena_inicial=True)
    contagem = {'Bella': 0, 'Kellen': 0}

    def gerar(prompt, pergunta, **kw):
        quem = _quem_fala(prompt); contagem[quem] += 1
        assuntos = ['pipoca', 'filme', 'sofá', 'controle', 'janela']
        return f'Ei, {"Bella" if quem == "Kellen" else "Kellen"}, olha {assuntos[sum(contagem.values()) - 1]}'   # sempre citam a outra
    monkeypatch.setattr(grok, 'gerar', gerar)
    r = models.responder('Kellen, vem cá', 1)
    assert r.falas[0]['nome'] == 'Kellen'
    nomes = [f['nome'] for f in r.falas]
    assert nomes == ['Kellen', 'Bella']                     # uma vez cada, pela ação; citar a outra não puxa outra rodada
    # a primeira montagem de cada uma atualiza o humor; as seguintes não
    origens = [(m['modelo_id'], m.get('origem', 'usuario')) for m in montagens]
    assert origens == [(KELLEN, 'usuario'), (BELLA, 'usuario')]


def test_silencio_encerra_a_rodada(logado, monkeypatch):
    ambiente(logado, monkeypatch, cena_inicial=True)
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: 'Oi, amor.' if _quem_fala(p) == 'Bella' else '[silêncio]')
    r = models.responder('oi, gente', 1)
    assert [f['nome'] for f in r.falas] == ['Bella']


def test_uma_mensagem_e_uma_voz_por_fala(logado, monkeypatch):
    ambiente(logado, monkeypatch, cena_inicial=True)
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: 'Kellen, você viu?' if _quem_fala(p) == 'Bella' else 'Vi sim.')
    r = roteador.resposta_models(models.responder('oi, gente', 1))
    assert r.mensagens[0]['texto'].startswith('*Bella:*') and r.mensagens[0]['modelo_voz']['voice_id'] == 'voz-bella'
    assert r.mensagens[1]['modelo_voz']['voice_id'] == 'voz-kellen'
    sintetizadas = []
    monkeypatch.setattr(models, 'sintetizar', lambda texto, canal, voz: sintetizadas.append((texto, voz['voice_id'])) or {'base64': 'x', 'mime': 'audio/mpeg'})
    with SessionLocal() as db:
        conta = db.get(Conta, 1); conta.voz = 'sempre'
        fala.falar_resposta(conta, 'whatsapp', r, entrada_audio=False)
    assert [v for _, v in sintetizadas] == ['voz-bella', 'voz-kellen']
    assert sintetizadas[0][0] == 'Kellen, você viu?' and all(m.get('audio') for m in r.mensagens)


def test_so_o_arquiteto_e_sem_modelo_escolhida(logado, monkeypatch):
    ambiente(logado, monkeypatch, admin=False)
    with SessionLocal() as db:
        assert 'somente para o Arquiteto' in models.comando(db.get(Conta, 1), '/addmodel', 'Kellen')


def test_removemodel_despede_e_volta_ao_individual(logado, monkeypatch):
    pedidos, _, estado = ambiente(logado, monkeypatch, cena_inicial=True)
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: {'Narrador': 'A Kellen pega a bolsa e vai embora.',
                                                         'Kellen': 'Tchau, gente.', 'Bella': 'x'}[_quem_fala(p)])
    with SessionLocal() as db:
        r = models.comando(db.get(Conta, 1), '/removemodel', 'Kellen')
    assert [f['nome'] for f in r.falas][:2] == ['', 'Kellen'] and 'segue só com Bella' in r.falas[-1]['texto']
    assert [p['modelo_id'] for p in estado['presentes']] == [BELLA]
    assert models.selecionado(1) == BELLA


def test_a_outra_responde_ao_que_a_primeira_disse(logado, monkeypatch):
    ambiente(logado, monkeypatch, cena_inicial=True)
    perguntas = {}

    def gerar(prompt, pergunta, **kw):
        quem = _quem_fala(prompt); perguntas.setdefault(quem, pergunta)
        return 'Quero ver quem tem coragem primeiro.' if quem == 'Bella' else 'Coragem eu tenho de sobra, só falta o sofá.'
    monkeypatch.setattr(grok, 'gerar', gerar)
    r = models.responder('quem me beija primeiro?', 1)
    assert [f['nome'] for f in r.falas] == ['Bella', 'Kellen']
    assert 'Agora mesmo, Bella: Quero ver quem tem coragem primeiro.' in perguntas['Kellen']
    assert 'não responda nem repita' in perguntas['Kellen']


def test_eco_da_outra_nao_vira_mensagem(logado, monkeypatch):
    ambiente(logado, monkeypatch, cena_inicial=True)
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: 'Cada uma no seu tempo, sem leilão nenhum aqui.' if _quem_fala(p) == 'Bella'
                        else 'Cada uma no seu tempo, sem leilão nenhum, viu?')
    r = models.responder('oi, gente', 1)
    assert [f['nome'] for f in r.falas] == ['Bella']


def test_whatsapp_primeira_fala_na_hora_e_a_reacao_chega_depois(logado, monkeypatch):
    pedidos, _, _ = ambiente(logado, monkeypatch, cena_inicial=True)
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: 'Kellen, você viu isso?' if _quem_fala(p) == 'Bella' else 'Vi e não acreditei.')
    tarefas, entregues = [], []
    monkeypatch.setattr(models_cena, '_em_segundo_plano', lambda alvo, *a: tarefas.append((alvo, a)))
    from canais import entrega
    monkeypatch.setattr(entrega, 'entregar', lambda db, canal, origem, r, **kw: entregues.append((canal, r.mensagens[0]['texto'])))
    from database import CanalVinculo
    with SessionLocal() as db:
        if not db.query(CanalVinculo).filter_by(conta_id=1, canal='whatsapp').first():
            db.add(CanalVinculo(conta_id=1, canal='whatsapp', origem='5561999999999@s.whatsapp.net')); db.commit()
    r = models.responder('oi, gente', 1, canal='whatsapp')
    assert [f['nome'] for f in r.falas] == ['Bella']                 # a resposta não espera a Kellen
    assert not any(rota.endswith('/cena/rodada') for _, rota, _ in pedidos)
    alvo, args = tarefas[0]; alvo(*args)
    assert entregues == [('whatsapp', '*Kellen:* Vi e não acreditei.')]
    rodada = next(c for _, rota, c in pedidos if rota.endswith('/cena/rodada'))
    assert [f['texto'] for f in rodada['falas']] == ['Kellen, você viu isso?', 'Vi e não acreditei.']
    assert rodada['usuario'] == 'oi, gente'


def test_mensagem_nova_interrompe_a_rodada_anterior(logado, monkeypatch):
    ambiente(logado, monkeypatch, cena_inicial=True)
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: 'Kellen, e aí?' if _quem_fala(p) == 'Bella' else 'Tô aqui.')
    tarefas = []
    monkeypatch.setattr(models_cena, '_em_segundo_plano', lambda alvo, *a: tarefas.append((alvo, a)))
    entregues = []
    from canais import entrega
    monkeypatch.setattr(entrega, 'entregar', lambda *a, **kw: entregues.append(a))
    models.responder('primeira', 1, canal='whatsapp')
    models.responder('segunda', 1, canal='whatsapp')
    alvo, args = tarefas[0]; alvo(*args)
    assert not entregues


def test_primeiro_nome_chama_e_fala_da_outra_nao_vaza():
    assert models_cena._citado('Kellen Iara', 'Fala pra mim Kellen, como está?')
    assert not models_cena._citado('Kellen Iara', 'Fala pra mim, Bella')
    texto = '[Fala de Kellen Iara]\n*me ajoelho devagar* Assim? Bella: Deitada eu fico.'
    assert models_cena._limpar(texto, 'Kellen Iara', ['Bella']) == '*me ajoelho devagar* Assim?'
    assert models_cena._limpar('Kellen: oi. Bella Costa: tchau', 'Kellen Iara', ['Bella Costa']) == 'oi.'


def test_quem_foi_chamada_pelo_primeiro_nome_fala_primeiro(logado, monkeypatch):
    ambiente(logado, monkeypatch, cena_inicial=True)
    vistos = []
    monkeypatch.setattr(grok, 'gerar', lambda p, q, **kw: vistos.append(p.split('.')[0]) or 'Uma ação nova e diferente desta vez.' + str(len(vistos)))
    monkeypatch.setattr(models_cena, 'cena_ativa', lambda conta, ident: {'ativa': True, 'limite_falas': 2, 'presentes': [
        {'modelo_id': BELLA, 'nome': 'Bella', 'anfitria': True}, {'modelo_id': KELLEN, 'nome': 'Kellen Iara'}]})
    r = models.responder('Fala pra mim Kellen, o que você está fazendo?', 1)
    assert r.falas[0]['voz']['voice_id'] == 'voz-kellen'


def test_na_cena_quem_desconversa_refaz_obedecendo(logado, monkeypatch):
    ambiente(logado, monkeypatch, cena_inicial=True)
    prompts = []

    def gerar(prompt, pergunta, **kw):
        prompts.append((_quem_fala(prompt), prompt))
        if _quem_fala(prompt) == 'Kellen':
            if '[CORREÇÃO]' in prompt:
                return '*passo a língua devagar* Ela está quente e treme a cada volta que eu dou.'
            return 'Arquiteto, eu não falo com plateia. Quem quiser saber, vem conferir.'
        return '*seguro o lençol e arqueio as costas* Não para, Kellen.'
    monkeypatch.setattr(grok, 'gerar', gerar)
    r = models.responder('Fala pra mim Kellen, descreve o que você está fazendo', 1)
    assert r.falas[0]['texto'].startswith('*passo a língua')
    assert 'O Arquiteto dirige esta cena' in prompts[0][1]
    assert sum(1 for q, p in prompts if q == 'Kellen') == 2       # uma tentativa a mais, só para quem desconversou


def test_esquiva_reconhecida():
    assert models_cena._desobedeceu('Não vou ficar aqui ditando manual pra plateia.')
    assert models_cena._desobedeceu('Quer saber? Então para de perguntar e vem conferir.')
    assert not models_cena._desobedeceu('*me ajoelho* Assim, devagar, do jeito que você mandou.')


def test_removermodel_pelo_primeiro_nome_e_com_apelido_do_comando(logado, monkeypatch):
    pedidos, _, estado = ambiente(logado, monkeypatch, cena_inicial=True)
    estado['presentes'][1]['nome'] = 'Kellen Iara'
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: 'Ela se despede e sai.' if _quem_fala(p) == 'Narrador' else 'Tchau.')
    with SessionLocal() as db:
        r = roteador.resposta_models(models.comando(db.get(Conta, 1), roteador.APELIDOS_CENA['/removermodel'], 'Kellen'))
    assert [p['modelo_id'] for p in estado['presentes']] == [BELLA]
    assert any('segue só com Bella' in m['texto'] for m in r.mensagens)


def test_portal_marca_e_desmarca_modelos_da_cena(logado, monkeypatch):
    pedidos, _, estado = ambiente(logado, monkeypatch)
    r = logado.put('/api/conta/models/cena', json={'modelos': [BELLA, KELLEN]})
    assert r.status_code == 200 and r.json() == {'modelo_id': BELLA, 'presentes': [BELLA, KELLEN]}
    adicionar = next(c for m, rota, c in pedidos if rota.endswith('/cena/adicionar'))
    assert adicionar == {'outra_modelo_id': KELLEN}
    assert logado.get('/api/conta/models').json()['presentes'] == [BELLA, KELLEN]
    r = logado.put('/api/conta/models/cena', json={'modelos': [BELLA]})      # desmarcou a Kellen: ela sai
    assert r.status_code == 200 and r.json()['presentes'] == []
    assert [p['modelo_id'] for p in estado['presentes']] == [BELLA]
    assert models.selecionado(1) == BELLA


def test_portal_nao_junta_as_duas_bellas_nem_libera_cena_para_quem_nao_e_arquiteto(logado, monkeypatch):
    ambiente(logado, monkeypatch)
    monkeypatch.setitem(NOMES, KELLEN, 'Bella Costa')
    r = logado.put('/api/conta/models/cena', json={'modelos': [BELLA, KELLEN]})
    assert r.status_code == 422 and 'duas Bellas' in r.json()['detail']
    monkeypatch.setitem(NOMES, KELLEN, 'Kellen')
    with SessionLocal() as db:
        db.get(Conta, 1).admin = False; db.commit()
    r = logado.put('/api/conta/models/cena', json={'modelos': [BELLA, KELLEN]})
    assert r.status_code == 422 and 'somente para o Arquiteto' in r.json()['detail']


def test_removermodel_digitado_no_chat_funciona(logado, monkeypatch):
    _, _, estado = ambiente(logado, monkeypatch, cena_inicial=True)
    estado['presentes'][1]['nome'] = 'Kellen Iara'
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: 'Ela sai.' if _quem_fala(p) == 'Narrador' else 'Tchau.')
    from database import CanalVinculo
    with SessionLocal() as db:
        if not db.query(CanalVinculo).filter_by(conta_id=1, canal='telegram').first():
            db.add(CanalVinculo(conta_id=1, canal='telegram', origem='99887766')); db.commit()
        origem = db.query(CanalVinculo).filter_by(conta_id=1, canal='telegram').first().origem
        r = roteador.atender_texto(db, 'telegram', origem, '/removermodel Kellen Iara')
    assert [p['modelo_id'] for p in estado['presentes']] == [BELLA]
    assert any('segue só com Bella' in m['texto'] for m in r.mensagens)
