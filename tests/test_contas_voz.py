"""Seleção persistente de conta e envio real simulado em cada chave."""
import httpx
import pytest

import config
from database import SessionLocal, gravar_config, ler_config
from nucleo import fala
from test_voz_admin import admin  # noqa: F401


@pytest.fixture()
def contas(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "segredo-principal")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "segredo-secundaria")
    monkeypatch.setattr(config, "ELEVENLABS_CONTAS_EXTRAS", {"3": "segredo-terceira"})
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "V")
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_flash_v2_5")
    monkeypatch.setattr(fala, "_estado", {"voz": None, "ultimo_erro": None})
    return ["segredo-principal", "segredo-secundaria", "segredo-terceira"]


def selecionar(conta):
    with SessionLocal() as db:
        gravar_config(db, fala.CHAVE_CONTA, conta)


def simular(monkeypatch, status):
    pedidos = []

    class Cliente:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json, headers):
            chave = headers["xi-api-key"]
            pedidos.append((chave, url, json))
            return httpx.Response(status[chave], content=b"AUDIO" if status[chave] == 200 else b"")
        def get(self, url, headers):
            chave = headers["xi-api-key"]
            return httpx.Response(200, json={"voices": [{"voice_id": chave + "-voz", "name": "Voz", "category": "cloned"}]})

    monkeypatch.setattr(fala.httpx, "Client", Cliente)
    return pedidos


def test_painel_seleciona_persiste_e_nao_expoe_chaves(admin, contas):
    painel = admin.get("/api/admin/voz")
    assert painel.json()["conta"] == {"atual": "automatica", "opcoes": [
        {"id": "principal", "nome": "Principal"}, {"id": "reserva", "nome": "Secundária"},
        {"id": "conta_3", "nome": "Conta 3"}]}
    assert all(chave not in painel.text for chave in contas)
    assert admin.put("/api/admin/voz", json={"conta": "reserva"}).status_code == 200
    assert ler_config(fala.CHAVE_CONTA) == "reserva"
    assert admin.get("/api/admin/voz").json()["conta"]["atual"] == "reserva"
    assert admin.put("/api/admin/voz", json={"conta": "conta_3"}).status_code == 200
    assert fala._chaves() == [contas[2]]
    assert admin.put("/api/admin/voz", json={"conta": "automatica"}).status_code == 200
    assert fala._chaves() == contas


def test_troca_limpa_vozes_e_rejeita_conta_invalida_sem_mudar(admin, contas):
    with SessionLocal() as db:
        gravar_config(db, fala.CHAVE_VOZ, "ANTIGA")
        gravar_config(db, fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    fala._estado["voz"] = "ANTIGA"
    assert admin.put("/api/admin/voz", json={"conta": "inexistente"}).status_code == 422
    assert ler_config(fala.CHAVE_VOZ) == "ANTIGA"
    assert admin.put("/api/admin/voz", json={"conta": "reserva", "voice_id": "X"}).status_code == 422
    assert fala.conta_escolhida() == "automatica"
    assert admin.put("/api/admin/voz", json={"conta": "reserva"}).status_code == 200
    assert ler_config(fala.CHAVE_VOZ) is None and ler_config(fala.CHAVE_VOZ_SISTEMA) is None
    assert fala._estado["voz"] is None


@pytest.mark.parametrize("status", [200, 402, 429])
def test_manual_usa_so_secundaria_mesmo_se_falhar(cliente, contas, monkeypatch, status):
    selecionar("reserva")
    pedidos = simular(monkeypatch, {contas[1]: status})
    resultado = fala.sintetizar("Oi", "whatsapp")
    assert bool(resultado) == (status == 200)
    assert [p[0] for p in pedidos] == [contas[1]]


def test_automatico_chega_na_terceira_apos_creditos_acabarem(cliente, contas, monkeypatch):
    pedidos = simular(monkeypatch, dict(zip(contas, [402, 402, 200])))
    assert fala.sintetizar("Oi", "whatsapp")
    assert [p[0] for p in pedidos] == contas
    assert fala.ultimo_erro() is None


@pytest.mark.parametrize("tom", [None, "sussurro"])
def test_automatico_usa_voz_da_proxima_conta(cliente, contas, monkeypatch, tom):
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "")
    with SessionLocal() as db:
        gravar_config(db, fala.CHAVE_VOZ, "CLONADA_PRINCIPAL")
        gravar_config(db, fala.CHAVE_VOZ_SISTEMA, "SUSSURRO_PRINCIPAL")
    pedidos = simular(monkeypatch, dict(zip(contas, [402, 200, 200])))
    assert fala.sintetizar("Oi", "whatsapp", tom=tom)
    assert ("SUSSURRO_PRINCIPAL" if tom else "CLONADA_PRINCIPAL") in pedidos[0][1]
    assert contas[1] + "-voz" in pedidos[-1][1]


def test_catalogo_manual_e_creditos_de_todas_as_contas(cliente, contas, monkeypatch):
    selecionar("conta_3")
    simular(monkeypatch, {})
    assert fala.listar_vozes()[0]["voice_id"] == contas[2] + "-voz"
    assert [c["rotulo"] for c in fala.creditos()] == ["principal", "reserva", "conta_3"]


def test_conta_removida_nao_gasta_em_outra(cliente, contas, monkeypatch):
    selecionar("conta_4")
    pedidos = simular(monkeypatch, {})
    assert fala.sintetizar("Oi", "whatsapp") is None
    assert not pedidos and "não está configurada" in fala.ultimo_erro()


def test_reserva_tenta_voz_conhecida_quando_catalogo_indisponivel(cliente, contas, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "")
    with SessionLocal() as db:
        gravar_config(db, fala.CHAVE_VOZ, "COMPARTILHADA")
    pedidos = simular(monkeypatch, dict(zip(contas, [402, 200, 200])))
    monkeypatch.setattr(fala, "listar_vozes", lambda chave=None: [])
    assert fala.sintetizar("Oi", "whatsapp")
    assert pedidos[-1][0] == contas[1] and "COMPARTILHADA" in pedidos[-1][1]


def test_so_admin_pode_trocar(logado, contas):
    assert logado.put("/api/admin/voz", json={"conta": "reserva"}).status_code == 403
    assert fala.conta_escolhida() == "automatica"
