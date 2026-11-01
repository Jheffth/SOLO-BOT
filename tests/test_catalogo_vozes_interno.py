"""Testes da consulta interna autenticada de vozes e saúde de integração."""
import pytest
from fastapi.testclient import TestClient

import config
from main import app
from nucleo import fala, modulos, voicestudio


TOKEN_MODELS = "token-teste-models-12345"


@pytest.fixture(autouse=True)
def setup_modulos():
    modulos_originais = list(config.MODULOS)
    novos_modulos = [dict(m) for m in config.MODULOS]
    models_encontrado = False
    for m in novos_modulos:
        if m["chave"] == "models":
            m["token"] = TOKEN_MODELS
            models_encontrado = True
    if not models_encontrado:
        novos_modulos.append({
            "chave": "models", "nome": "Solo Models", "emoji": "🎭", "cor": "#9333ea",
            "descricao": "Catálogo", "url": "http://solo-models_app:8000", "token": TOKEN_MODELS, "painel": ""
        })
    modulos.recarregar(novos_modulos)
    yield
    modulos.recarregar(modulos_originais)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_saude_publica_vs_interna(client):
    # Rota pública /saude: não exige token
    r_pub = client.get("/saude")
    assert r_pub.status_code == 200
    assert r_pub.json() == {"ok": True}

    # Rota interna /interno/saude: exige X-Solo-Token
    # 1. Sem token
    r_sem = client.get("/interno/saude")
    assert r_sem.status_code == 403
    assert r_sem.json() == {"detail": "token de serviço inválido"}

    # 2. Token inválido
    r_err = client.get("/interno/saude", headers={"X-Solo-Token": "invalido"})
    assert r_err.status_code == 403
    assert r_err.json() == {"detail": "token de serviço inválido"}

    # 3. Token válido de Solo Models
    r_ok = client.get("/interno/saude", headers={"X-Solo-Token": TOKEN_MODELS})
    assert r_ok.status_code == 200
    assert r_ok.json() == {"status": "ok", "app": "models", "nome": "Solo Models"}


def test_vozes_internas_autenticacao(client):
    # Sem token
    r_sem = client.get("/interno/vozes")
    assert r_sem.status_code == 403
    assert r_sem.json() == {"detail": "token de serviço inválido"}

    # Token incorreto
    r_err = client.get("/interno/vozes", headers={"X-Solo-Token": "token-falso"})
    assert r_err.status_code == 403
    assert TOKEN_MODELS not in r_err.text


def test_catalogo_todas_vozes_multiplas_contas_e_provedores(monkeypatch):
    # Configura duas contas ElevenLabs e VoiceStudio ativo
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "chave-principal")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "chave-reserva")
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "http://voicestudio-teste:8000")

    vozes_principal = [
        {"voice_id": "v_el_1", "nome": "Voz Principal 1", "categoria": "cloned",
         "preview_url": "https://preview.com/v1.mp3", "descricao": "Suave, jovem"},
    ]
    vozes_reserva = [
        {"voice_id": "v_el_2", "nome": "Voz Reserva 2", "categoria": "premade",
         "preview_url": None, "descricao": "Grave"},
    ]

    def mock_listar_vozes(chave=None):
        if chave == "chave-principal":
            return vozes_principal
        if chave == "chave-reserva":
            return vozes_reserva
        return []

    vozes_vs = [
        {"voice_id": "v_vs_1", "nome": "Clone Local VS", "preview_url": None},
    ]

    monkeypatch.setattr(fala, "listar_vozes", mock_listar_vozes)
    monkeypatch.setattr(voicestudio, "disponivel_servidor", lambda: True)
    monkeypatch.setattr(voicestudio, "listar_vozes", lambda forcar=False: vozes_vs)

    itens = fala.catalogo_todas_vozes()
    assert len(itens) == 3

    # Conta principal ElevenLabs
    item0 = next(x for x in itens if x["identificador"] == "v_el_1")
    assert item0["provedor"] == "elevenlabs"
    assert item0["conta"] == "principal"
    assert item0["amostra"] == "https://preview.com/v1.mp3"
    assert "chave" not in str(item0)

    # Conta reserva ElevenLabs
    item1 = next(x for x in itens if x["identificador"] == "v_el_2")
    assert item1["provedor"] == "elevenlabs"
    assert item1["conta"] == "reserva"
    assert item1["amostra"] is None

    # VoiceStudio
    item2 = next(x for x in itens if x["identificador"] == "v_vs_1")
    assert item2["provedor"] == "voicestudio"
    assert item2["conta"] == "voicestudio"
    assert item2["nome"] == "Clone Local VS"


def test_catalogo_vozes_tolerante_a_falha(monkeypatch):
    # Se uma conta falhar ou VoiceStudio falhar, não derruba o catálogo
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "chave-ok")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "chave-quebrada")
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "http://voicestudio-offline:8000")

    def mock_listar_vozes(chave=None):
        if chave == "chave-ok":
            return [{"voice_id": "v_ok", "nome": "Voz OK", "categoria": "cloned", "preview_url": None, "descricao": ""}]
        raise RuntimeError("Conta ElevenLabs offline")

    def mock_vs(forcar=False):
        raise RuntimeError("VoiceStudio offline")

    monkeypatch.setattr(fala, "listar_vozes", mock_listar_vozes)
    monkeypatch.setattr(voicestudio, "disponivel_servidor", lambda: True)
    monkeypatch.setattr(voicestudio, "listar_vozes", mock_vs)

    itens = fala.catalogo_todas_vozes()
    # Continua retornando o que funcionou
    assert len(itens) == 1
    assert itens[0]["identificador"] == "v_ok"
    assert itens[0]["conta"] == "principal"


def test_rota_vozes_interna_endpoint(client, monkeypatch):
    vozes_falsas = [
        {"identificador": "v_teste", "nome": "Teste", "provedor": "elevenlabs", "conta": "principal", "amostra": None, "categoria": "cloned", "descricao": None}
    ]
    monkeypatch.setattr(fala, "catalogo_todas_vozes", lambda: vozes_falsas)

    r = client.get("/interno/vozes", headers={"X-Solo-Token": TOKEN_MODELS})
    assert r.status_code == 200
    dados = r.json()
    assert "vozes" in dados
    assert len(dados["vozes"]) == 1
    assert dados["vozes"][0]["identificador"] == "v_teste"
