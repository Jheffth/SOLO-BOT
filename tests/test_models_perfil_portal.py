import hashlib
from urllib.parse import urlsplit,parse_qs
import pytest
from nucleo import modulos


@pytest.fixture
def portal(monkeypatch):
    antigo=modulos.todos()
    modulos.recarregar([{'chave':'models','nome':'Models','url':'http://models','token':'token-models'}])
    yield
    modulos.recarregar([m.__dict__ for m in antigo])


def test_entrada_exige_login_e_pkce(cliente,portal):
    desafio=hashlib.sha256(b'v'*43).hexdigest()
    r=cliente.get('/models/perfil',params={'estado':'e'*43,'desafio':desafio},follow_redirects=False)
    assert r.status_code==303 and r.headers['location'].startswith('/entrar?proximo=')
    assert cliente.get('/models/perfil?estado=ruim',follow_redirects=False).status_code==422


def test_codigo_unico_so_entrega_a_identidade_atual(logado,portal):
    estado='e'*43;verificador='v'*43
    r=logado.get('/models/perfil',params={'estado':estado,'desafio':hashlib.sha256(verificador.encode()).hexdigest()},follow_redirects=False)
    assert r.status_code==303 and urlsplit(r.headers['location']).netloc=='solomodels.duckdns.org'
    codigo=parse_qs(urlsplit(r.headers['location']).query)['codigo'][0]
    base='/interno/models/portal/resgatar';dados={'codigo':codigo,'verificador':verificador}
    assert logado.post(base,json=dados).status_code==403
    assert logado.post(base,json={**dados,'verificador':'x'*43},headers={'X-Solo-Token':'token-models'}).status_code==403
    r=logado.post(base,json=dados,headers={'X-Solo-Token':'token-models'})
    assert r.status_code==200 and r.json()['arquiteto'] is False
    assert r.json()['dono_id'].startswith('solo-bot:conta:')
    assert 'email' not in r.json() and 'senha' not in r.text
    assert logado.post(base,json=dados,headers={'X-Solo-Token':'token-models'}).status_code==403
