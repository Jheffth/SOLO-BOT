"""Os adaptadores de integracao/, importados com Finances e Rotinas de mentira."""
import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent / "integracao"


class U:
    def __init__(self, id, nome, ativo=True):
        self.id, self.nome, self.login, self.ativo = id, nome, nome.lower(), ativo


class DB:
    def __init__(self, usuarios):
        self.u = {u.id: u for u in usuarios}

    def get(self, _cls, i):
        return self.u.get(i)


def _falsos(monkeypatch, sistema):
    db = DB([U(4, "Jefferson"), U(9, "Inativo", ativo=False)])
    mods = {
        "database": types.SimpleNamespace(Usuario=U, get_db=lambda: db),
        "auth": types.ModuleType("auth"),
        "auth.router": types.SimpleNamespace(get_usuario_atual=lambda: db.u[4]),
    }
    if sistema == "finances":
        nucleo = types.SimpleNamespace(responder=lambda db, canal, origem, u, texto: f"{canal}|{origem}|{u.nome}|{texto}")
        mods["bot"] = types.SimpleNamespace(nucleo=nucleo)
        mods["bot.nucleo"] = nucleo
    else:
        class Canal:
            nome = "?"
            def __init__(self, origem, rotulo=None):
                self.origem, self.rotulo = str(origem), rotulo or str(origem)

        def processar(canal, texto, db):
            assert canal.usuario.id == 4
            canal.enviar(f"dia de {canal.usuario.nome}: {texto}", [{"titulo": "Banho", "acoes": [{"rotulo": "✅", "dados": "ok|r|1"}]}])

        def agir(db, u, canal, dados):
            return (dados == "ok|r|1", "Concluída!", "🎉 +40 XP" if dados == "ok|r|1" else None)

        conversa = types.SimpleNamespace(Canal=Canal, processar=processar, agir=agir, mostrar_blocos=None)
        mods["motors"] = types.SimpleNamespace(conversa=conversa)
        mods["motors.conversa"] = conversa
    for k, v in mods.items():
        monkeypatch.setitem(sys.modules, k, v)
    monkeypatch.syspath_prepend(str(RAIZ / "comum"))
    monkeypatch.syspath_prepend(str(RAIZ / sistema))
    monkeypatch.setenv("BOT_SERVICE_TOKEN", "segredo-servico")
    monkeypatch.setenv("SOLO_BOT_URL", "https://solobot.test")
    monkeypatch.setenv("SOLO_BOT_APP", "fin" if sistema == "finances" else "rot")
    monkeypatch.delitem(sys.modules, "solobot_ponte", raising=False)
    spec = importlib.util.spec_from_file_location(f"solobot_{sistema}", RAIZ / sistema / "routers" / "solobot.py")
    rota = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rota)
    app = FastAPI()
    app.include_router(rota.publico)
    app.include_router(rota.interno)
    return TestClient(app), importlib.import_module("solobot_ponte")


H = {"X-Solo-Token": "segredo-servico"}


@pytest.mark.parametrize("sistema", ["finances", "rotinas"])
def test_conectar_e_resgatar(monkeypatch, sistema):
    c, ponte = _falsos(monkeypatch, sistema)
    url = c.post("/api/solobot/conectar").json()["url"]
    assert url.startswith("https://solobot.test/conectar?app=")
    from urllib.parse import parse_qs, urlparse
    codigo = parse_qs(urlparse(url).query)["codigo"][0]
    assert len(codigo) <= 128
    assert c.post("/interno/bot/resgatar", json={"codigo": codigo}).status_code == 403   # sem token
    r = c.post("/interno/bot/resgatar", headers=H, json={"codigo": codigo})
    assert r.json() == {"usuario_id": "4", "nome": "Jefferson"}
    assert c.post("/interno/bot/resgatar", headers=H, json={"codigo": codigo}).status_code == 404  # uso único
    falso = codigo.replace("4.", "9.", 1)
    assert c.post("/interno/bot/resgatar", headers=H, json={"codigo": falso}).status_code == 404  # assinatura


def test_codigo_expirado(monkeypatch):
    c, ponte = _falsos(monkeypatch, "finances")
    monkeypatch.setattr(ponte, "VALIDADE", -1)
    codigo = ponte.gerar_codigo(4)
    assert ponte.resgatar(codigo) is None


def test_finances_mensagem(monkeypatch):
    c, _ = _falsos(monkeypatch, "finances")
    r = c.post("/interno/bot/mensagem", headers=H, json={"usuario_id": "4", "canal": "whatsapp", "origem": "solo:1:whatsapp", "texto": "60 uber"})
    assert r.json()["mensagens"][0]["texto"] == "WHATSAPP|solo:1:whatsapp|Jefferson|60 uber"
    r = c.post("/interno/bot/mensagem", headers=H, json={"usuario_id": "9", "texto": "x"})
    assert r.json()["desvinculado"] is True


def test_rotinas_mensagem_e_acao(monkeypatch):
    c, _ = _falsos(monkeypatch, "rotinas")
    r = c.post("/interno/bot/mensagem", headers=H, json={"usuario_id": "4", "texto": "/hoje"}).json()
    assert r["mensagens"][0]["texto"] == "dia de Jefferson: /hoje"
    assert r["mensagens"][0]["opcoes"][0]["acoes"][0]["dados"] == "ok|r|1"
    r = c.post("/interno/bot/acao", headers=H, json={"usuario_id": "4", "dados": "ok|r|1"}).json()
    assert r == {"mensagens": [{"texto": "🎉 +40 XP", "opcoes": []}], "curta": "Concluída!"}
    r = c.post("/interno/bot/acao", headers=H, json={"usuario_id": "4", "dados": "ok|r|999"}).json()
    assert r["mensagens"][0]["texto"].startswith("⚠️")
