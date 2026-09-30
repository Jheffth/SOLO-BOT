import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp()
os.environ.update({
    "AMBIENTE": "test",
    "DATABASE_URL": f"sqlite:///{_TMP}/teste.db",
    "TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_BOT_USERNAME": "SoloBot", "TELEGRAM_SECRET": "tg-secreto",
    "EVOLUTION_API_KEY": "evo", "EVOLUTION_WEBHOOK_SECRET": "wa-secreto", "WHATSAPP_NUMERO": "5561999990000",
    "ADMIN_EMAILS": "arquiteto@solo.dev",
    "SOLO_MODULOS": json.dumps([
        {"chave": "fin", "nome": "Solo Finances", "emoji": "💰", "url": "http://fin", "token": "tok-fin",
         "painel": "https://fin.example/bots"},
        {"chave": "rot", "nome": "Solo Rotinas", "emoji": "⚔️", "url": "http://rot", "token": "tok-rot"},
    ]),
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
from canais import evolution, telegram  # noqa: E402
from nucleo import modulos  # noqa: E402


class Resp:
    def __init__(self, status, dados):
        self.status_code, self._d, self.text = status, dados, json.dumps(dados)

    def json(self):
        return self._d


class SistemasFalsos:
    """Finances e Rotinas de mentira: guardam o que receberam e respondem eco."""

    def __init__(self):
        self.codigos = {"fin": {"CODFIN1": ("4", "jefferson")}, "rot": {"CODROT1": ("1", "Arquiteto")}}
        self.recebidos = []

    def __call__(self, url, token, corpo, timeout=None):
        app = url.split("//")[1].split("/")[0]
        rota = url.rsplit("/", 1)[1]
        esperado = {"fin": "tok-fin", "rot": "tok-rot"}[app]
        if token != esperado:
            return Resp(403, {"detail": "token"})
        self.recebidos.append((app, rota, corpo))
        if rota == "resgatar":
            par = self.codigos[app].pop(corpo["codigo"], None)
            return Resp(404, {}) if not par else Resp(200, {"usuario_id": par[0], "nome": par[1]})
        if rota == "mensagem" and "audio_base64" in corpo:
            return Resp(200, {"mensagens": [{"texto": f"ouvi {len(corpo['audio_base64'])} b64",
                                             "audio": {"base64": "QUJD", "mime": "audio/ogg"}}]})
        if rota == "mensagem":
            opcoes = [{"titulo": "Banho", "acoes": [{"rotulo": "✅", "dados": "ok|r|12"}]}] if app == "rot" else []
            return Resp(200, {"mensagens": [{"texto": f"eco:{corpo['texto']}", "opcoes": opcoes}]})
        if rota == "acao":
            return Resp(200, {"mensagens": [{"texto": f"feito:{corpo['dados']}"}], "curta": "ok!"})
        return Resp(200, {"ok": True})

    manifestos = {
        "fin": {"versao": "1", "comandos": [{"comando": "/saldo", "descricao": "Saldo das contas"}]},
        "rot": {"versao": "1", "comandos": [{"comando": "/hoje", "descricao": "Missões do dia"}]},
    }

    def get(self, url, token):
        app = url.split("//")[1].split("/")[0]
        if token != {"fin": "tok-fin", "rot": "tok-rot"}[app]:
            return Resp(403, {})
        return Resp(200, self.manifestos[app])


@pytest.fixture()
def sistemas(monkeypatch):
    s = SistemasFalsos()
    s.manifestos = {k: dict(v) for k, v in SistemasFalsos.manifestos.items()}
    monkeypatch.setattr(modulos, "_post", s)
    monkeypatch.setattr(modulos, "_get", s.get)
    return s


@pytest.fixture()
def caixa(monkeypatch):
    """Tudo que o bot mandaria para o Telegram e o WhatsApp."""
    enviadas = []
    monkeypatch.setattr(telegram, "enviar", lambda chat, t, teclado=None: enviadas.append(("telegram", chat, t, teclado)) or {"ok": True})
    monkeypatch.setattr(telegram, "responder_toque", lambda cid, t="": enviadas.append(("toque", cid, t, None)))
    monkeypatch.setattr(evolution, "enviar", lambda jid, t: enviadas.append(("whatsapp", jid, t, None)) or {})
    monkeypatch.setattr(telegram, "enviar_voz", lambda chat, b, mime: enviadas.append(("voz-telegram", chat, b, mime)) or True)
    monkeypatch.setattr(evolution, "enviar_audio", lambda jid, b64: enviadas.append(("voz-whatsapp", jid, b64, None)) or {})
    import config
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")          # sem voz, a não ser que o teste ligue
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "")
    return enviadas


@pytest.fixture()
def cliente():
    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    from main import app
    from routers import auth
    auth._tentativas.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def logado(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Jefferson Costa", "usuario": "jeff", "email": "j@solo.dev", "senha": "senha-forte-1"})
    assert r.status_code == 200, r.text
    return cliente
