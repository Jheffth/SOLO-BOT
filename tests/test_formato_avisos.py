"""Contrato dos formatos de aviso; transportes e síntese simulados."""
from test_avisos import pronto, voz_falsa, _hora, ROT
from canais import telegram, evolution, entrega
from nucleo import roteador
from database import SessionLocal
from nucleo import avisos
from datetime import datetime
from zoneinfo import ZoneInfo
import config


def enviar(pronto, formato):
    r=pronto.post('/interno/enviar',headers=ROT,json={'usuario_id':'1','texto':'Comprar fio dental','falado':'Comprar fio dental','formato':formato})
    assert r.status_code==200


def test_audio_ambos_texto_e_preferencia_global(pronto,caixa,voz_falsa,monkeypatch):
    _hora(monkeypatch,14)
    caixa.clear();enviar(pronto,'audio')
    assert [m[0] for m in caixa]==['voz-telegram']
    caixa.clear();enviar(pronto,'ambos')
    assert [m[0] for m in caixa]==['telegram','voz-telegram']
    caixa.clear();enviar(pronto,'texto')
    assert [m[0] for m in caixa]==['telegram']
    pronto.patch('/api/conta/avisos',json={'voz':'nunca'})
    caixa.clear();enviar(pronto,'audio')
    assert [m[0] for m in caixa]==['telegram']
    pronto.patch('/api/conta/avisos',json={'voz':'sempre'})
    caixa.clear();enviar(pronto,'texto')
    assert [m[0] for m in caixa]==['telegram','voz-telegram']


def test_audio_falha_entrega_tem_texto(pronto,caixa,voz_falsa,monkeypatch):
    _hora(monkeypatch,14)
    monkeypatch.setattr(telegram,'enviar_voz',lambda *a:False)
    caixa.clear();enviar(pronto,'audio')
    assert [m[0] for m in caixa]==['telegram']
    assert 'Comprar fio dental' in caixa[0][2]


def test_formato_persistido_no_silencio(pronto,caixa,voz_falsa,monkeypatch):
    pronto.patch('/api/conta/avisos',json={'silencio':True,'de':'22:00','ate':'07:00'})
    _hora(monkeypatch,23)
    caixa.clear();enviar(pronto,'audio');assert caixa==[]
    with SessionLocal() as db:
        assert avisos.despachar_pendentes(db,datetime(2026,10,2,7,tzinfo=ZoneInfo(config.FUSO)))==1
    assert [m[0] for m in caixa]==['voz-telegram']


def test_whatsapp_audio_exclusivo_e_fallback(monkeypatch,caixa):
    r=roteador.Resposta();r.mensagens=[{'texto':'Missão','formato':'audio','audio':{'base64':'Vk9a','mime':'audio/ogg'}}]
    monkeypatch.setattr(evolution,'enviar_audio',lambda *a:caixa.append(('audio',)) or {'key':{'id':'1'}})
    entrega.entregar(None,'whatsapp','jid',r,falar=False)
    assert caixa==[('audio',)]
    caixa.clear();monkeypatch.setattr(evolution,'enviar_audio',lambda *a:{'erro':'falha de rede'})
    entrega.entregar(None,'whatsapp','jid',r,falar=False)
    assert [m[0] for m in caixa]==['whatsapp']


def test_formato_invalido(pronto):
    assert pronto.post('/interno/enviar',headers=ROT,json={'usuario_id':'1','texto':'x','formato':'invalido'}).status_code==422
