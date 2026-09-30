"""Parear o número da Evolution: os estados que travavam o QR."""
from canais import evolution


def _evolution_falsa(monkeypatch, estados, connect=(200, {"base64": "QUJD", "pairingCode": "X1"})):
    chamadas = []
    fila = list(estados)

    def chamar(metodo, caminho, corpo=None, timeout=15):
        chamadas.append((metodo, caminho.split("/")[1] + "/" + caminho.split("/")[2], corpo))
        if "connectionState" in caminho:
            e = fila.pop(0) if len(fila) > 1 else fila[0]
            return e if isinstance(e, tuple) else (200, {"instance": {"state": e}})
        if "/instance/connect/" in caminho:
            return connect
        return 200, {}
    monkeypatch.setattr(evolution, "_chamar", chamar)
    return chamadas


def test_instancia_travada_em_close_e_recriada(monkeypatch):
    ch = _evolution_falsa(monkeypatch, ["close", "connecting"])
    r = evolution.parear("http://solo_bot:8000/api/whatsapp/webhook/s")
    assert r["qr"] == "data:image/png;base64,QUJD" and r["estado"] == "connecting"
    feitos = [c[1] for c in ch]
    assert "instance/delete" in feitos and "instance/create" in feitos and "webhook/set" in feitos
    webhook = next(c[2] for c in ch if c[1] == "webhook/set")["webhook"]
    assert webhook["url"].endswith("/s") and "QRCODE_UPDATED" in webhook["events"]


def test_instancia_inexistente_e_criada_sem_apagar(monkeypatch):
    ch = _evolution_falsa(monkeypatch, [(404, {}), "connecting"])
    assert evolution.parear("u")["qr"]
    feitos = [c[1] for c in ch]
    assert "instance/create" in feitos and "instance/delete" not in feitos


def test_connecting_nao_recria(monkeypatch):
    ch = _evolution_falsa(monkeypatch, ["connecting"])
    evolution.parear("u")
    assert not any(c[1] in ("instance/delete", "instance/create") for c in ch)


def test_ja_conectado_so_reaplica_webhook(monkeypatch):
    ch = _evolution_falsa(monkeypatch, ["open"])
    r = evolution.parear("u")
    assert r["estado"] == "open" and "qr" not in r and "já está conectado" in r["detalhe"]
    assert [c[1] for c in ch if c[0] != "GET"] == ["webhook/set"]


def test_chave_errada_e_evolution_fora(monkeypatch):
    _evolution_falsa(monkeypatch, [(401, {})])
    assert evolution.parear("u")["estado"] == "chave_invalida"
    _evolution_falsa(monkeypatch, [(0, {})])
    assert "Não alcancei" in evolution.parear("u")["detalhe"]


def test_qr_so_pelo_webhook(cliente, monkeypatch):
    from routers.webhooks import ULTIMO_QR
    ULTIMO_QR["base64"] = None
    cliente.post("/api/whatsapp/webhook/wa-secreto", json={"event": "qrcode.updated", "data": {"qrcode": {"base64": "WFla"}}})
    assert ULTIMO_QR["base64"] == "data:image/png;base64,WFla"


def test_numero_vem_da_evolution_quando_falta_no_env(monkeypatch):
    import config
    monkeypatch.setattr(config, "WHATSAPP_NUMERO", "")
    monkeypatch.setattr(evolution, "_NUMERO_CACHE", {"valor": None})
    monkeypatch.setattr(evolution, "_chamar", lambda *a, **k: (200, [{"ownerJid": "5561912345678@s.whatsapp.net"}]))
    assert evolution.numero() == "5561912345678"
    assert "wa.me/5561912345678?text=SOLO" in evolution.link_wa("SOLO 123456")


def test_sem_numero_mensagem_diz_o_que_fazer(logado, monkeypatch):
    import config
    monkeypatch.setattr(config, "WHATSAPP_NUMERO", "")
    monkeypatch.setattr(evolution, "_NUMERO_CACHE", {"valor": None})
    monkeypatch.setattr(evolution, "_chamar", lambda *a, **k: (200, [{"ownerJid": None}]))
    r = logado.post("/api/conta/canais/whatsapp/codigo")
    assert r.status_code == 503 and "ler o QR" in r.json()["detail"]
