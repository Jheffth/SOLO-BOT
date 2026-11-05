"""TV LG de casa: pedidos em português, fila com a ponte, rotas autenticadas e ponte local."""
import asyncio
import sys
import threading
import types
from pathlib import Path

import pytest

import config
from nucleo import tv_lg
from test_clonarvoz import _admin
from test_fluxos import _ligar_telegram, _tg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ponte_tv"))
import lgtv  # noqa: E402
import ponte  # noqa: E402

TOKEN = "segredo-da-ponte"
PONTE = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def fila(monkeypatch):
    monkeypatch.setattr(config, "PONTE_TV_TOKEN", TOKEN)
    f = tv_lg.Fila()
    monkeypatch.setattr(tv_lg, "FILA", f)
    return f


def _ponte_falsa(fila, respostas=None, tvs=("sala", "quarto"), vezes=1):
    """Faz o papel do notebook: busca o comando e responde."""
    recebidos = []

    def rodar():
        for _ in range(vezes):
            cmd = fila.proximo(5, list(tvs))
            if cmd:
                recebidos.append(cmd)
                ok, msg = (respostas or {}).get(cmd["acao"], (True, f"feito: {cmd['acao']}"))
                fila.resultado(cmd["id"], ok, msg)
    fila.visto_em = __import__("time").monotonic()
    fila.tvs = list(tvs)
    t = threading.Thread(target=rodar, daemon=True)
    t.start()
    return recebidos, t


# ── pedidos em português ──────────────────────────────────────────
@pytest.mark.parametrize("texto, esperado", [
    ("desliga a tv", ("tv.desligar", {}, None)),
    ("Liga a TV do quarto", ("tv.ligar", {}, "quarto")),
    ("desliga o som da tv", ("tv.volume", {"modo": "mudo"}, None)),
    ("tv no mudo", ("tv.volume", {"modo": "mudo"}, None)),
    ("tira a tv do mudo", ("tv.volume", {"modo": "som"}, None)),
    ("volume 20 na tv da sala", ("tv.volume", {"modo": "definir", "valor": 20}, "sala")),
    ("aumenta o volume da televisão", ("tv.volume", {"modo": "subir"}, None)),
    ("abaixa a tv", ("tv.volume", {"modo": "descer"}, None)),
    ("abre o netflix na tv", ("tv.abrir_app", {"app": "netflix"}, None)),
    ("coloca globo play na tv", ("tv.abrir_app", {"app": "globoplay"}, None)),
    ("tv hdmi 2", ("tv.entrada", {"hdmi": 2}, None)),
    ("pausa a tv", ("tv.pause", {}, None)),
    ("play na tv", ("tv.play", {}, None)),
    ("/tv estado", ("tv.estado", {}, None)),
    ("mostra na tv: Jantar pronto, desce!", ("tv.aviso", {"texto": "Jantar pronto, desce!"}, None)),
    ("/tv aviso Liga pra mamãe", ("tv.aviso", {"texto": "Liga pra mamãe"}, None)),
    ("desliga a tv do escritorio", ("tv.desligar", {}, "escritorio")),
    ("/tv volume 20", ("tv.volume", {"modo": "definir", "valor": 20}, None)),
    ("tira a tv do mudo", ("tv.volume", {"modo": "som"}, None)),
    ("abre The Chosen na tv", ("tv.favorito_abrir", {"nome": "the chosen"}, None)),
    ("Abra a Netflix em The Chosen", ("tv.favorito_abrir", {"nome": "the chosen"}, None)),
    ("coloca o youtube no clipe da festa na tv sala", ("tv.favorito_abrir", {"nome": "clipe da festa"}, "sala")),
    ("abre o youtube na tv", ("tv.abrir_app", {"app": "youtube"}, None)),
    ("/tv favorito The Chosen https://www.netflix.com/watch/81622759?trackId=284616272",
     ("tv.favorito_salvar", {"nome": "The Chosen", "link": "https://www.netflix.com/watch/81622759?trackId=284616272"}, None)),
    ("/tv favoritos", ("tv.favoritos", {}, None)),
    ("/tv esquecer The Chosen", ("tv.favorito_apagar", {"nome": "The Chosen"}, None)),
])
def test_entende_pedidos(texto, esperado):
    assert tv_lg.interpretar(texto, tvs=["sala", "quarto"]) == esperado


