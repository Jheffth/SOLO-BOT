"""Saudações: custos só na primeira síntese, identidade da voz e cache persistente."""
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

import config
from database import Conta, SessionLocal, gravar_config
from nucleo import fala
from routers import bella


@pytest.fixture()
def banco(logado, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BELLA_AUDIO_DIR", str(tmp_path))
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "chave-principal")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "chave-reserva")
    monkeypatch.setattr(config, "ELEVENLABS_CONTAS_EXTRAS", {})
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "")
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_flash_v2_5")
    monkeypatch.setattr(fala, "_estado", {"voz": None, "ultimo_erro": None})
    with SessionLocal() as db:
        gravar_config(db, fala.CHAVE_VOZ, "VOZ_A")
    pedidos, status = [], {"chave-principal": 200, "chave-reserva": 200}

    class Cliente:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, json, headers):
            pedidos.append((headers["xi-api-key"], url, json))
            codigo = status[headers["xi-api-key"]]
            return httpx.Response(codigo, content=(url + json["text"]).encode() if codigo == 200 else b"")
        def get(self, url, headers):
            id_ = "VOZ_A" if headers["xi-api-key"] == "chave-principal" else "VOZ_RESERVA"
            return httpx.Response(200, json={"voices": [{"voice_id": id_, "name": id_, "category": "cloned"}]})

    monkeypatch.setattr(fala.httpx, "Client", Cliente)
    bella._JANELAS_SAUDACAO.clear()
    chave = logado.post("/api/conta/bella").json()["chave"]
    return logado, {"X-Bella-Chave": chave}, pedidos, status, tmp_path


def catalogo(banco):
    c, h, *_ = banco
    r = c.get("/api/bella/saudacoes", headers=h)
    assert r.status_code == 200
    return r.json()


def saudar(banco, id_=0):
    c, h, *_ = banco
    r = c.post("/api/bella/saudacao", headers=h, json={"id": id_})
    assert r.status_code == 200
    return r.json()


def test_catalogo_tem_20_frases_diferentes_com_login_e_sem_gastar(banco):
    d = catalogo(banco)
    assert d["usuario"] == "jeff" and len(d["saudacoes"]) >= 20
    assert len({s["texto"] for s in d["saudacoes"]}) == len(d["saudacoes"])
    assert all("jeff" in s["texto"] and "Jefferson Costa" not in s["texto"] for s in d["saudacoes"])
    assert d["voz"] == {"conta": "principal", "voz": "VOZ_A", "modelo": "eleven_flash_v2_5"}
    assert banco[2] == [] and "chave-principal" not in json.dumps(d)


def test_20_audios_gerados_uma_vez_e_reusados_depois_de_reiniciar(banco, monkeypatch):
    primeiros = [saudar(banco, i) for i in range(20)]
    assert len(banco[2]) == 20 and len(list(banco[4].rglob("*.mp3"))) == 20
    # Um novo minuto e estado em memória vazio: os arquivos/identidade continuam válidos.
    bella._JANELAS_SAUDACAO.clear()
    monkeypatch.setattr(fala, "_estado", {"voz": None, "ultimo_erro": None})
    assert [saudar(banco, i) for i in range(20)] == primeiros
    assert len(banco[2]) == 20


def test_trocar_voz_nao_mistura_audios_e_voltar_reutiliza(banco):
    a = saudar(banco)
    with SessionLocal() as db:
        gravar_config(db, fala.CHAVE_VOZ, "VOZ_B")
    assert catalogo(banco)["perfil"] != a["perfil"]
    b = saudar(banco)
    assert a["cache_id"] != b["cache_id"] and b["voz"]["voz"] == "VOZ_B"
    with SessionLocal() as db:
        gravar_config(db, fala.CHAVE_VOZ, "VOZ_A")
    assert saudar(banco) == a and len(banco[2]) == 2


