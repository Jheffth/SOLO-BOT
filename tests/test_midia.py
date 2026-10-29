"""Foto e vídeo nas respostas dos sistemas: validação, entrega no Telegram e no WhatsApp, falha sem derrubar o texto."""
import base64

import pytest

from canais import entrega, evolution, midia, telegram
from conftest import Resp
from nucleo import modulos
from test_fluxos import _ligar_telegram, _tg, _wa

JPG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64
b64 = lambda x: base64.b64encode(x).decode()   # noqa: E731


def _m(conteudo=JPG, mime="image/jpeg", **extra):
    return {"base64": b64(conteudo), "mime": mime, **extra}


# ── validação ────────────────────────────────────────────────────
def test_validar_aceita_os_formatos_e_normaliza():
    for conteudo, mime, tipo in ((JPG, "image/jpeg", "imagem"), (PNG, "image/png", "imagem"),
                                 (WEBP, "image/webp", "imagem"), (MP4, "video/mp4", "video")):
        v = midia.validar(_m(conteudo, mime, legenda="  oi  ", spoiler=True))
        assert v and v["tipo"] == tipo and v["legenda"] == "oi" and v["spoiler"] is True
    assert midia.validar(_m(JPG, "IMAGE/JPG; charset=x"))["mime"] == "image/jpeg"
    assert midia.validar(_m())["spoiler"] is False and midia.validar(_m())["legenda"] == ""


@pytest.mark.parametrize("ruim", [
    None, "texto", [], {}, {"mime": "image/jpeg"}, {"base64": "", "mime": "image/jpeg"},
    {"base64": "não é base64!!", "mime": "image/jpeg"},
    {"base64": b64(JPG), "mime": "application/x-msdownload"},
    {"base64": b64(b"MZ" + b"0" * 64), "mime": "image/jpeg"},              # um executável fingindo ser foto
    {"base64": b64(PNG), "mime": "image/jpeg"},                           # conteúdo não bate com o tipo
    {"base64": b64(JPG), "mime": "video/mp4"},
    {"base64": b64(b"\xff\xd8\xff" + b"0" * (midia.IMAGEM_MAX + 1)), "mime": "image/jpeg"},
    {"base64": b64(MP4 + b"0" * midia.VIDEO_MAX), "mime": "video/mp4"},
])
def test_validar_recusa_o_que_nao_e_midia_boa(ruim):
    assert midia.validar(ruim) is None


def test_legenda_longa_e_cortada_e_tipo_errado_ignorado():
    assert len(midia.validar(_m(legenda="x" * 5000))["legenda"]) == midia.LEGENDA_MAX
    assert midia.validar(_m(legenda=123))["legenda"] == ""


# ── entrega ──────────────────────────────────────────────────────
def _sistema_com_midia(monkeypatch, sistemas, midia_resposta):
    def post(url, token, corpo, timeout=None):
        if url.rsplit("/", 1)[1] == "mensagem" and "audio_base64" not in corpo:
            return Resp(200, {"mensagens": [{"texto": "olha isto", "midia": midia_resposta}]})
        return sistemas(url, token, corpo, timeout)
    monkeypatch.setattr(modulos, "_post", post)


def test_telegram_recebe_texto_depois_foto_com_legenda_e_spoiler(logado, sistemas, caixa, monkeypatch):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _sistema_com_midia(monkeypatch, sistemas, _m(JPG, "image/jpeg", legenda="Praia", spoiler=True))
    _tg(logado, "/rot hoje")
    tipos = [c[0] for c in caixa[-2:]]
    assert tipos == ["telegram", "midia-telegram"]
    assert "olha isto" in caixa[-2][2]
    assert caixa[-1][2] == ("image/jpeg", "Praia", True) and caixa[-1][3] == JPG


def test_telegram_video(logado, sistemas, caixa, monkeypatch):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _sistema_com_midia(monkeypatch, sistemas, _m(MP4, "video/mp4"))
    _tg(logado, "/rot hoje")
    assert caixa[-1][0] == "midia-telegram" and caixa[-1][2][0] == "video/mp4" and caixa[-1][3] == MP4