@pytest.mark.parametrize("texto", [
    "gastei 80 no mercado", "liga pra mim amanhã", "abre o netflix",
    "ontem eu vi na tv uma reportagem enorme sobre como desligar o celular à noite",
])
def test_ignora_o_que_nao_e_pedido_de_tv(texto):
    assert tv_lg.interpretar(texto, tvs=["sala"]) is None


def test_validacao_recusa_fora_da_lista():
    with pytest.raises(tv_lg.ErroTV):
        tv_lg.validar("tv.formatar", {})
    with pytest.raises(tv_lg.ErroTV):
        tv_lg.validar("tv.volume", {"modo": "definir", "valor": 150})
    with pytest.raises(tv_lg.ErroTV):
        tv_lg.validar("tv.abrir_app", {"app": "cmd.exe"})
    assert tv_lg.validar("tv.aviso", {"texto": "x" * 500}) == {"texto": "x" * 200}


def test_bot_e_ponte_validam_igual():
    casos = [("volume", {"modo": "definir", "valor": "15"}), ("abrir_app", {"app": "Prime"}),
             ("entrada", {"hdmi": "3"}), ("aviso", {"texto": "  oi   tv "}), ("pause", {})]
    for acao, args in casos:
        assert tv_lg.validar(f"tv.{acao}", args) == lgtv.validar(acao, args)
    assert set(tv_lg.ACOES_AGENTE) == {f"tv.{a}" for a in lgtv.ACOES}
    assert set(tv_lg.APPS) == set(lgtv.APPS)


# ── fila e execução ───────────────────────────────────────────────
def test_favorito_so_aceita_netflix_e_youtube():
    assert tv_lg.validar("tv.favorito_salvar", {"nome": "The Chosen", "link": "https://www.netflix.com/br/title/81622759"}) \
        == {"nome": "The Chosen", "link": "https://www.netflix.com/watch/81622759"}
    assert tv_lg.validar("tv.favorito_salvar", {"nome": "Clipe", "link": "https://youtu.be/dQw4w9WgXcQ?t=3"}) \
        == {"nome": "Clipe", "link": "https://youtu.be/dQw4w9WgXcQ"}
    for link in ("https://evil.example/netflix.com", "file:///c:/x", "https://www.netflix.com/browse"):
        with pytest.raises(tv_lg.ErroTV):
            tv_lg.validar("tv.favorito_salvar", {"nome": "x", "link": link})
    with pytest.raises(tv_lg.ErroTV):
        tv_lg.validar("tv.favorito_abrir", {"nome": "x" * 61})
    assert "Esse app eu não abro" in str(pytest.raises(tv_lg.ErroTV, tv_lg.validar, "tv.abrir_app", {"app": "cmd"}).value)


def test_ponte_guarda_abre_e_tira_favoritos(monkeypatch, tmp_path):
    monkeypatch.setattr(lgtv, "CONFIG", tmp_path / "tv_config.json")
    lgtv.salvar_config({"tvs": {"sala": {"ip": "10.0.0.9", "mac": "f0:86:20:f2:26:1e", "client_key": "k"}}})
    args = tv_lg.validar("tv.favorito_salvar", {"nome": "The Chosen", "link": "https://www.netflix.com/watch/81622759"})
    r = asyncio.run(lgtv.executar("favorito_salvar", args, "sala"))
    assert r["mensagem"] == "Favorito salvo: The Chosen (Netflix)."
    assert lgtv.carregar_config()["favoritos"] == {"the chosen": {"titulo": "The Chosen", "app": "netflix", "codigo": "81622759"}}

    abertos = []

    class Cliente:
        async def get_apps(self):
            return [{"id": "netflix", "title": "Netflix"}]

        async def launch_app_with_content_id(self, app, conteudo):
            abertos.append((app, conteudo))

        async def disconnect(self):
            pass

    async def cliente(tv, parear=False):
        return Cliente()
    monkeypatch.setattr(lgtv, "_cliente", cliente)
    monkeypatch.setitem(sys.modules, "bscpylgtv.exceptions", types.SimpleNamespace(PyLGTVCmdException=RuntimeError))
    r = asyncio.run(lgtv.executar("favorito_abrir", {"nome": "chosen"}, "sala"))
    assert abertos == [("netflix", "m=https://www.netflix.com/watch/81622759&source_type=4")]
    assert r["mensagem"] == "Abrindo The Chosen no Netflix da TV sala."
    with pytest.raises(lgtv.ErroTV, match="Favoritos: The Chosen"):
        asyncio.run(lgtv.executar("favorito_abrir", {"nome": "calculadora"}, "sala"))
    assert "Tirei The Chosen" in asyncio.run(lgtv.executar("favorito_apagar", {"nome": "o the chosen"}, "sala"))["mensagem"]
    assert lgtv.carregar_config()["favoritos"] == {}


