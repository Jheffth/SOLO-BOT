"""Siri / Atalhos do iPhone: mais um canal, com chave pessoal."""
import pytest

import config
from nucleo import fala


@pytest.fixture()
def siri(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    r = logado.post("/api/conta/atalho").json()
    assert r["chave"].startswith("solo_") and r["url"].endswith("/api/atalho")
    return logado, {"X-Solo-Chave": r["chave"]}


def test_chave_aparece_uma_vez_e_so_o_hash_fica(siri):
    c, h = siri
    from database import Conta, SessionLocal
    db = SessionLocal()
    conta = db.query(Conta).first()
    assert conta.atalho_hash and h["X-Solo-Chave"] not in (conta.atalho_hash or "")
    db.close()
    e = c.get("/api/conta/atalho").json()
    assert e["ativo"] and "chave" not in e and e["usado_em"] is None


def test_siri_fala_com_o_sistema_e_escolhe_pelo_numero_falado(siri, sistemas):
    c, h = siri
    r = c.post("/api/atalho", headers=h, json={"texto": "/rot hoje"}).json()
    assert sistemas.recebidos[-1][0] == "rot" and sistemas.recebidos[-1][2]["texto"] == "hoje"
    assert sistemas.recebidos[-1][2]["canal"] == "siri"
    assert "eco:hoje" in r["texto"] and "1. ✅ — Banho" in r["texto"] and "*" not in r["texto"]
    assert r["falar"].endswith("Para escolher, diga o número.") and "audio_base64" not in r

    r = c.post("/api/atalho", headers=h, json={"texto": "Um."}).json()           # o ditado do iPhone
    assert sistemas.recebidos[-1][1] == "acao" and sistemas.recebidos[-1][2]["dados"] == "ok|r|12"
    assert c.get("/api/conta/atalho").json()["usado_em"]


def test_modo_ativo_vale_entre_um_ei_siri_e_outro(siri, sistemas):
    c, h = siri
    c.post("/api/atalho", headers=h, json={"texto": "/fin"})
    c.post("/api/atalho", headers=h, json={"texto": "/saldo"})
    assert sistemas.recebidos[-1][0] == "fin" and sistemas.recebidos[-1][2]["texto"] == "/saldo"


def test_voz_do_solo_bot_vem_em_mp3(siri, monkeypatch):
    c, h = siri
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    ditos = []
    monkeypatch.setattr(fala, "sintetizar", lambda t, canal, v=None: ditos.append((t, canal)) or
                        {"base64": "TVAz", "mime": "audio/mpeg"})
    r = c.post("/api/atalho", headers=h, json={"texto": "/fin saldo", "voz": True}).json()
    assert r["audio_base64"] == "TVAz" and r["mime"] == "audio/mpeg"
    assert ditos == [(r["falar"], "whatsapp")]


def test_chave_errada_revogada_ou_trocada_nao_entra(siri):
    c, h = siri
    assert c.post("/api/atalho", headers={"X-Solo-Chave": "solo_" + "x" * 40}, json={"texto": "oi"}).status_code == 401
    assert c.post("/api/atalho", json={"texto": "oi"}).status_code == 401
    nova = c.post("/api/conta/atalho").json()["chave"]                    # trocar invalida a antiga
    assert c.post("/api/atalho", headers=h, json={"texto": "oi"}).status_code == 401
    assert c.post("/api/atalho", headers={"X-Solo-Chave": nova}, json={"texto": "oi"}).status_code == 200
    c.delete("/api/conta/atalho")
    assert c.post("/api/atalho", headers={"X-Solo-Chave": nova}, json={"texto": "oi"}).status_code == 401
    assert c.get("/api/conta/atalho").json()["ativo"] is False


def test_origem_siri_nao_se_forja_pelo_telegram(siri, caixa):
    """`siri:<id>` só vale no canal siri; um chat do Telegram com esse nome não vira a conta."""
    from database import SessionLocal
    from nucleo import roteador
    db = SessionLocal()
    assert roteador.conta_de(db, "telegram", "siri:1") is None
    assert roteador.conta_de(db, "siri", "siri:abc") is None
    assert roteador.conta_de(db, "siri", "siri:1") is not None
    db.close()


def test_numero_falado():
    from routers.atalho import _numero_falado
    assert _numero_falado("Dois.") == "2" and _numero_falado("opção 3") == "3"
    assert _numero_falado("o número três") == "3" and _numero_falado("2") == "2"
    assert _numero_falado("dois reais no almoço") is None
