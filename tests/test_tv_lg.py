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
    with pytest.raises(lgtv.TVDesligada):
        asyncio.run(lgtv.executar("volume", {"modo": "subir"}, "sala"))
    assert asyncio.run(lgtv.executar("desligar", {}, "sala"))["mensagem"] == "A TV sala já está desligada."


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
