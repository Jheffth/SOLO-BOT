"""O Bot encaminha contexto e memória ao Models sem reconstruir o mundo localmente."""
from uuid import UUID

from database import SessionLocal, Conta, CanalVinculo, BellaArquivo, BellaMemoria
from nucleo import models, grok, roteador
from test_models import remoto, IDENT


def ambiente(logado, monkeypatch, admin=False):
    _, chamadas, _ = remoto(monkeypatch)
    logado.put('/api/conta/models', json={'modelo_id': IDENT})
    with SessionLocal() as db:
        conta = db.get(Conta, 1)
        conta.admin = admin
        db.commit()
    original = models._requisicao
    estado = {'ligado': False, 'modo': 'automatico'}
    episodios = [{'id': 'episodio-ficticio', 'titulo': 'Noite de chuva', 'tipo': 'narrador'}]
    pedidos = []

    def pedir(metodo, rota, conta=None, modelo_id=None, corpo=None):
        pedidos.append((metodo, rota, corpo))
        if rota.endswith('/construtivo'):
            if metodo == 'PUT': estado.update(corpo)
            return dict(estado)
        if rota.endswith('/mente/estado'):
            return {'bloco': 'Saudade moderada; fala carinhosa e curiosa.', 'temperatura': (corpo or {}).get('temperatura', 0),
                'emocoes': {'saudade': 40}, 'medidores': {'confianca': 70}}
        if rota.endswith('/episodios'):
            return {'id': 'novo-episodio', 'titulo': corpo['titulo']} if metodo == 'POST' else list(episodios)
        if '/episodios/' in rota and metodo == 'DELETE': return {'ok': True}
        return original(metodo, rota, conta, modelo_id, corpo)

    monkeypatch.setattr(models, '_requisicao', pedir)
    return pedidos, estado


def test_busca_contexto_autorizado_e_registra_apenas_ids_utilizados(logado, monkeypatch):
    pedidos, _ = ambiente(logado, monkeypatch)
    capturas = []
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: capturas.append((p, t, kw)) or 'Resposta livre.')
    assert models.responder('E a noite de chuva?', 1) == 'Resposta livre.'
    montagem = next(v for v in pedidos if v[1] == '/api/servico/contexto/montar')
    assert montagem[0] == 'POST'
    assert montagem[2]['dono_id'] == 'solo-bot:conta:1' and montagem[2]['modelo_id'] == IDENT
    assert montagem[2]['mensagem'] == 'E a noite de chuva?'
    assert montagem[2]['elenco'] == {'presentes': [IDENT], 'mencionados': []}
    UUID(montagem[2]['requisicao_id'])
    turno = next(v[2] for v in pedidos if v[1].endswith('/registros'))
    assert turno['memorias_usadas'] == ['episodio-chuva']
    assert turno['contexto_id'] == montagem[2]['requisicao_id']
    assert turno['usuario'] == 'E a noite de chuva?' and turno['texto'] == 'Resposta livre.'
    assert not any(v[1].endswith('/contexto') or v[1].endswith('/sinais') for v in pedidos)
    with SessionLocal() as db:
        assert db.query(BellaArquivo).count() == 0 and db.query(BellaMemoria).count() == 0


def test_contexto_invalido_nao_cai_em_memorias_antigas(logado, monkeypatch):
    ambiente(logado, monkeypatch)
    original = models._requisicao
    def pedir(metodo, rota, *args, **kw):
        if rota == '/api/servico/contexto/montar': return {'formato': 1, 'memorias': [{'texto': 'Não usar'}]}
        assert not rota.endswith('/contexto')
        return original(metodo, rota, *args, **kw)
    monkeypatch.setattr(models, '_requisicao', pedir)
    monkeypatch.setattr(grok, 'gerar', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('IA não deveria ser chamada')))
    assert 'contexto válido' in models.responder('Oi', 1)


def test_pacote_bruto_nao_contorna_filtro_do_montador(logado, monkeypatch):
    ambiente(logado, monkeypatch)
    original = models._requisicao
    def pedir(metodo, rota, *args, **kw):
        r = original(metodo, rota, *args, **kw)
        if rota.endswith('/pacote'):
            r['modelo'].update(persona='DADO BRUTO NÃO AUTORIZADO', historia='LORE BRUTA NÃO AUTORIZADA',
                perfil_modelo={'identidade': {'idade': 99}})
        if rota == '/api/servico/contexto/montar':
            r['perfil_modelo'] = {'identidade': {'idade': 19}}
        return r
    monkeypatch.setattr(models, '_requisicao', pedir)
    capturas = []
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: capturas.append(p+t) or 'Resposta livre.')
    models.responder('Oi', 1)
    assert 'DADO BRUTO NÃO AUTORIZADO' not in capturas[0] and 'LORE BRUTA NÃO AUTORIZADA' not in capturas[0]
    assert '"idade": 19' in capturas[0] and '"idade": 99' not in capturas[0]