def test_whatsapp_recebe_a_midia_depois_do_texto(logado, sistemas, caixa, monkeypatch):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    r = logado.post("/api/conta/canais/whatsapp/codigo").json()
    _wa(logado, r["mensagem"])
    _sistema_com_midia(monkeypatch, sistemas, _m(PNG, "image/png", legenda="Oi"))
    _wa(logado, "/rot hoje")
    assert [c[0] for c in caixa[-2:]] == ["whatsapp", "midia-whatsapp"]
    m = caixa[-1][2]
    assert m["mime"] == "image/png" and m["legenda"] == "Oi" and m["tipo"] == "imagem" and m["base64"] == b64(PNG)


def test_midia_invalida_do_sistema_nao_derruba_o_texto(logado, sistemas, caixa, monkeypatch):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _sistema_com_midia(monkeypatch, sistemas, {"base64": b64(b"MZ" + b"0" * 64), "mime": "image/jpeg"})
    _tg(logado, "/rot hoje")
    assert "olha isto" in caixa[-1][2] and not any(c[0] == "midia-telegram" for c in caixa)


def test_falha_no_envio_da_midia_nao_levanta_nem_apaga_a_voz(monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("rede")
    monkeypatch.setattr(telegram, "enviar_midia", quebra)
    monkeypatch.setattr(evolution, "enviar_midia", quebra)
    v = midia.validar(_m())
    assert entrega._midia("telegram", "1", v) is False
    assert entrega._midia("whatsapp", "1", v) is False
    assert entrega._midia("telegram", "1", None) is False


def test_whatsapp_so_conta_como_enviada_com_id_da_mensagem(monkeypatch):
    v = midia.validar(_m())
    monkeypatch.setattr(evolution, "enviar_midia", lambda j, m: {"key": {"id": "ABC"}})
    assert entrega._midia("whatsapp", "1", v) is True
    monkeypatch.setattr(evolution, "enviar_midia", lambda j, m: {"erro": "falha de rede"})
    assert entrega._midia("whatsapp", "1", v) is False


# ── transporte ───────────────────────────────────────────────────
def test_evolution_monta_o_pedido_de_midia(monkeypatch):
    visto = {}

    def chamar(metodo, caminho, corpo=None, timeout=15):
        visto.update(metodo=metodo, caminho=caminho, corpo=corpo, timeout=timeout)
        return 201, {"key": {"id": "Z"}}
    monkeypatch.setattr(evolution, "_chamar", chamar)
    r = evolution.enviar_midia("5561988887777@s.whatsapp.net", midia.validar(_m(MP4, "video/mp4", legenda="v")))
    assert r == {"key": {"id": "Z"}} and visto["caminho"].startswith("/message/sendMedia/")
    c = visto["corpo"]
    assert c["number"] == "5561988887777" and c["mediatype"] == "video" and c["mimetype"] == "video/mp4"
    assert c["caption"] == "v" and c["fileName"] == "video.mp4" and c["media"] == b64(MP4) and visto["timeout"] >= 60
    monkeypatch.setattr(evolution, "_chamar", lambda *a, **k: (0, {}))
    assert evolution.enviar_midia("5561@s.whatsapp.net", midia.validar(_m())) == {"erro": "falha de rede"}


def test_telegram_escolhe_o_metodo_e_cai_para_arquivo(monkeypatch):
    import config
    import httpx
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123:abc")
    chamadas = []

    class Cliente:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def post(self, url, data=None, files=None):
            chamadas.append((url.rsplit("/", 1)[1], dict(data), list(files)))
            return type("R", (), {"status_code": 400 if url.endswith("sendPhoto") else 200})()
    monkeypatch.setattr(httpx, "Client", Cliente)
    assert telegram.enviar_midia("9", JPG, "image/jpeg", "oi", True) is True
    assert [c[0] for c in chamadas] == ["sendPhoto", "sendDocument"]          # foto recusada → arquivo
    assert chamadas[0][1]["has_spoiler"] == "true" and "has_spoiler" not in chamadas[1][1]
    chamadas.clear()
    assert telegram.enviar_midia("9", MP4, "video/mp4", "v") is True
    assert chamadas[0][0] == "sendVideo" and chamadas[0][1]["supports_streaming"] == "true" and chamadas[0][2] == ["video"]
