"""Áudio: o Solo Bot ouve uma vez, para todos os sistemas."""
import pytest

from canais import evolution, telegram
from nucleo import voz
from test_fluxos import TG, _ligar_telegram, _tg

FIN = {"X-Solo-Token": "tok-fin"}
MANIFESTO_FIN_COM_AUDIO = {"versao": "1", "audio": {"recebe": True},
                           "comandos": [{"comando": "/saldo", "descricao": "Saldo"}]}


def _voz_tg(c, chat=777, uid=[20000], duracao=4):
    uid[0] += 1
    return c.post("/api/telegram/webhook", headers=TG, json={
        "update_id": uid[0], "message": {"chat": {"id": chat, "type": "private"}, "from": {"username": "jeff"},
                                         "voice": {"file_id": "F1", "duration": duracao, "mime_type": "audio/ogg"}}})


@pytest.fixture()
def ouvido(monkeypatch):
    """Transcrição de mentira e download de mentira."""
    monkeypatch.setattr(telegram, "baixar", lambda fid: b"OGG-BYTES")
    ouvidos = []

    def transcrever(conteudo, mime):
        ouvidos.append((conteudo, mime))
        return "terminei o treino"
    monkeypatch.setattr(voz, "transcrever", transcrever)
    return ouvidos


def test_sistema_sem_audio_recebe_transcricao(logado, sistemas, caixa, ouvido):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _voz_tg(logado)
    assert ouvido == [(b"OGG-BYTES", "audio/ogg")]
    app, rota, corpo = sistemas.recebidos[-1]
    assert (app, rota, corpo["texto"], corpo["via_audio"]) == ("rot", "mensagem", "terminei o treino", True)
    assert caixa[-1][2].startswith("🎤 _“terminei o treino”_\n\n⚔️ *Rotinas*")


def test_sistema_com_audio_recebe_os_bytes_e_responde_em_voz(logado, sistemas, caixa, ouvido):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/interno/manifesto", headers=FIN, json=MANIFESTO_FIN_COM_AUDIO)
    _ligar_telegram(logado)
    _voz_tg(logado)
    assert ouvido == []                                     # quem ouve é o Finances
    corpo = sistemas.recebidos[-1][2]
    assert corpo["mime"] == "audio/ogg" and "audio_base64" in corpo and "texto" not in corpo
    assert caixa[-2][2].startswith("💰 *Finances*")         # texto primeiro
    assert caixa[-1] == ("voz-telegram", "777", b"ABC", "audio/ogg")   # depois a voz


def test_hub_com_dois_sistemas_pergunta_e_guarda_a_transcricao(logado, sistemas, caixa, ouvido):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _voz_tg(logado)
    assert "Para qual sistema" in caixa[-1][2] and "terminei o treino" in caixa[-1][2]


def test_sem_chave_de_transcricao(logado, sistemas, caixa, monkeypatch):
    monkeypatch.setattr(telegram, "baixar", lambda fid: b"x")
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _voz_tg(logado)
    assert "falta a chave de transcrição" in caixa[-1][2]


def test_audio_longo_demais(logado, sistemas, caixa, ouvido):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _voz_tg(logado, duracao=300)
    assert "longo demais" in caixa[-1][2] and ouvido == []


def test_whatsapp_audio_pela_evolution(logado, sistemas, caixa, ouvido, monkeypatch):
    monkeypatch.setattr(evolution, "midia_base64", lambda k, m: {"base64": "T0dH", "mimetype": "audio/ogg; codecs=opus"})
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    r = logado.post("/api/conta/canais/whatsapp/codigo").json()
    jid = "5561988887777@s.whatsapp.net"
    ev = lambda i, from_me=False: logado.post("/api/whatsapp/webhook/wa-secreto", json={
        "event": "messages.upsert", "data": {"key": {"remoteJid": jid, "id": i, "fromMe": from_me},
                                             "message": {"audioMessage": {"seconds": 3}}}})
    logado.post("/api/whatsapp/webhook/wa-secreto", json={"event": "messages.upsert", "data": {
        "key": {"remoteJid": jid, "id": "v1", "fromMe": False}, "message": {"conversation": r["mensagem"]}}})
    ev("a1")
    assert ouvido[-1] == (b"OGG", "audio/ogg") and "terminei o treino" in caixa[-1][2]
    n = len(caixa)
    ev("a1")                                               # reentrega: ignora
    ev("a2", from_me=True)                                 # áudio do próprio aparelho: ignora
    assert len(caixa) == n


def test_transcrever_sem_motor_levanta(monkeypatch):
    monkeypatch.setattr(voz, "motores", lambda: [])
    with pytest.raises(voz.SemVoz):
        voz.transcrever(b"x", "audio/ogg")


def test_transcrever_cai_no_proximo_motor(monkeypatch):
    def ruim(c, m):
        raise RuntimeError("fora do ar")
    bom = lambda c, m: '"gastei 45 no mercado"'
    ruim.nome, bom.nome = "ruim", "bom"
    monkeypatch.setattr(voz, "motores", lambda: [ruim, bom])
    assert voz.transcrever(b"x", "audio/ogg; codecs=opus") == "gastei 45 no mercado"


@pytest.mark.parametrize("codigo,motivo", [(429, "limite de uso"), (401, "chave recusada"),
                                          (403, "acesso recusado"), (404, "modelo indisponível"),
                                          (503, "HTTP 503")])
def test_falha_transcricao_informa_status_sem_vazar_dados(monkeypatch, caplog, codigo, motivo):
    import httpx
    def falhar(c, m):
        resposta = httpx.Response(codigo, text="SEGREDO E TEXTO PESSOAL",
                                  request=httpx.Request("POST", "https://teste.invalid/?key=SEGREDO"))
        resposta.raise_for_status()
    falhar.nome = "gemini/principal"
    monkeypatch.setattr(voz, "motores", lambda: [falhar])
    with pytest.raises(voz.FalhaVoz) as erro:
        voz.transcrever(b"audio pessoal", "audio/ogg")
    assert motivo in str(erro.value) and motivo in caplog.text
    assert "SEGREDO" not in str(erro.value) + caplog.text


def test_gemini_incompleto_passa_para_reserva(monkeypatch):
    import httpx
    class Cliente:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json, headers):
            return httpx.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS",
                "content": {"parts": [{"text": "recebi R$ 9"}]}}]}, request=httpx.Request("POST", url))
    def reserva(c, m): return "recebi R$ 92,60 na conta Uber"
    reserva.nome = "gemini/reserva"
    monkeypatch.setattr(voz.httpx, "Client", Cliente)
    monkeypatch.setattr(voz, "motores", lambda: [voz._gemini("chave", "principal"), reserva])
    assert voz.transcrever(b"audio", "audio/ogg") == "recebi R$ 92,60 na conta Uber"


def test_motivo_aparece_no_chat_sem_encaminhar_ao_sistema(logado, sistemas, caixa, monkeypatch):
    import httpx
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    monkeypatch.setattr(telegram, "baixar", lambda fid: b"audio")
    def falhar(c, m): raise httpx.ReadTimeout("segredo")
    falhar.nome = "gemini/principal"
    monkeypatch.setattr(voz, "motores", lambda: [falhar])
    antes = len(sistemas.recebidos)
    _voz_tg(logado)
    assert len(sistemas.recebidos) == antes
    assert "tempo de resposta esgotado" in caixa[-1][2] and "segredo" not in caixa[-1][2]
