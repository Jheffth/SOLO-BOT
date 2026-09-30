"""O tom "sussurro": a voz do Sistema cobrando (os Ecos do Rotinas)."""
import httpx
import pytest

import config
from nucleo import fala
from test_avisos import ROT, _hora, pronto  # noqa: F401  (fixture)
from test_voz_admin import VOZES, admin  # noqa: F401  (fixture)


@pytest.fixture()
def voz_tom(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    ditos = []

    def sintetizar(texto, canal, id_voz=None, tom=None):
        ditos.append({"texto": texto, "voz": id_voz, "tom": tom})
        return {"base64": "Vk9a", "mime": "audio/ogg"}
    monkeypatch.setattr(fala, "sintetizar", sintetizar)
    monkeypatch.setattr(fala, "voz", lambda: "BOT")
    return ditos


def test_eco_sai_em_italico_na_voz_do_sistema_e_sem_resumo(pronto, caixa, voz_tom, monkeypatch):
    from database import SessionLocal, gravar_config
    from nucleo import gemini
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: pytest.fail("sussurro não passa pela IA"))
    db = SessionLocal()
    gravar_config(db, fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    db.close()
    _hora(monkeypatch, 21)
    frase = "Fio dental. O Sistema anotou. Quatro dívidas, Jogador, e você ainda acha que ele brinca com você?"
    r = pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": frase,
                                                         "voz": True, "tom": "sussurro"}).json()
    assert r["entregues"] == 1
    assert f"_{frase}_" in caixa[-2][2]                                  # texto em itálico
    assert voz_tom == [{"texto": frase, "voz": "SOMBRA", "tom": "sussurro"}]   # literal, voz do Sistema


def test_sem_voz_do_sistema_usa_a_do_bot_e_tom_desconhecido_e_ignorado(pronto, caixa, voz_tom, monkeypatch):
    _hora(monkeypatch, 21)
    pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "O Sistema observa.",
                                                     "voz": True, "tom": "sussurro"})
    assert voz_tom[-1]["voz"] == "BOT" and voz_tom[-1]["tom"] == "sussurro"
    pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "Missão concluída.",
                                                     "voz": True, "tom": "gritando"})
    assert voz_tom[-1]["tom"] is None and "_Missão" not in caixa[-2][2]


def test_sussurro_guardado_no_silencio_mantem_o_tom(pronto, caixa, voz_tom, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from database import SessionLocal
    from nucleo import avisos
    pronto.patch("/api/conta/avisos", json={"silencio": True, "de": "22:00", "ate": "07:00"})
    _hora(monkeypatch, 23)
    pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "Ele não dorme.",
                                                     "voz": True, "tom": "sussurro"})
    db = SessionLocal()
    avisos.despachar_pendentes(db, datetime(2026, 10, 2, 7, 0, tzinfo=ZoneInfo(config.FUSO)))
    db.close()
    assert voz_tom[-1]["tom"] == "sussurro" and "_Ele não dorme._" in caixa[-2][2]


def test_sintetizar_sussurro_marca_e_ajusta_a_atuacao(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "")
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "V")
    pedidos = []

    class Cliente:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, json, headers):
            pedidos.append(json)
            return httpx.Response(200, content=b"OK")
    monkeypatch.setattr(fala.httpx, "Client", Cliente)

    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_v4_turbo")
    fala.sintetizar("O Sistema anotou.", "whatsapp", "S", tom="sussurro")
    assert pedidos[-1]["text"] == "[whispers] O Sistema anotou."
    assert pedidos[-1]["voice_settings"]["stability"] == 0.0 and pedidos[-1]["voice_settings"]["style"] > 0.5

    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_flash_v2_5")
    fala.sintetizar("O Sistema anotou.", "whatsapp", "S", tom="sussurro")
    assert pedidos[-1]["text"] == "O Sistema anotou."                # Flash não lê etiqueta
    assert pedidos[-1]["voice_settings"]["stability"] == 0.3

    fala.sintetizar("Oi", "whatsapp")
    assert pedidos[-1]["voice_settings"] == {"stability": 0.5, "similarity_boost": 0.8}   # sem tom, nada muda


def test_admin_escolhe_e_limpa_a_voz_do_sistema(admin):
    assert admin.get("/api/admin/voz").json()["voz_sistema"]["origem"] == "mesma"
    assert admin.put("/api/admin/voz", json={"voice_id_sistema": "B"}).status_code == 200
    v = admin.get("/api/admin/voz").json()
    assert v["voz_sistema"] == {"id": "B", "origem": "tela", "nome": "Bia"} and v["voz"]["id"] == "A"
    assert admin.put("/api/admin/voz", json={"voice_id_sistema": "ZZZ"}).status_code == 404
    assert admin.put("/api/admin/voz", json={"voice_id_sistema": ""}).status_code == 200
    assert admin.get("/api/admin/voz").json()["voz_sistema"]["origem"] == "mesma"
