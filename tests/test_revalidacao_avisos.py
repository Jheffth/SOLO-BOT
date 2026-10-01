"""Fila com referência: o sistema dono confirma; sem rede real."""
from datetime import datetime
from zoneinfo import ZoneInfo
from test_avisos import pronto, voz_falsa, _hora, ROT
from conftest import Resp
from database import SessionLocal, AvisoPendente, VinculoSistema
from nucleo import avisos, modulos
import config


def enfileirar(pronto,monkeypatch,referencia='central:1:ref',formato='texto'):
    pronto.patch('/api/conta/avisos',json={'silencio':True,'de':'22:00','ate':'07:00'})
    _hora(monkeypatch,23)
    corpo={'usuario_id':'1','texto':'A missão não foi iniciada.','falado':'Versão antiga',
           'formato':formato,'valido_ate':'2026-10-02T08:00:00-03:00'}
    if referencia: corpo['referencia']=referencia
    assert pronto.post('/interno/enviar',headers=ROT,json=corpo).json()['adiados']==1


def despachar(h=7):
    with SessionLocal() as db:
        return avisos.despachar_pendentes(db,datetime(2026,10,2,h,tzinfo=ZoneInfo(config.FUSO)))


def quantidade():
    with SessionLocal() as db: return db.query(AvisoPendente).count()


def test_concluida_revoga_ainda_durante_silencio(pronto,caixa,monkeypatch):
    enfileirar(pronto,monkeypatch);caixa.clear()
    chamadas=[]
    def validar(url,token,corpo,timeout=None):
        chamadas.append((url,token,corpo));return Resp(200,{'valido':False})
    monkeypatch.setattr(modulos,'_post',validar)
    assert despachar(6)==0 and quantidade()==0 and caixa==[]
    assert chamadas[0]==('http://rot/interno/bot/validar-aviso','tok-rot',{'usuario_id':'1','referencia':'central:1:ref'})
    assert despachar()==0


def test_indisponivel_mantem_na_fila_e_expira(pronto,caixa,monkeypatch):
    enfileirar(pronto,monkeypatch);caixa.clear()
    def offline(*a): raise OSError('simulado')
    monkeypatch.setattr(modulos,'_post',offline)
    assert despachar()==0 and quantidade()==1 and caixa==[]
    assert despachar(8)==0 and quantidade()==0


def test_malformado_nao_autoriza_e_recuperacao_entrega_estado_atual(pronto,caixa,voz_falsa,monkeypatch):
    enfileirar(pronto,monkeypatch,formato='audio');caixa.clear()
    monkeypatch.setattr(modulos,'_post',lambda *a:Resp(200,{'valido':'true'}))
    assert despachar()==0 and quantidade()==1
    monkeypatch.setattr(modulos,'_post',lambda *a:Resp(200,{'valido':True,'texto':'A missão está em andamento.'}))
    assert despachar()==1 and quantidade()==0
    assert voz_falsa==['A missão está em andamento.']
    assert [m[0] for m in caixa]==['voz-telegram']


def test_sem_referencia_preserva_contrato_legado(pronto,caixa,monkeypatch):
    enfileirar(pronto,monkeypatch,referencia=None);caixa.clear()
    monkeypatch.setattr(modulos,'_post',lambda *a:(_ for _ in ()).throw(AssertionError('legado não consulta')))
    assert despachar()==1 and quantidade()==0
    assert [m[0] for m in caixa]==['telegram']


def test_desvinculado_descarta_sem_callback(pronto,caixa,monkeypatch):
    enfileirar(pronto,monkeypatch);caixa.clear()
    with SessionLocal() as db:
        db.query(VinculoSistema).filter_by(app='rot').delete();db.commit()
    monkeypatch.setattr(modulos,'_post',lambda *a:(_ for _ in ()).throw(AssertionError('não deve consultar outro hunter')))
    assert despachar()==0 and quantidade()==0 and caixa==[]


def test_cache_compartilha_consulta_entre_canais(pronto,caixa,monkeypatch):
    enfileirar(pronto,monkeypatch);caixa.clear()
    with SessionLocal() as db:
        p=db.query(AvisoPendente).one()
        db.add(AvisoPendente(conta_id=p.conta_id,canal=p.canal,origem=p.origem,app=p.app,mensagens=p.mensagens,voz=False,valido_ate=p.valido_ate));db.commit()
    chamadas=[]
    monkeypatch.setattr(modulos,'_post',lambda *a:chamadas.append(a) or Resp(200,{'valido':False}))
    assert despachar()==0 and quantidade()==0 and len(chamadas)==1