def test_executa_pela_ponte(fila):
    recebidos, t = _ponte_falsa(fila, {"volume": (True, "Volume em 20.")})
    assert tv_lg.executar("tv.volume", {"modo": "definir", "valor": 20}, "Sala") == "📺 Volume em 20."
    t.join(2)
    assert recebidos == [{"id": 1, "acao": "volume", "args": {"modo": "definir", "valor": 20}, "tv": "sala"}]


def test_erro_da_tv_volta_para_o_usuario(fila):
    _ponte_falsa(fila, {"desligar": (False, "A TV está desligada ou fora da rede.")})
    assert tv_lg.atender("desliga a tv") == "⚠️ A TV está desligada ou fora da rede."


def test_ponte_desligada_e_tv_desconhecida(fila):
    assert "ponte da TV está desligada" in tv_lg.atender("desliga a tv")
    fila.visto_em = __import__("time").monotonic()
    fila.tvs = ["sala"]
    assert "Não conheço a TV" in tv_lg.atender("/tv quarto desligar")


def test_comando_velho_nao_e_entregue(fila, monkeypatch):
    monkeypatch.setattr(tv_lg, "ESPERA_RESULTADO", 0.05)
    fila.visto_em = __import__("time").monotonic()
    assert "não respondeu" in tv_lg.executar("tv.ligar", {}, None)
    assert fila.proximo(0) is None          # quem desistiu não deixa o comando na fila


def test_sem_token_no_servidor(monkeypatch):
    monkeypatch.setattr(config, "PONTE_TV_TOKEN", "")
    with pytest.raises(tv_lg.ErroTV):
        tv_lg.executar("tv.ligar")


# ── rotas da ponte ────────────────────────────────────────────────
def test_rotas_exigem_token(cliente, fila):
    assert cliente.get("/api/ponte-tv/proximo?espera=0").status_code == 401
    assert cliente.get("/api/ponte-tv/proximo?espera=0", headers={"Authorization": "Bearer errado"}).status_code == 401
    assert cliente.post("/api/ponte-tv/resultado", json={"id": 1, "ok": True}).status_code == 401
    r = cliente.get("/api/ponte-tv/proximo?espera=0&tvs=sala,Quarto", headers=PONTE)
    assert r.status_code == 204 and fila.tvs == ["sala", "quarto"] and fila.online()


def test_rotas_somem_sem_token_configurado(cliente, monkeypatch):
    monkeypatch.setattr(config, "PONTE_TV_TOKEN", "")
    assert cliente.get("/api/ponte-tv/proximo?espera=0", headers=PONTE).status_code == 404


def test_ida_e_volta_pelas_rotas(cliente, fila):
    fila.visto_em = __import__("time").monotonic()
    resposta = {}
    t = threading.Thread(target=lambda: resposta.setdefault("r", tv_lg.executar("tv.pause")), daemon=True)
    t.start()
    cmd = None
    for _ in range(50):
        r = cliente.get("/api/ponte-tv/proximo?espera=1", headers=PONTE)
        if r.status_code == 200:
            cmd = r.json()
            break
    assert cmd["acao"] == "pause"
    assert cliente.post("/api/ponte-tv/resultado", headers=PONTE,
                        json={"id": cmd["id"], "ok": True, "mensagem": "Pausado."}).json() == {"aceito": True}
    t.join(2)
    assert resposta["r"] == "📺 Pausado."


