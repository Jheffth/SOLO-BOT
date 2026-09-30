"""Fala central: o Solo Bot responde por voz para qualquer sistema."""
import pytest

import config
from nucleo import fala
from test_fluxos import TG, _ligar_telegram, _tg


@pytest.fixture()
def voz_falsa(monkeypatch):
    from nucleo import gemini
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(gemini, "gerar", lambda instrucao, texto, **k:
                        "Você tem uma missão hoje: o banho." if "Itens com botões" in texto else None)
    ditos = []

    def sintetizar(texto, canal):
        ditos.append((texto, canal))
        return {"base64": "Vk9a", "mime": "audio/ogg" if canal == "telegram" else "audio/mpeg"}
    monkeypatch.setattr(fala, "sintetizar", sintetizar)
    return ditos


def _audio_tg(c, monkeypatch, uid=[40000]):
    from canais import telegram
    from nucleo import voz
    monkeypatch.setattr(telegram, "baixar", lambda f: b"OGG")
    monkeypatch.setattr(voz, "transcrever", lambda c_, m: "o que falta hoje")
    uid[0] += 1
    return c.post("/api/telegram/webhook", headers=TG, json={"update_id": uid[0], "message": {
        "chat": {"id": 777, "type": "private"}, "voice": {"file_id": "F", "duration": 3}}})


def _preparar(logado):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)


def test_texto_falavel_limpa_e_corta():
    t = "🎤 _“x”_\n\n⚔️ *Rotinas*\n✅ Despesa de *R$ 1.318,40*\n*1.* ✅ — Banho\n_Responda com o número._"
    assert fala.texto_falavel(t) == "Despesa de 1318 reais e 40 centavos."   # selo e eco ficam de fora
    assert fala.texto_falavel("a" * 600) is None


def test_padrao_fala_so_quando_manda_audio(logado, sistemas, caixa, voz_falsa, monkeypatch):
    _preparar(logado)
    _tg(logado, "/rot hoje")
    assert voz_falsa == []                                # texto → texto
    _audio_tg(logado, monkeypatch)
    assert voz_falsa and voz_falsa[-1][1] == "telegram"   # áudio → voz
    assert caixa[-1] == ("voz-telegram", "777", b"VOZ", "audio/ogg")
    assert voz_falsa[-1][0] == "Você tem uma missão hoje: o banho."   # lista → resumo falado pela IA


def test_sempre_e_nunca(logado, sistemas, caixa, voz_falsa, monkeypatch):
    _preparar(logado)
    _tg(logado, "/voz sempre")
    assert any(e[0] == "telegram" and "falo sempre" in e[2] for e in caixa[-2:])
    n = len(voz_falsa)
    _tg(logado, "/rot hoje")
    assert len(voz_falsa) == n + 1
    _tg(logado, "/voz off")
    n = len(voz_falsa)
    _audio_tg(logado, monkeypatch)
    assert len(voz_falsa) == n and caixa[-1][0] == "telegram"


def test_usa_o_falado_do_sistema(logado, sistemas, caixa, voz_falsa, monkeypatch):
    from conftest import Resp
    orig = sistemas.__call__

    def com_falado(url, token, corpo, timeout=None):
        if url.endswith("/mensagem"):
            return Resp(200, {"mensagens": [{"texto": "✅ *R$ 45,00* lançado", "falado": "Lancei quarenta e cinco reais."}]})
        return orig(url, token, corpo, timeout)
    import nucleo.modulos as mm
    monkeypatch.setattr(mm, "_post", com_falado)
    _preparar(logado)
    _audio_tg(logado, monkeypatch)
    assert voz_falsa[-1][0] == "Lancei quarenta e cinco reais."


def test_painel_troca_preferencia(logado):
    assert logado.get("/api/auth/eu").json()["voz"] == "audio"
    assert logado.patch("/api/conta", json={"voz": "sempre"}).json()["voz"] == "sempre"
    assert logado.patch("/api/conta", json={"voz": "gritando"}).status_code == 422


def test_aviso_nao_e_falado(logado, sistemas, caixa, voz_falsa):
    _preparar(logado)
    logado.patch("/api/conta", json={"voz": "sempre"})
    logado.post("/interno/enviar", headers={"X-Solo-Token": "tok-rot"}, json={"usuario_id": "1", "texto": "☀️ Bom dia"})
    assert voz_falsa == []


def test_sintetizar_cai_no_flash_e_na_chave_reserva(monkeypatch):
    import httpx
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k1")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "k2")
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_v4_turbo")
    monkeypatch.setattr(config, "ELEVENLABS_VOICE_ID", "V")
    pedidos = []

    class Cliente:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, json, headers):
            pedidos.append((headers["xi-api-key"], json["model_id"], json["text"]))
            if json["model_id"] != "eleven_flash_v2_5":
                return httpx.Response(402)
            if headers["xi-api-key"] == "k1":
                return httpx.Response(401)
            return httpx.Response(200, content=b"OK")
    monkeypatch.setattr(fala.httpx, "Client", Cliente)
    r = fala.sintetizar("[animado] Oi", "whatsapp")
    assert r == {"base64": "T0s=", "mime": "audio/mpeg"}
    assert pedidos[1] == ("k1", "eleven_flash_v2_5", "Oi")      # tags fora no Flash
    assert pedidos[-1][0] == "k2"


def test_resposta_curta_nao_chama_a_ia(monkeypatch):
    from nucleo import gemini
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: pytest.fail("não precisava de IA"))
    msgs = [{"texto": "⚔️ *Rotinas*\n✅ Missão concluída! *+40 XP*", "opcoes": []}]
    assert fala.o_que_falar(msgs) == "Missão concluída! +40 XP."


def test_lista_vira_resumo_com_os_itens_dos_botoes(monkeypatch):
    from nucleo import gemini
    vistos = []
    monkeypatch.setattr(gemini, "gerar", lambda instrucao, texto, **k: vistos.append(texto) or "Faltam duas missões: leitura e banho.")
    msgs = [{"texto": "⚔️ *Rotinas*\n📅 Hoje · 3 missões", "opcoes": [
        {"titulo": "Leitura", "acoes": [{"rotulo": "✅ Concluir", "dados": "rot:ok|r|1"}]},
        {"titulo": "Banho", "acoes": [{"rotulo": "▶️ Iniciar", "dados": "rot:ini|r|2"}]}]}]
    assert fala.o_que_falar(msgs) == "Faltam duas missões: leitura e banho."
    assert "- Leitura (✅ Concluir)" in vistos[0] and "- Banho (▶️ Iniciar)" in vistos[0]


def test_sem_gemini_lista_nao_e_falada(monkeypatch):
    from nucleo import gemini
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: None)
    msgs = [{"texto": "x", "opcoes": [{"titulo": "Banho", "acoes": [{"rotulo": "✅", "dados": "d"}]}]}]
    assert fala.o_que_falar(msgs) is None


def test_falado_do_sistema_tem_prioridade(monkeypatch):
    from nucleo import gemini
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: pytest.fail("não precisava de IA"))
    assert fala.o_que_falar([{"texto": "longo " * 200, "falado": "Pronto."}]) == "Pronto."
