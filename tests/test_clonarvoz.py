"""/clonarvoz: o próximo áudio da conta administradora vira uma voz clonada no VoiceStudio."""
import config
from canais import telegram
from nucleo import voicestudio, voz
from test_audio import _voz_tg
from test_fluxos import _ligar_telegram, _tg


VOZES = [{"voice_id": "a1", "nome": "Bella Original"}, {"voice_id": "b2", "nome": "Jefferson"}]


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
    monkeypatch.setattr(voicestudio, "listar_vozes", lambda forcar=False: list(VOZES))
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
    assert "computador desligado" in caixa[-1][2] and "/clonarvoz repetir" in caixa[-1][2]


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


def _gravada(cliente):
    import database
    with database.SessionLocal() as db:
        return database.ler_config(voicestudio.CHAVE_VOZ)


def test_vozes_lista_numerada_e_marca_a_que_esta_em_uso(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    _preparar(monkeypatch)
    monkeypatch.setattr(voicestudio, "voz_id", lambda: "b2")
    _ligar_telegram(c)
    _tg(c, "/vozes")
    t = caixa[-1][2]
    assert "1. Bella Original" in t and "2. Jefferson" in t and "em uso" in t.split("2. Jefferson")[1].splitlines()[0]
    assert "motor de voz" in t                                  # o motor padrão não é VoiceStudio


def test_usarvoz_por_numero_nome_e_ambiguidade(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    _preparar(monkeypatch)
    _ligar_telegram(c)
    _tg(c, "/usarvoz 2")
    assert "Jefferson" in caixa[-1][2] and _gravada(c) == "b2"
    _tg(c, "/usarvoz bella")                                    # sem acento/maiúscula, por trecho
    assert _gravada(c) == "a1"
    _tg(c, "/usarvoz inexistente")
    assert "Não achei" in caixa[-1][2] and _gravada(c) == "a1"
    VOZES.append({"voice_id": "c3", "nome": "Bella Segunda"})
    try:
        _tg(c, "/usarvoz bella")
        assert "Mais de uma" in caixa[-1][2] and _gravada(c) == "a1"
    finally:
        VOZES.pop()


def test_testarvoz_manda_texto_e_audio(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    _preparar(monkeypatch)
    monkeypatch.setattr(voicestudio, "voz_id", lambda: "a1")
    monkeypatch.setattr(voicestudio, "disponivel", lambda: True)
    pedidos = []
    monkeypatch.setattr(voicestudio, "sintetizar", lambda t, canal, **k: pedidos.append((t, canal)) or {"base64": "QUJD", "mime": "audio/ogg"})
    _ligar_telegram(c)
    _tg(c, "/testarvoz oi gente")
    assert pedidos == [("oi gente", "telegram")]
    assert caixa[-2][2].startswith("🎙️ Voz *Bella Original*") and caixa[-1][0] == "voz-telegram"
    monkeypatch.setattr(voicestudio, "sintetizar", lambda *a, **k: None)
    _tg(c, "/testarvoz")
    assert "não gerou" in caixa[-1][2]


def test_conta_comum_nao_mexe_nas_vozes(logado, caixa, monkeypatch):
    _preparar(monkeypatch)
    _ligar_telegram(logado)
    for cmd in ("/vozes", "/usarvoz 1", "/testarvoz"):
        _tg(logado, cmd)
        assert "administradora" in caixa[-1][2]


def test_repetir_usa_a_amostra_guardada_depois_de_falha(cliente, caixa, monkeypatch):
    from nucleo import roteador
    c = _admin(cliente)
    roteador._AMOSTRAS.clear()
    respostas = [{"ok": False, "erro": "o VoiceStudio demorou demais"}, {"ok": True, "id": "n1", "nome": "Nova"}]
    criados = []
    _preparar(monkeypatch)
    monkeypatch.setattr(voicestudio, "criar_perfil", lambda n, b, m: criados.append((n, b)) or respostas.pop(0))
    _ligar_telegram(c)
    _tg(c, "/clonarvoz Nova")
    _voz_tg(c, duracao=20)
    assert "/clonarvoz repetir" in caixa[-1][2]
    _tg(c, "/clonarvoz repetir")                                # sem reenviar o áudio
    assert criados == [("Nova", b"AMOSTRA"), ("Nova", b"AMOSTRA")]
    assert "criada" in caixa[-1][2]
    _tg(c, "/clonarvoz repetir")
    assert "Não tenho nenhuma amostra" in caixa[-1][2]


def test_nao_duplica_voz_com_o_mesmo_nome(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    criados = _preparar(monkeypatch)
    _ligar_telegram(c)
    _tg(c, "/clonarvoz jefferson")                              # já existe "Jefferson"
    _voz_tg(c, duracao=20)
    assert criados == [] and "Já existe" in caixa[-1][2] and "/usarvoz Jefferson" in caixa[-1][2]