# ── pelo bot, como o usuário fala ─────────────────────────────────
def test_admin_comanda_a_tv_pelo_telegram(cliente, caixa, fila):
    c = _admin(cliente)
    _ligar_telegram(c)
    recebidos, t = _ponte_falsa(fila, {"abrir_app": (True, "Abrindo Netflix na TV sala.")})
    _tg(c, "abre o netflix na tv")
    t.join(2)
    assert caixa[-1][2] == "📺 Abrindo Netflix na TV sala."
    assert recebidos[0]["acao"] == "abrir_app"
    _tg(c, "/tv")
    assert "Ponte de casa: ligada" in caixa[-1][2]


def test_conta_comum_nao_mexe_na_tv(logado, caixa, fila):
    _ligar_telegram(logado)
    _tg(logado, "/tv desligar")
    assert "administradora" in caixa[-1][2]
    _tg(logado, "desliga a tv")
    assert "📺" not in caixa[-1][2] and fila.proximo(0) is None


# ── ponte local (notebook) ────────────────────────────────────────
def test_ponte_recusa_acao_fora_da_lista():
    ok, msg = asyncio.run(ponte._atender({"id": 1, "acao": "rodar_comando", "args": {"cmd": "del"}}))
    assert not ok and "não permitida" in msg


def test_pareamento_negado_vira_mensagem(monkeypatch, tmp_path):
    class Negado(Exception):
        pass

    class ClienteFalso:
        client_key = None

        @classmethod
        async def create(cls, *a, **k):
            return cls()

        async def connect(self):
            raise Negado("Unable to pair")

        async def disconnect(self):
            pass

    bsc = types.ModuleType("bscpylgtv")
    bsc.WebOsClient = ClienteFalso
    exc = types.ModuleType("bscpylgtv.exceptions")
    exc.PyLGTVPairException = Negado
    exc.PyLGTVCmdException = Exception
    monkeypatch.setitem(sys.modules, "bscpylgtv", bsc)
    monkeypatch.setitem(sys.modules, "bscpylgtv.exceptions", exc)
    monkeypatch.setattr(lgtv, "CONFIG", tmp_path / "tv_config.json")
    monkeypatch.setattr(lgtv, "porta_aberta", lambda *a, **k: True)
    with pytest.raises(lgtv.PareamentoNegado):
        asyncio.run(lgtv.parear("sala", "192.168.1.13", "f0:86:20:f2:26:1e"))
    assert not (tmp_path / "tv_config.json").exists()


def test_tv_desligada_na_ponte(monkeypatch, tmp_path):
    monkeypatch.setattr(lgtv, "CONFIG", tmp_path / "tv_config.json")
    lgtv.salvar_config({"tvs": {"sala": {"ip": "10.0.0.9", "mac": "f0:86:20:f2:26:1e", "client_key": "k"}}})
    monkeypatch.setattr(lgtv, "porta_aberta", lambda *a, **k: False)
    monkeypatch.setattr(lgtv, "_ip_pelo_mac", lambda mac: None)
    with pytest.raises(lgtv.TVDesligada):
        asyncio.run(lgtv.executar("volume", {"modo": "subir"}, "sala"))
    assert asyncio.run(lgtv.executar("desligar", {}, "sala"))["mensagem"] == \
        "Não achei a TV sala na rede: ela já parece desligada."


