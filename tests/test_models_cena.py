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
        return f'Ei, {"Bella" if quem == "Kellen" else "Kellen"}, fala {contagem[quem]}'   # sempre citam a outra
    monkeypatch.setattr(grok, 'gerar', gerar)
    r = models.responder('Kellen, vem cá', 1)
    assert r.falas[0]['nome'] == 'Kellen'
    nomes = [f['nome'] for f in r.falas]
    assert nomes.count('Kellen') <= 2 and nomes.count('Bella') <= 2 and len(nomes) == 4
    # a primeira montagem de cada uma atualiza o humor; as seguintes não
    origens = [(m['modelo_id'], m.get('origem', 'usuario')) for m in montagens]
    assert origens[0] == (KELLEN, 'usuario') and (KELLEN, 'iniciativa') in origens


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
