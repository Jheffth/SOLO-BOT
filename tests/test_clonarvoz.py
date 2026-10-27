"""/clonarvoz: o próximo áudio da conta administradora vira uma voz clonada no VoiceStudio."""
import config
from canais import telegram
from nucleo import voicestudio, voz
from test_audio import _voz_tg
from test_fluxos import _ligar_telegram, _tg


def _admin(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Arq", "usuario": "arq", "email": "arquiteto@solo.dev",
                                                  "senha": "12345678"})
    assert r.json()["admin"] is True
    return cliente


def _preparar(monkeypatch, resultado=None):
    criados = []
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "https://voice.internal")
    monkeypatch.setattr(telegram, "baixar", lambda fid: b"AMOSTRA")
    monkeypatch.setattr(voz, "transcrever", lambda c, m: (_ for _ in ()).throw(AssertionError("não é para transcrever")))

    def criar(nome, conteudo, mime):
        criados.append((nome, conteudo, mime))
        return resultado or {"ok": True, "id": "ab12cd34", "nome": nome}
    monkeypatch.setattr(voicestudio, "criar_perfil", criar)
    return criados


def test_admin_clona_a_voz_com_o_proximo_audio(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    criados = _preparar(monkeypatch)
    _ligar_telegram(c)
    _tg(c, "/clonarvoz Bella Casa")
    assert "Bella Casa" in caixa[-1][2] and "10 a 60 segundos" in caixa[-1][2]
    _voz_tg(c, duracao=20)
    assert criados == [("Bella Casa", b"AMOSTRA", "audio/ogg")]
    assert "Criando a voz" in caixa[-2][2]                      # aviso imediato, antes da espera
    assert "criada" in caixa[-1][2] and "Bella Casa" in caixa[-1][2]
    _voz_tg(c, duracao=20)                         # só vale UM áudio: o seguinte volta ao fluxo normal
    assert len(criados) == 1


def test_amostra_curta_pede_outra_sem_gastar_o_pedido(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    criados = _preparar(monkeypatch)
    _ligar_telegram(c)
    _tg(c, "/clonarvoz Teste")
    _voz_tg(c, duracao=2)
    assert criados == [] and "curto" in caixa[-1][2]
    _voz_tg(c, duracao=15)
    assert len(criados) == 1


def test_falha_do_voicestudio_e_explicada(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    _preparar(monkeypatch, {"ok": False, "erro": "não consegui falar com o VoiceStudio (computador desligado ou sem conexão?)"})
    _ligar_telegram(c)
    _tg(c, "/clonarvoz Teste")
    _voz_tg(c, duracao=15)
    assert "computador desligado" in caixa[-1][2] and "/clonarvoz Teste" in caixa[-1][2]


def test_conta_comum_nao_clona(logado, caixa, monkeypatch):
    criados = _preparar(monkeypatch)
    _ligar_telegram(logado)
    _tg(logado, "/clonarvoz Teste")
    assert "administradora" in caixa[-1][2]
    assert criados == []


def test_sem_nome_cancelar_e_sem_voicestudio(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    criados = _preparar(monkeypatch)
    _ligar_telegram(c)
    _tg(c, "/clonarvoz")
    assert "Diga o nome" in caixa[-1][2]
    _tg(c, "/clonarvoz Um")
    _tg(c, "/clonarvoz cancelar")
    assert "cancelei" in caixa[-1][2]
    monkeypatch.setattr(voz, "transcrever", lambda c_, m: "oi")
    _voz_tg(c, duracao=15)
    assert criados == []                            # cancelado: o áudio segue o fluxo normal
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "")
    _tg(c, "/clonarvoz Outro")
    assert "não está configurado" in caixa[-1][2]


def test_criacao_usa_tempo_proprio_maior_que_o_da_fala(monkeypatch):
    import httpx
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "https://voice.internal")
    monkeypatch.setattr(config, "VOICESTUDIO_TIMEOUT", 35)
    monkeypatch.setattr(config, "VOICESTUDIO_CLONE_TIMEOUT", 240)
    visto = {}

    class Cli:
        def __init__(self, *a, **k): visto.update(k)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return httpx.Response(200, json={"id": "x1"})
    monkeypatch.setattr(voicestudio.httpx, "Client", Cli)
    assert voicestudio.criar_perfil("A", b"a", "audio/ogg")["ok"]
    assert visto["timeout"].read == 240
