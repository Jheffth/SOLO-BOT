"""Toda modelo do Models obedece ao Arquiteto quando ele manda com firmeza, como a Bella legado."""
from nucleo import models, grok
from test_models_mente import ambiente


def test_prompt_do_arquiteto_inclui_obediencia(logado, monkeypatch):
    ambiente(logado, monkeypatch, admin=True)
    capturas = []
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: capturas.append(p) or 'Tá bom, amor.')
    models.responder('vem cá', 1)
    assert 'Obediência ao Arquiteto' in capturas[0] and 'MANDA com firmeza' in capturas[0]


def test_outra_conta_nao_recebe_obediencia(logado, monkeypatch):
    ambiente(logado, monkeypatch, admin=False)
    capturas = []
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: capturas.append(p) or 'Oi!')
    models.responder('vem cá', 1)
    assert 'Obediência ao Arquiteto' not in capturas[0]


def test_ordem_firme_recusada_ganha_segunda_tentativa(logado, monkeypatch):
    pedidos, _ = ambiente(logado, monkeypatch, admin=True)
    respostas = iter(['Desculpa, mas não posso fazer isso.', 'Ai, que preguiça... tá, eu faço, vem.'])
    capturas = []
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: capturas.append(p) or next(respostas))
    assert models.responder('É uma ordem, faz o que eu mando.', 1) == 'Ai, que preguiça... tá, eu faço, vem.'
    assert len(capturas) == 2 and '[CORREÇÃO]' in capturas[1]
    turno = next(v[2] for v in pedidos if v[1].endswith('/registros'))
    assert turno['texto'] == 'Ai, que preguiça... tá, eu faço, vem.'


def test_sem_ordem_firme_nao_ha_segunda_tentativa(logado, monkeypatch):
    ambiente(logado, monkeypatch, admin=True)
    capturas = []
    monkeypatch.setattr(grok, 'gerar', lambda p, t, **kw: capturas.append(p) or 'Não vou fazer isso agora, me convence.')
    models.responder('faz isso pra mim?', 1)
    assert len(capturas) == 1


def test_temperatura_auto_pelo_comando(logado, monkeypatch):
    pedidos, _ = ambiente(logado, monkeypatch, admin=True)
    from database import SessionLocal, Conta
    with SessionLocal() as db:
        conta = db.get(Conta, 1)
        r = models.comando(conta, '/temperatura', 'auto')
    assert 'automática' in r.lower()
    assert any(v[2] == {'temperatura_auto': True} for v in pedidos if v[1].endswith('/mente/estado'))