def test_construtivo_comeca_desligado_e_so_arquiteto_altera(logado, monkeypatch):
    pedidos, estado = ambiente(logado, monkeypatch)
    conta = type('C', (), {'id': 1, 'admin': False})()
    assert 'somente para o Arquiteto' in models.comando(conta, '/construtivo', 'ligar')
    assert not any(v[1].endswith('/construtivo') for v in pedidos)
    conta.admin = True
    assert 'desligado' in models.comando(conta, '/construtivo', '')
    assert 'ligado' in models.comando(conta, '/construtivo', 'ligar')
    assert estado == {'ligado': True, 'modo': 'automatico'}
    assert 'aguardam sua aprovação' in models.comando(conta, '/construtivo', 'aprovacao')
    assert estado['modo'] == 'aprovacao'
    assert 'desligado' in models.comando(conta, '/construtivo', 'desligar')


def test_narrador_segredo_encaminha_fonte_original_sem_ia_local(logado, monkeypatch):
    pedidos, _ = ambiente(logado, monkeypatch, admin=True)
    monkeypatch.setattr(grok, 'gerar', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Consolidação pertence ao Models')))
    conta = type('C', (), {'id': 1, 'admin': True})()
    assert 'Descoberta' in models.comando(conta, '/narrador', 'segredo Descoberta: Cinco dias depois ela recebeu uma notícia.')
    corpo = next(v[2] for v in pedidos if v[0] == 'POST' and v[1].endswith('/episodios'))
    assert corpo['tipo'] == 'narrador' and corpo['segredo'] is True
    assert corpo['texto'] == 'Cinco dias depois ela recebeu uma notícia.'
    UUID(corpo['requisicao_id'])


def test_eternizar_envia_conversa_para_estruturar_no_models(logado, monkeypatch):
    pedidos, _ = ambiente(logado, monkeypatch)
    original = models._requisicao
    def pedir(metodo, rota, *args, **kw):
        r = original(metodo, rota, *args, **kw)
        if rota == '/api/servico/contexto/montar':
            r['historico'] = [{'usuario': 'Primeira fala', 'texto': 'Primeira resposta'},
                             {'usuario': 'Segunda fala', 'texto': 'Segunda resposta'}]
        return r
    monkeypatch.setattr(models, '_requisicao', pedir)
    monkeypatch.setattr(grok, 'gerar', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Não resumir no Bot')))
    conta = type('C', (), {'id': 1, 'admin': False})()
    assert 'Conversa boa' in models.comando(conta, '/eternizar', 'Conversa boa')
    corpo = next(v[2] for v in pedidos if v[0] == 'POST' and v[1].endswith('/episodios'))
    assert corpo['tipo'] == 'eternizar' and 'Primeira fala' in corpo['texto'] and 'Segunda resposta' in corpo['texto']


def test_esquecimento_remove_episodio_em_vez_de_registro_legado(logado, monkeypatch):
    pedidos, _ = ambiente(logado, monkeypatch)
    conta = type('C', (), {'id': 1, 'admin': False})()
    assert 'Noite de chuva' in models.comando(conta, '/memoria', '')
    assert 'removida' in models.comando(conta, '/esquecer', '1')
    assert any(m == 'DELETE' and r.endswith('/episodios/episodio-ficticio') for m, r, _ in pedidos)


def test_sentimentos_e_temperatura_leem_estado_do_models(logado, monkeypatch):
    pedidos, _ = ambiente(logado, monkeypatch)
    conta = type('C', (), {'id': 1, 'admin': False})()
    assert 'Saudade moderada' in models.comando(conta, '/sentimentos', '')
    assert '0 de 5' in models.comando(conta, '/temperatura', '')
    assert 'Só o Arquiteto' in models.comando(conta, '/temperatura', '3')
    conta.admin = True
    assert '3 de 5' in models.comando(conta, '/temperatura', '3')
    assert any(m == 'PUT' and r.endswith('/mente/estado') and d == {'temperatura': 3} for m, r, d in pedidos)


def test_comando_construtivo_chega_pelo_whatsapp_sem_trocar_modelo(logado, monkeypatch):
    _, estado = ambiente(logado, monkeypatch, admin=True)
    with SessionLocal() as db:
        db.add(CanalVinculo(conta_id=1, canal='whatsapp', origem='construtivo-teste'))
        db.commit()
        r = roteador.atender_texto(db, 'whatsapp', 'construtivo-teste', '/construtivo ligar')
        assert 'ligado' in r.mensagens[0]['texto']
        assert estado['ligado'] and models.selecionado(1) == IDENT
