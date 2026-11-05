"""Foto do desktop: seleção, capa própria, autenticação e retorno ao legado."""
import base64
from uuid import uuid4
import pytest
from test_bella import acesso
from nucleo import models, models_galeria as galeria


def preparar(monkeypatch, capa=True):
    ident, foto = str(uuid4()), str(uuid4())
    monkeypatch.setattr(models, 'selecionado', lambda conta: ident)
    monkeypatch.setattr(models, 'pacote', lambda conta, m: {'id':m,'nome':'Modelo de teste',
        'galeria':{'capa':foto if capa else None}})
    monkeypatch.setattr(galeria, 'catalogo', lambda conta,p,t: [{'id':foto,'nivel':0,'tipo':'imagem'}])
    chamadas=[]
    def baixar(i,t,miniatura=False):
        chamadas.append((i,t,miniatura))
        return {'mime':'image/jpeg','base64':base64.b64encode(b'\xff\xd8\xffimagem-teste').decode()}
    monkeypatch.setattr(galeria,'baixar',baixar)
    return ident,foto,chamadas


def test_perfil_foto_e_condicional_nao_repete_download(acesso,monkeypatch):
    c,h=acesso
    ident,foto,chamadas=preparar(monkeypatch)
    r=c.get('/api/bella/perfil',headers=h)
    assert r.status_code==200
    assert r.headers['cache-control']=='private, no-store'
    p=r.json()
    assert p['origem']=='models' and p['modelo_id']==ident
    assert p['foto'].startswith('data:image/jpeg;base64,')
    assert chamadas==[(foto,'imagem',True)]
    r=c.get('/api/bella/perfil',headers=h,params={'foto_atual':p['foto_id']})
    assert r.json()['inalterada'] is True and r.json()['foto'] is None
    assert len(chamadas)==1
    assert c.get('/api/bella/perfil').status_code==401
    c.delete('/api/conta/bella')
    assert c.get('/api/bella/perfil',headers=h).status_code==401


def test_perfil_troca_de_modelo_e_remove_capa(acesso,monkeypatch):
    c,h=acesso
    ident,foto,_=preparar(monkeypatch)
    primeiro=c.get('/api/bella/perfil',headers=h).json()
    segundo,_,downloads=preparar(monkeypatch,capa=False)
    r=c.get('/api/bella/perfil',headers=h,params={'foto_atual':primeiro['foto_id']}).json()
    assert r['modelo_id']==segundo and segundo!=ident
    assert r['foto'] is None and r['inalterada'] is False and downloads==[]
    monkeypatch.setattr(models,'selecionado',lambda c:None)
    r=c.get('/api/bella/perfil',headers=h).json()
    assert r['origem']=='legado' and r['foto'] is None


def test_capa_alheia_e_nivel_intimo_nao_sao_baixados(acesso,monkeypatch):
    c,h=acesso
    ident,foto,downloads=preparar(monkeypatch)
    # O catálogo filtrado só permite imagens padrão da própria modelo.
    monkeypatch.setattr(galeria,'catalogo',lambda *a:[])
    r=c.get('/api/bella/perfil',headers=h)
    assert r.status_code==200 and r.json()['foto'] is None and downloads==[]


def test_falha_preserva_selecao_sem_substituir_por_legado(acesso,monkeypatch):
    c,h=acesso
    preparar(monkeypatch)
    def falhar(*a): raise models.ErroModels('Models indisponível.')
    monkeypatch.setattr(models,'pacote',falhar)
    assert c.get('/api/bella/perfil',headers=h).status_code==503
