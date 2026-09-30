"""Avisos: canais, horário de silêncio (fila) e voz."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import config
from nucleo import avisos, fala
from test_fluxos import _ligar_telegram

ROT = {"X-Solo-Token": "tok-rot"}
FIN = {"X-Solo-Token": "tok-fin"}


def _hora(monkeypatch, h, m=0):
    monkeypatch.setattr(avisos, "agora_local", lambda: datetime(2026, 10, 1, h, m, tzinfo=ZoneInfo(config.FUSO)))


@pytest.fixture()
def pronto(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    _ligar_telegram(logado)
    return logado


@pytest.fixture()
def voz_falsa(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    ditos = []
    monkeypatch.setattr(fala, "sintetizar", lambda t, c, v=None: ditos.append(t) or {"base64": "Vk9a", "mime": "audio/ogg"})
    return ditos


def test_silencio_guarda_e_solta_depois(pronto, caixa, monkeypatch):
    pronto.patch("/api/conta/avisos", json={"silencio": True, "de": "22:00", "ate": "07:00"})
    _hora(monkeypatch, 23, 30)
    n = len(caixa)
    r = pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "Missão das 23h vencida"}).json()
    assert r == {"entregues": 0, "adiados": 1, "vinculado": True} and len(caixa) == n
    a = pronto.get("/api/conta/avisos").json()
    assert a["na_fila"] == 1 and a["silencio"]["agora"] and a["silencio"]["termina_as"] == "07:00"

    from database import SessionLocal
    db = SessionLocal()
    assert avisos.despachar_pendentes(db, datetime(2026, 10, 2, 6, 59, tzinfo=ZoneInfo(config.FUSO))) == 0
    assert avisos.despachar_pendentes(db, datetime(2026, 10, 2, 7, 0, tzinfo=ZoneInfo(config.FUSO))) == 1
    db.close()
    assert "Missão das 23h vencida" in caixa[-1][2]
    assert pronto.get("/api/conta/avisos").json()["na_fila"] == 0


def test_fora_do_silencio_entrega_na_hora(pronto, caixa, monkeypatch):
    pronto.patch("/api/conta/avisos", json={"silencio": True, "de": "22:00", "ate": "07:00"})
    _hora(monkeypatch, 14)
    r = pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "Faltam 15 min"}).json()
    assert r["entregues"] == 1 and "Faltam 15 min" in caixa[-1][2]


def test_janela_no_mesmo_dia_e_atravessando_meia_noite():
    class C: pass
    c = C(); c.avisos_silencio_de, c.avisos_silencio_ate = "13:00", "14:00"
    tz = ZoneInfo(config.FUSO)
    assert avisos.em_silencio(c, datetime(2026, 1, 1, 13, 30, tzinfo=tz))
    assert not avisos.em_silencio(c, datetime(2026, 1, 1, 14, 0, tzinfo=tz))
    c.avisos_silencio_de, c.avisos_silencio_ate = "22:00", "07:00"
    assert avisos.em_silencio(c, datetime(2026, 1, 1, 2, 0, tzinfo=tz))
    assert not avisos.em_silencio(c, datetime(2026, 1, 1, 12, 0, tzinfo=tz))


def test_voz_do_finances_quando_o_sistema_pede(pronto, caixa, voz_falsa, monkeypatch):
    _hora(monkeypatch, 9)
    pronto.post("/interno/enviar", headers=FIN, json={"usuario_id": "4", "texto": "☀️ *Bom dia!* Saldo R$ 1.500,00",
                                                     "falado": "Bom dia! Seu saldo é de mil e quinhentos reais.", "voz": True})
    assert voz_falsa == ["Bom dia! Seu saldo é de mil e quinhentos reais."]      # o roteiro do Finances
    assert caixa[-1][0] == "voz-telegram"
    pronto.post("/interno/enviar", headers=FIN, json={"usuario_id": "4", "texto": "Fatura vence amanhã", "voz": False})
    assert len(voz_falsa) == 1                                                   # sem pedido, sem voz


def test_voz_sempre_e_nunca(pronto, caixa, voz_falsa, monkeypatch):
    _hora(monkeypatch, 9)
    pronto.patch("/api/conta/avisos", json={"voz": "sempre"})
    pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "Missão concluída!"})
    assert len(voz_falsa) == 1
    pronto.patch("/api/conta/avisos", json={"voz": "nunca"})
    pronto.post("/interno/enviar", headers=FIN, json={"usuario_id": "4", "texto": "x", "falado": "x", "voz": True})
    assert len(voz_falsa) == 1


def test_canal_sem_avisos_nao_recebe(pronto, caixa, monkeypatch):
    _hora(monkeypatch, 9)
    pronto.patch("/api/conta/canais/telegram", json={"avisos": False})
    r = pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "x"}).json()
    assert r["entregues"] == 0


def test_validacao(pronto):
    assert pronto.patch("/api/conta/avisos", json={"silencio": True, "de": "25:00"}).status_code == 422
    assert pronto.patch("/api/conta/avisos", json={"silencio": True, "de": "07:00", "ate": "07:00"}).status_code == 422
    assert pronto.patch("/api/conta/avisos", json={"voz": "gritando"}).status_code == 422
    a = pronto.patch("/api/conta/avisos", json={"silencio": False}).json()
    assert a["silencio"]["ativo"] is False