def test_tv_que_mudou_de_ip_e_achada_pelo_mac(monkeypatch, tmp_path):
    """O roteador trocou o IP (13 → 6): a ponte acha pelo MAC, grava e desliga a TV certa."""
    monkeypatch.setattr(lgtv, "CONFIG", tmp_path / "tv_config.json")
    lgtv.salvar_config({"tvs": {"sala": {"ip": "192.168.1.13", "mac": "f0:86:20:f2:26:1e", "client_key": "k"}}})
    monkeypatch.setattr(lgtv, "porta_aberta", lambda ip, *a, **k: ip == "192.168.1.6")
    monkeypatch.setattr(lgtv, "_ip_pelo_mac", lambda mac: "192.168.1.6")
    usados = []

    class Cliente:
        async def power_off(self):
            pass

        async def disconnect(self):
            pass

    async def cliente(tv, parear=False):
        usados.append(tv["ip"])
        return Cliente()
    monkeypatch.setattr(lgtv, "_cliente", cliente)
    monkeypatch.setitem(sys.modules, "bscpylgtv.exceptions", types.SimpleNamespace(PyLGTVCmdException=RuntimeError))
    assert asyncio.run(lgtv.executar("desligar", {}, "sala"))["mensagem"] == "TV sala desligada."
    assert usados == ["192.168.1.6"] and lgtv.carregar_config()["tvs"]["sala"]["ip"] == "192.168.1.6"


def test_ip_pelo_mac_le_a_tabela_arp(monkeypatch):
    saida = "  192.168.1.6           f0-86-20-f2-26-1e     dinâmico\n  192.168.1.1  aa-bb-cc-dd-ee-ff  dinâmico\n"
    monkeypatch.setattr(lgtv.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout=saida))
    assert lgtv._ip_pelo_mac("F0:86:20:F2:26:1E") == "192.168.1.6"
    assert lgtv._ip_pelo_mac("00:11:22:33:44:55") is None


def test_pacote_magico(monkeypatch):
    enviados = []

    class Sock:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def setsockopt(self, *a):
            pass

        def sendto(self, dados, destino):
            enviados.append((dados, destino))
    monkeypatch.setattr(lgtv.socket, "socket", Sock)
    lgtv.wake_on_lan("F0-86-20-F2-26-1E", "192.168.1.13")
    pacote = enviados[0][0]
    assert pacote[:6] == b"\xff" * 6 and pacote[6:12] == bytes.fromhex("f08620f2261e") and len(pacote) == 102
    assert ("192.168.1.255", 9) in {d for _, d in enviados}


# ── conversa: a IA entende pedido solto e a própria modelo responde ──
def _ia_responde(monkeypatch, saida):
    from nucleo import gemini
    chamadas = []

    def gerar(instrucao, texto, **kw):
        chamadas.append(texto)
        return saida
    monkeypatch.setattr(gemini, "gerar", gerar)
    return chamadas


def test_ia_entende_pedido_solto(monkeypatch, fila):
    chamadas = _ia_responde(monkeypatch, '{"acao":"tv.volume","args":{"modo":"descer"},"tv":"sala","confianca":0.9}')
    pedido = tv_lg.entender("tá alto demais esse barulho, dá uma baixada", tvs=["sala", "quarto"])
    assert pedido == ("tv.volume", {"modo": "descer"}, "sala") and len(chamadas) == 1


@pytest.mark.parametrize("saida", [
    '{"acao":"","args":{},"tv":"","confianca":0.9}',                                              # só conversa
    '{"acao":"tv.volume","args":{"modo":"descer"},"tv":"","confianca":0.4}',                      # incerta
    '{"acao":"tv.favorito_apagar","args":{"nome":"x"},"tv":"","confianca":0.99}',                # fora das ações da IA
    '{"acao":"tv.volume","args":{"modo":"definir","valor":900},"tv":"","confianca":0.99}',       # valor inválido
    '{"acao":"tv.desligar","args":{},"tv":"garagem","confianca":0.99}',                          # TV que a ponte não conhece
    "isso não é json", None])
def test_ia_recusa_o_que_nao_vale(monkeypatch, fila, saida):
    _ia_responde(monkeypatch, saida)
    assert tv_lg.entender("baixa o barulho", tvs=["sala"]) is None


def test_ia_so_e_chamada_quando_vale_a_pena(monkeypatch, fila):
    chamadas = _ia_responde(monkeypatch, '{"acao":"tv.desligar","args":{},"tv":"","confianca":1}')
    assert tv_lg.entender("gastei 80 no mercado", tvs=["sala"]) is None
    assert tv_lg.entender("/saldo barulho", tvs=["sala"]) is None
    assert tv_lg.entender("baixa o barulho", tvs=["sala"], ia=False) is None
    assert tv_lg.entender("desliga a tv", tvs=["sala"]) == ("tv.desligar", {}, None)      # palavras bastam: sem IA
    assert not chamadas
    monkeypatch.setattr(config, "PONTE_TV_TOKEN", "")
    assert tv_lg.entender("baixa o barulho", tvs=["sala"]) is None and not chamadas