def test_automatico_aprende_voz_real_da_reserva_e_reutiliza(banco):
    banco[3]["chave-principal"] = 402
    r = saudar(banco)
    assert r["voz"]["conta"] == "reserva" and r["voz"]["voz"] == "VOZ_RESERVA"
    assert [p[0] for p in banco[2]] == ["chave-principal", "chave-reserva"]
    assert catalogo(banco)["perfil"] == r["perfil"]
    assert saudar(banco) == r and len(banco[2]) == 2
    # Uma resposta normal volta à principal quando ela tiver créditos: próxima chamada acompanha.
    banco[3]["chave-principal"] = 200
    fala.sintetizar("Resposta normal", "whatsapp")
    assert catalogo(banco)["voz"]["voz"] == "VOZ_A"
    assert saudar(banco)["voz"]["voz"] == "VOZ_A"


def test_selecao_manual_invalida_perfil_da_reserva_automatica(banco):
    banco[3]["chave-principal"] = 402
    reserva = saudar(banco)
    with SessionLocal() as db:
        gravar_config(db, fala.CHAVE_CONTA, "principal")
    atual = catalogo(banco)
    assert atual["perfil"] != reserva["perfil"] and atual["voz"]["conta"] == "principal"
    # Manual não usa a saudação de outra voz/conta mesmo se a conta selecionada falhar.
    assert "audio_base64" not in saudar(banco)


def test_login_novo_tem_perfil_e_audio_proprios(banco):
    anterior = saudar(banco)
    with SessionLocal() as db:
        db.query(Conta).first().usuario = "arquiteto"
        db.commit()
    atual = saudar(banco)
    assert atual["perfil"] != anterior["perfil"] and atual["cache_id"] != anterior["cache_id"]
    assert "arquiteto" in atual["texto"] and "jeff" not in atual["texto"]


def test_modelo_novo_separa_cache_e_amostra_nao_troca_voz_ativa(banco, monkeypatch):
    primeiro = saudar(banco)
    fala.sintetizar("Amostra", "whatsapp", id_voz="OUTRA")
    assert catalogo(banco)["perfil"] == primeiro["perfil"]
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_v4_turbo")
    outro = saudar(banco)
    assert outro["perfil"] != primeiro["perfil"] and outro["cache_id"] != primeiro["cache_id"]


def test_saudacao_sem_provedor_devolve_frase_sem_ia(banco, monkeypatch):
    from nucleo import gemini
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "")
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: pytest.fail("Saudação não usa Gemini"))
    d = saudar(banco)
    assert "jeff" in d["falar"] and "audio_base64" not in d and banco[2] == []


def test_pedidos_simultaneos_geram_um_unico_audio(banco):
    # Mesmo usuário/voz/modelo/texto, sem confundir a trava do cache com a janela HTTP.
    with ThreadPoolExecutor(max_workers=4) as executor:
        audios = list(executor.map(lambda _: fala.sintetizar("Oi, jeff.", "whatsapp", guardar=True), range(4)))
    assert all(a["cache_id"] == audios[0]["cache_id"] for a in audios)
    assert len(banco[2]) == 1


def test_saudacoes_exigem_chave_e_revogacao_bloqueia(banco):
    c, h, *_ = banco
    assert c.get("/api/bella/saudacoes").status_code == 401
    assert c.post("/api/bella/saudacao", json={"id": 0}).status_code == 401
    c.delete("/api/conta/bella")
    assert c.get("/api/bella/saudacoes", headers=h).status_code == 401
    assert c.post("/api/bella/saudacao", headers=h, json={"id": 0}).status_code == 401


@pytest.mark.parametrize("id_", [-1, 20, "../../arquivo"])
def test_so_aceita_frases_do_catalogo(banco, id_):
    c, h, *_ = banco
    assert c.post("/api/bella/saudacao", headers=h, json={"id": id_}).status_code == 422
    assert banco[2] == []
