"""Administração da voz: saldo de créditos, vozes e modelo."""
import pytest

import config
from nucleo import fala

VOZES = [{"voice_id": "A", "nome": "Ana", "categoria": "cloned", "propria": True, "biblioteca": False, "preview_url": "u", "descricao": ""},
         {"voice_id": "B", "nome": "Bia", "categoria": "premade", "propria": False, "biblioteca": False, "preview_url": "u", "descricao": ""}]


@pytest.fixture()
def admin(cliente, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "")
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "")
    monkeypatch.setattr(fala, "_estado", {"voz": None, "ultimo_erro": None})
    monkeypatch.setattr(fala, "listar_vozes", lambda: VOZES)
    monkeypatch.setattr(fala, "creditos", lambda: [{"rotulo": "principal", "usados": 2500, "limite": 10000,
                                                    "restantes": 7500, "plano": "starter", "renova_em": "2026-10-20"}])
    cliente.post("/api/auth/cadastro", json={"nome": "Arq", "usuario": "arq", "email": "arquiteto@solo.dev", "senha": "12345678"})
    return cliente


def test_painel_mostra_saldo_voz_automatica_e_modelo_padrao(admin):
    v = admin.get("/api/admin/voz").json()
    assert v["creditos"][0]["restantes"] == 7500
    assert v["voz"] == {"id": "A", "nome": "Ana", "origem": "automatica"}     # própria antes de padrão
    assert v["modelo"]["atual"] == "eleven_flash_v2_5" and not v["modelo"]["fixo_no_env"]


def test_escolher_voz_e_modelo_na_tela(admin):
    assert admin.put("/api/admin/voz", json={"voice_id": "B"}).status_code == 200
    assert admin.put("/api/admin/voz", json={"modelo": "eleven_v4_turbo"}).status_code == 200
    v = admin.get("/api/admin/voz").json()
    assert v["voz"]["id"] == "B" and v["voz"]["origem"] == "tela" and v["modelo"]["atual"] == "eleven_v4_turbo"
    assert fala.voz() == "B" and fala.modelo() == "eleven_v4_turbo"               # e a síntese passa a usar
    assert admin.put("/api/admin/voz", json={"voice_id": "ZZZ"}).status_code == 404
    assert admin.put("/api/admin/voz", json={"modelo": "eleven_v9"}).status_code == 422


def test_env_fixa_e_a_tela_nao_troca(admin, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "B")
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_v4")
    v = admin.get("/api/admin/voz").json()
    assert v["voz"]["origem"] == "env" and v["modelo"]["fixo_no_env"]
    assert admin.put("/api/admin/voz", json={"voice_id": "A"}).status_code == 409
    assert admin.put("/api/admin/voz", json={"modelo": "eleven_flash_v2_5"}).status_code == 409


def test_amostra_devolve_mp3(admin, monkeypatch):
    monkeypatch.setattr(fala, "sintetizar", lambda t, c, v=None: {"base64": "SUQz", "mime": "audio/mpeg"})
    r = admin.post("/api/admin/voz/amostra", json={"texto": "oi"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3"


def test_so_admin(logado):
    assert logado.get("/api/admin/voz").status_code == 403


def test_creditos_sem_permissao(monkeypatch):
    import httpx
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "")

    class C:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, url, headers): return httpx.Response(401)
    monkeypatch.setattr(fala.httpx, "Client", C)
    assert "User → Read" in fala.creditos()[0]["erro"]