def test_prompt_da_persona_so_fala_de_tv_para_o_admin(monkeypatch, fila):
    assert "TV DA CASA" in tv_lg.bloco_prompt(True) and "[AÇÃO NA TV]" in tv_lg.bloco_prompt(True)
    assert tv_lg.bloco_prompt(False) == ""
    monkeypatch.setattr(config, "PONTE_TV_TOKEN", "")
    assert tv_lg.bloco_prompt(True) == ""


def test_nota_conta_o_que_aconteceu():
    assert "DEU CERTO" in tv_lg.nota_acao("tv.volume", True, "Volume 12.")
    nota = tv_lg.nota_acao("tv.desligar", False, "A TV está fora da rede.")
    assert "FALHOU" in nota and "A TV está fora da rede." in nota and "sem inventar causa" in nota


def _persona(monkeypatch, texto):
    from nucleo import bella_conversa
    vistos = []

    def responder(fala, conta_id=None, numero_conta=None, saida_midia=None, nota_interna=""):
        vistos.append((fala, nota_interna))
        return texto
    monkeypatch.setattr(bella_conversa, "responder", responder)
    return vistos


def test_modelo_responde_sobre_o_que_fez_na_tv(cliente, caixa, fila, monkeypatch):
    c = _admin(cliente)
    _ligar_telegram(c)
    vistos = _persona(monkeypatch, "Pronto, amor, baixei pra você.")
    recebidos, t = _ponte_falsa(fila, {"volume": (True, "Volume 12.")})
    _tg(c, "abaixa a tv")
    t.join(2)
    assert recebidos[0]["acao"] == "volume"
    assert caixa[-1][2] == "Pronto, amor, baixei pra você."
    assert vistos[0][0] == "abaixa a tv" and "DEU CERTO" in vistos[0][1] and "Volume 12." in vistos[0][1]


def test_falha_da_tv_aparece_mesmo_com_a_modelo_suavizando(cliente, caixa, fila, monkeypatch):
    c = _admin(cliente)
    _ligar_telegram(c)
    _persona(monkeypatch, "Ih, amor, não consegui agora.")
    recebidos, t = _ponte_falsa(fila, {"desligar": (False, "A TV está desligada ou fora da rede.")})
    _tg(c, "desliga a tv")
    t.join(2)
    assert caixa[-2][2] == "Ih, amor, não consegui agora."
    assert caixa[-1][2] == "⚠️ A TV está desligada ou fora da rede."


def test_sem_voz_da_modelo_o_resultado_seco_nao_se_perde(cliente, caixa, fila, monkeypatch):
    c = _admin(cliente)
    _ligar_telegram(c)
    _persona(monkeypatch, None)
    recebidos, t = _ponte_falsa(fila, {"volume": (True, "Volume 12.")})
    _tg(c, "abaixa a tv")
    t.join(2)
    assert caixa[-1][2] == "📺 Volume 12."


def test_pedido_solto_pelo_telegram_passa_pela_ia(cliente, caixa, fila, monkeypatch):
    c = _admin(cliente)
    _ligar_telegram(c)
    _ia_responde(monkeypatch, '{"acao":"tv.abrir_app","args":{"app":"youtube"},"tv":"","confianca":0.9}')
    _persona(monkeypatch, "Abri o YouTube, vai querer ver o quê?")
    recebidos, t = _ponte_falsa(fila, {"abrir_app": (True, "Abrindo YouTube na TV sala.")})
    _tg(c, "bella, quero ver uns clipes agora")
    t.join(2)
    assert recebidos[0]["acao"] == "abrir_app" and recebidos[0]["args"] == {"app": "youtube"}
    assert caixa[-1][2] == "Abri o YouTube, vai querer ver o quê?"
