"""Intenção: o hub entende para qual sistema é, e traduz frase em comando."""
import pytest

from nucleo import intencao
from test_fluxos import _ligar_telegram, _tg

FIN = {"versao": "1", "comandos": [{"comando": "/saldo", "descricao": "Saldo das contas"}],
       "exemplos": ["gastei 80 almoço nubank"]}                       # aceita texto livre
ROT = {"versao": "1", "comandos": [{"comando": "/hoje", "descricao": "Tudo do dia"},
                                   {"comando": "/ok", "descricao": "Concluir uma missão"}], "exemplos": []}


@pytest.fixture()
def dois(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    logado.post("/interno/manifesto", headers={"X-Solo-Token": "tok-fin"}, json=FIN)
    logado.post("/interno/manifesto", headers={"X-Solo-Token": "tok-rot"}, json=ROT)
    _ligar_telegram(logado)
    return logado


def _ia(monkeypatch, resposta):
    chamadas = []

    def falsa(texto, sistemas, modo):
        chamadas.append((texto, modo, [s["chave"] for s in sistemas]))
        return intencao.Intencao(**resposta, via="ia") if resposta else None
    monkeypatch.setattr(intencao, "_ia", falsa)
    return chamadas


def test_frase_do_rotinas_vira_hoje(dois, sistemas, caixa, monkeypatch):
    ch = _ia(monkeypatch, {"app": "rot", "mensagem": "/hoje", "confianca": 0.95})
    _tg(dois, "Olhe nas minhas rotinas, quero que você veja o que tem para hoje.")
    assert ch and sistemas.recebidos[-1][0] == "rot" and sistemas.recebidos[-1][2]["texto"] == "/hoje"
    assert "🧭 _Entendi: Rotinas · `/hoje`_" in caixa[-1][2]
    assert "Para qual sistema" not in caixa[-1][2]


def test_lancamento_vai_ao_finances_sem_gastar_ia(dois, sistemas, caixa, monkeypatch):
    ch = _ia(monkeypatch, None)
    _tg(dois, "gastei 30 no almoço no nubank")
    assert ch == []                                         # só palavras: grátis
    assert sistemas.recebidos[-1][0] == "fin" and sistemas.recebidos[-1][2]["texto"] == "gastei 30 no almoço no nubank"


def test_na_duvida_continua_perguntando(dois, caixa, monkeypatch):
    _ia(monkeypatch, {"app": "rot", "mensagem": "/hoje", "confianca": 0.3})
    _tg(dois, "e aí, tudo certo?")
    assert "Para qual sistema" in caixa[-1][2]


def test_no_modo_rotinas_a_frase_vira_comando(dois, sistemas, caixa, monkeypatch):
    _tg(dois, "/rot hoje")
    _ia(monkeypatch, {"app": "rot", "mensagem": "/ok leitura", "confianca": 0.9})
    _tg(dois, "terminei a leitura")
    assert sistemas.recebidos[-1][2]["texto"] == "/ok leitura"


def test_no_modo_rotinas_um_gasto_troca_para_o_finances(dois, sistemas, caixa, monkeypatch):
    _tg(dois, "/rot hoje")
    _ia(monkeypatch, {"app": "fin", "mensagem": "gastei 40 no mercado", "confianca": 0.95})
    _tg(dois, "gastei 40 no mercado")
    assert sistemas.recebidos[-1][0] == "fin"
    _ia(monkeypatch, None)
    _tg(dois, "/saldo")                                     # e o modo agora é Finances
    assert sistemas.recebidos[-1][0] == "fin"


def test_sistema_de_texto_livre_recebe_a_frase_original_nao_a_reescrita(dois, sistemas, caixa, monkeypatch):
    # A IA reescreveu "Paguei 123,67 da internet." como "gastei 123.67 internet",
    # e o Finances leu R$ 12.367. Para quem entende frase solta, vai a original.
    _tg(dois, "/rot hoje")
    _ia(monkeypatch, {"app": "fin", "mensagem": "gastei 123.67 internet", "confianca": 0.95})
    _tg(dois, "Paguei 123,67 da internet.")
    assert sistemas.recebidos[-1][0] == "fin"
    assert sistemas.recebidos[-1][2]["texto"] == "Paguei 123,67 da internet."


def test_no_modo_finances_texto_livre_nao_chama_ia(dois, sistemas, monkeypatch):
    _tg(dois, "/fin saldo")
    ch = _ia(monkeypatch, None)
    _tg(dois, "35 uber nubank")
    assert ch == [] and sistemas.recebidos[-1][2]["texto"] == "35 uber nubank"


@pytest.mark.parametrize("audio", [False, True])
@pytest.mark.parametrize("modo,frase,destino,comando", [
    ("fin", "Crie a missão geral fazer a barba até meia-noite", "rot", "/criar barba"),
    ("fin", "Some R$ 25 na rotina de R$ 50 no turno da noite", "rot", "/somar noite 25"),
    ("rot", "Crie um novo banco chamado Conta 99, saldo R$ 62,53.", "fin", None),
])
def test_troca_entre_sistemas_por_texto_e_audio(dois, sistemas, caixa, monkeypatch,
                                               audio, modo, frase, destino, comando):
    from canais import telegram
    from nucleo import voz
    from test_audio import _voz_tg

    dois.post("/interno/manifesto", headers={"X-Solo-Token": "tok-fin"},
              json={**FIN, "audio": {"recebe": True}})
    # Comandos de exemplo do sistema falso: a execução continua sendo do sistema.
    dois.post("/interno/manifesto", headers={"X-Solo-Token": "tok-rot"}, json={
        **ROT, "comandos": ROT["comandos"] + [
            {"comando": "/criar", "descricao": "Criar missão"},
            {"comando": "/somar", "descricao": "Somar progresso"}]})
    _tg(dois, f"/{modo} ajuda")
    ch = _ia(monkeypatch, {"app": destino, "mensagem": comando or frase, "confianca": 0.95})
    antes = len(sistemas.recebidos)
    if audio:
        monkeypatch.setattr(telegram, "baixar", lambda fid: b"OGG-BYTES")
        monkeypatch.setattr(voz, "transcrever", lambda conteudo, mime: frase)
        _voz_tg(dois)
    else:
        _tg(dois, frase)
    assert ch and len(sistemas.recebidos) == antes + 1
    app, rota, corpo = sistemas.recebidos[-1]
    assert (app, rota, corpo["texto"]) == (destino, "mensagem", comando or frase)
    assert "audio_base64" not in corpo
    assert corpo.get("via_audio", False) == audio
    _tg(dois, "/hoje" if destino == "rot" else "/saldo")
    assert sistemas.recebidos[-1][0] == destino


@pytest.mark.parametrize("confianca", [0.3, 0.8])
def test_termos_mistos_nao_trocam_sem_confianca_alta(dois, sistemas, monkeypatch, confianca):
    _tg(dois, "/fin saldo")
    ch = _ia(monkeypatch, {"app": "rot", "mensagem": "/hoje", "confianca": confianca})
    frase = "minha meta de dinheiro"
    _tg(dois, frase)
    assert ch and sistemas.recebidos[-1][0] == "fin"
    assert sistemas.recebidos[-1][2]["texto"] == frase


def test_audio_financeiro_em_modo_finances_preserva_valor(dois, sistemas, monkeypatch):
    from canais import telegram
    from nucleo import voz
    from test_audio import _voz_tg

    dois.post("/interno/manifesto", headers={"X-Solo-Token": "tok-fin"},
              json={**FIN, "audio": {"recebe": True}})
    _tg(dois, "/fin saldo")
    frase = "Paguei 123,67 da internet."
    monkeypatch.setattr(telegram, "baixar", lambda fid: b"OGG-BYTES")
    monkeypatch.setattr(voz, "transcrever", lambda conteudo, mime: frase)
    ch = _ia(monkeypatch, None)
    _voz_tg(dois)
    assert ch == []
    app, _, corpo = sistemas.recebidos[-1]
    assert app == "fin" and corpo["texto"] == frase and corpo["via_audio"] is True


def test_escolha_da_pergunta_tambem_traduz(dois, sistemas, caixa, monkeypatch):
    from test_fluxos import _toque
    _ia(monkeypatch, None)
    _tg(dois, "e aí, tudo certo?")                           # pergunta
    _ia(monkeypatch, {"app": "rot", "mensagem": "/hoje", "confianca": 0.9})
    _toque(dois, "hub:app|rot")
    assert sistemas.recebidos[-1][2]["texto"] == "/hoje"


def test_ia_le_o_json_do_gemini(monkeypatch):
    import httpx
    import config
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g")

    class C:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, json, headers):
            assert "MENSAGEM: o que tem pra hoje" in json["contents"][0]["parts"][0]["text"]
            assert json["generationConfig"]["responseMimeType"] == "application/json"
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": '{"app": "rot", "mensagem": "/hoje", "confianca": 0.92}'}]}}]},
                request=httpx.Request("POST", url))
    from nucleo import gemini
    monkeypatch.setattr(gemini.httpx, "Client", C)
    it = intencao._ia("o que tem pra hoje", [{"chave": "rot"}], None)
    assert (it.app, it.mensagem, it.confianca) == ("rot", "/hoje", 0.92)


def test_ia_recebe_a_sintaxe_do_comando(dois, sistemas, monkeypatch):
    """O `uso` do manifesto chega à IA, e o prompt manda seguir a ordem dos argumentos."""
    from database import SessionLocal
    from nucleo import manifestos, modulos
    db = SessionLocal()
    man = {"app": "rot", "versao": "9", "comandos": [
        {"comando": "/somar", "descricao": "Registrar progresso numa meta",
         "uso": "/somar <título> <valor>", "exemplo": "/rot somar água 500"}]}
    manifestos.guardar(db, modulos.por_chave("rot"), man, "teste")
    d = intencao._descrever(db, [modulos.por_chave("rot")])
    db.close()
    assert d[0]["comandos"][0]["uso"] == "/somar <título> <valor>"
    assert "ORDEM dos argumentos" in intencao.PROMPT and '"/somar noite 25"' in intencao.PROMPT
