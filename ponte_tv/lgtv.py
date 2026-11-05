"""Controle das TVs LG webOS da casa. Roda no notebook, na mesma rede das TVs.

Cada TV tem um apelido ("sala", "quarto") em tv_config.json, que fica fora do Git
porque guarda o client-key do pareamento e o token da ponte.
"""
import asyncio
import json
import os
import re
import socket
import unicodedata
from pathlib import Path

CONFIG = Path(os.environ.get("TV_CONFIG", Path(__file__).with_name("tv_config.json")))

# Apps aceitos: nome falado → ids conhecidos e trecho do título para procurar na TV.
APPS = {
    "youtube": (["youtube.leanback.v4"], "youtube"),
    "netflix": (["netflix"], "netflix"),
    "globoplay": (["globoplay", "com.globo.globoplay"], "globoplay"),
    "prime": (["amazon", "com.amazon.amazonvideo"], "prime video"),
}

# O que a ponte aceita executar. Qualquer outra coisa é recusada antes de falar com a TV.
ACOES = ("ligar", "desligar", "volume", "abrir_app", "entrada", "aviso", "play", "pause", "estado",
         "favorito_abrir", "favorito_salvar", "favoritos", "favorito_apagar")
VOLUME_MODOS = ("subir", "descer", "mudo", "som", "definir")
AVISO_MAX = 200
NOME_MAX = 60

# Links aceitos nos favoritos: só o código do título/vídeo é guardado.
LINKS = (
    ("netflix", re.compile(r"netflix\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:watch|title)/(\d{5,12})", re.I)),
    ("youtube", re.compile(r"(?:youtube\.com/(?:watch\?(?:[^#\s]*&)?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})", re.I)),
)


def ler_link(link):
    """Link da Netflix ou do YouTube → (app, código). Qualquer outro link é recusado."""
    for app, padrao in LINKS:
        m = padrao.search(str(link or ""))
        if m:
            return app, m.group(1)
    raise ErroTV("Favorito: mande um link da Netflix (netflix.com/watch/… ou /title/…) ou de um vídeo do YouTube.")


def chave_nome(nome):
    """Nome do favorito comparável: sem acento, minúsculas, sem artigo no começo."""
    s = unicodedata.normalize("NFKD", str(nome or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"^(?:o|a|os|as)\s+", "", s)


class ErroTV(Exception):
    """Erro com mensagem pronta para mostrar ao usuário."""


class TVDesligada(ErroTV):
    pass


class PareamentoNegado(ErroTV):
    pass


class _Chave:
    """Armazenamento em memória exigido pela bscpylgtv; quem grava em disco é salvar_config."""

    def __init__(self):
        self.dados = {}

    async def set_key(self, key, val):
        self.dados[key] = val

    async def get_key(self, key):
        return self.dados.get(key)

    async def list_keys(self):
        return dict(self.dados)


def carregar_config():
    if not CONFIG.exists():
        return {"tvs": {}}
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def salvar_config(cfg):
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG)


def tv_do_apelido(cfg, apelido=None):
    tvs = cfg.get("tvs", {})
    if not tvs:
        raise ErroTV("Nenhuma TV cadastrada. Rode: python tv.py parear <apelido> <ip> <mac>")
    nome = (apelido or cfg.get("padrao") or next(iter(tvs))).strip().lower()
    if nome not in tvs:
        raise ErroTV(f"Não conheço a TV “{nome}”. Cadastradas: {', '.join(tvs)}.")
    return nome, tvs[nome]


def validar(acao, args):
    """Confere ação e argumentos. Devolve os argumentos limpos ou levanta ErroTV."""
    args = dict(args or {})
    if acao not in ACOES:
        raise ErroTV(f"Ação não permitida: {acao}.")
    if acao == "volume":
        modo = args.get("modo")
        if modo not in VOLUME_MODOS:
            raise ErroTV("Volume: use subir, descer, mudo, som ou definir.")
        if modo == "definir":
            try:
                valor = int(args.get("valor"))
            except (TypeError, ValueError):
                raise ErroTV("Volume: diga um número de 0 a 100.")
            if not 0 <= valor <= 100:
                raise ErroTV("Volume: diga um número de 0 a 100.")
            args["valor"] = valor
        return {"modo": modo, **({"valor": args["valor"]} if modo == "definir" else {})}
    if acao == "abrir_app":
        app = str(args.get("app", "")).strip().lower()
        if app not in APPS:
            raise ErroTV(f"App não permitido. Use: {', '.join(APPS)}.")
        return {"app": app}
    if acao == "entrada":
        try:
            hdmi = int(args.get("hdmi"))
        except (TypeError, ValueError):
            raise ErroTV("Entrada: diga HDMI 1, 2, 3 ou 4.")
        if not 1 <= hdmi <= 4:
            raise ErroTV("Entrada: diga HDMI 1, 2, 3 ou 4.")
        return {"hdmi": hdmi}
    if acao == "aviso":
        texto = re.sub(r"\s+", " ", str(args.get("texto", ""))).strip()
        if not texto:
            raise ErroTV("Aviso: falta o texto.")
        return {"texto": texto[:AVISO_MAX]}
    if acao in ("favorito_abrir", "favorito_salvar", "favorito_apagar"):
        nome = re.sub(r"\s+", " ", str(args.get("nome", ""))).strip(" .,:;!?\"'")
        if not chave_nome(nome) or len(nome) > NOME_MAX:
            raise ErroTV(f"Favorito: diga um nome de até {NOME_MAX} letras.")
        if acao != "favorito_salvar":
            return {"nome": nome}
        app, codigo = ler_link(args.get("link"))
        return {"nome": nome, "app": app, "codigo": codigo}
    return {}


def mac_normalizado(mac):
    limpo = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(limpo) != 12:
        raise ErroTV(f"MAC inválido: {mac}")
    return ":".join(limpo[i:i + 2] for i in range(0, 12, 2)).lower()


def wake_on_lan(mac, ip=None):
    """Manda o pacote mágico para a TV acordar (precisa de “Ligar via Wi-Fi” ativo na TV)."""
    corpo = bytes.fromhex(mac_normalizado(mac).replace(":", ""))
    pacote = b"\xff" * 6 + corpo * 16
    destinos = {"255.255.255.255"}
    if ip:
        destinos.add(".".join(ip.split(".")[:3] + ["255"]))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for _ in range(3):
            for destino in destinos:
                for porta in (9, 7):
                    s.sendto(pacote, (destino, porta))


def porta_aberta(ip, porta=3001, espera=0.8):
    try:
        with socket.create_connection((ip, porta), timeout=espera):
            return True
    except OSError:
        return False


async def _cliente(tv, parear=False):
    """Abre a conexão com a TV. Sem client-key, a TV mostra o pedido de pareamento."""
    from bscpylgtv import WebOsClient
    from bscpylgtv.exceptions import PyLGTVPairException
    if not parear and not tv.get("client_key"):
        raise ErroTV("Esta TV ainda não foi pareada. Rode: python tv.py parear …")
    if not porta_aberta(tv["ip"]):
        raise TVDesligada("A TV está desligada ou fora da rede.")
    cliente = await WebOsClient.create(
        tv["ip"], client_key=tv.get("client_key"), storage=_Chave(), states=[],
        timeout_connect=4, connect_retry_attempts=2, ping_interval=None,
    )
    try:
        await asyncio.wait_for(cliente.connect(), timeout=90 if parear else 12)
    except asyncio.TimeoutError:
        await cliente.disconnect()
        if parear:
            raise PareamentoNegado("Ninguém aceitou o pedido na TV a tempo.")
        raise TVDesligada("A TV não respondeu.")
    except (PyLGTVPairException, KeyError):
        await cliente.disconnect()
        raise PareamentoNegado("A TV recusou o pareamento (pedido negado ou chave revogada).")
    except OSError:
        await cliente.disconnect()
        raise TVDesligada("A TV está desligada ou fora da rede.")
    return cliente


async def parear(apelido, ip, mac, modelo=""):
    """Pede pareamento, guarda o client-key em tv_config.json e devolve as informações da TV."""
    apelido = apelido.strip().lower()
    tv = {"ip": ip, "mac": mac_normalizado(mac), "modelo": modelo}
    cliente = await _cliente(tv, parear=True)
    try:
        info = await cliente.get_software_info()
        tv["client_key"] = cliente.client_key
    finally:
        await cliente.disconnect()
    cfg = carregar_config()
    cfg.setdefault("tvs", {})[apelido] = tv
    cfg.setdefault("padrao", apelido)
    salvar_config(cfg)
    return {"apelido": apelido, "webos": info.get("product_name") or info.get("major_ver")}


async def _app_id(cliente, app):
    ids, titulo = APPS[app]
    instalados = await cliente.get_apps()
    disponiveis = {a.get("id"): a.get("title", "") for a in instalados or []}
    for i in ids:
        if i in disponiveis:
            return i
    for i, t in disponiveis.items():
        if titulo in t.lower():
            return i
    raise ErroTV(f"O app {app} não está instalado nesta TV.")


def _lista_favoritos(cfg):
    favs = cfg.get("favoritos", {})
    return ", ".join(f["titulo"] for f in favs.values()) or "nenhum ainda"


def achar_favorito(cfg, nome):
    """Pelo nome exato (sem acento/artigo) ou por um pedaço que só um favorito tenha."""
    favs = cfg.get("favoritos", {})
    chave = chave_nome(nome)
    if chave in favs:
        return favs[chave]
    parecidos = [f for k, f in favs.items() if chave in k or k in chave]
    if len(parecidos) == 1:
        return parecidos[0]
    raise ErroTV(f"Não tenho o favorito “{nome}”. Favoritos: {_lista_favoritos(cfg)}.")


def _gerir_favoritos(cfg, acao, args):
    favs = cfg.setdefault("favoritos", {})
    if acao == "favoritos":
        return f"Favoritos: {_lista_favoritos(cfg)}."
    chave = chave_nome(args["nome"])
    if acao == "favorito_apagar":
        fav = achar_favorito(cfg, args["nome"])
        favs.pop(chave_nome(fav["titulo"]), None)
        salvar_config(cfg)
        return f"Tirei {fav['titulo']} dos favoritos."
    favs[chave] = {"titulo": args["nome"], "app": args["app"], "codigo": args["codigo"]}
    salvar_config(cfg)
    return f"Favorito salvo: {args['nome']} ({args['app'].capitalize()})."


async def _abrir_conteudo(cliente, fav):
    """Abre o app já no título. Perfil e controle de maturidade continuam com a Netflix."""
    if fav["app"] == "netflix":
        await cliente.launch_app_with_content_id(
            await _app_id(cliente, "netflix"), f"m=https://www.netflix.com/watch/{fav['codigo']}&source_type=4")
    else:
        await cliente.launch_app_with_params(
            await _app_id(cliente, "youtube"), {"contentTarget": f"https://www.youtube.com/tv?v={fav['codigo']}"})


async def executar(acao, args=None, apelido=None):
    """Executa uma ação permitida na TV pelo apelido. Devolve {ok, mensagem, tv}."""
    args = validar(acao, args)
    cfg = carregar_config()
    nome, tv = tv_do_apelido(cfg, apelido)

    if acao in ("favorito_salvar", "favoritos", "favorito_apagar"):
        return {"ok": True, "tv": nome, "mensagem": _gerir_favoritos(cfg, acao, args)}

    if acao == "ligar":
        if porta_aberta(tv["ip"]):
            return {"ok": True, "tv": nome, "mensagem": f"A TV {nome} já está ligada."}
        wake_on_lan(tv["mac"], tv["ip"])
        for _ in range(20):
            await asyncio.sleep(1)
            if porta_aberta(tv["ip"]):
                return {"ok": True, "tv": nome, "mensagem": f"TV {nome} ligada."}
        raise TVDesligada("Mandei o sinal para ligar, mas a TV não respondeu. "
                          "Confira se “Ligar via Wi-Fi” está ativo nas configurações da TV.")

    if acao == "desligar" and not porta_aberta(tv["ip"]):
        return {"ok": True, "tv": nome, "mensagem": f"A TV {nome} já está desligada."}

    from bscpylgtv.exceptions import PyLGTVCmdException
    cliente = await _cliente(tv)
    try:
        if acao == "desligar":
            await cliente.power_off()
            msg = f"TV {nome} desligada."
        elif acao == "volume":
            modo = args["modo"]
            if modo == "subir":
                await cliente.volume_up()
            elif modo == "descer":
                await cliente.volume_down()
            elif modo == "mudo":
                await cliente.set_mute(True)
            elif modo == "som":
                await cliente.set_mute(False)
            else:
                await cliente.set_volume(args["valor"])
            msg = {"mudo": "Som cortado.", "som": "Som de volta."}.get(modo)
            if not msg:
                msg = f"Volume em {await cliente.get_volume()}."
        elif acao == "abrir_app":
            await cliente.launch_app(await _app_id(cliente, args["app"]))
            msg = f"Abrindo {args['app'].capitalize()} na TV {nome}."
        elif acao == "favorito_abrir":
            fav = achar_favorito(cfg, args["nome"])
            await _abrir_conteudo(cliente, fav)
            msg = f"Abrindo {fav['titulo']} no {fav['app'].capitalize()} da TV {nome}."
        elif acao == "entrada":
            await cliente.set_input(f"HDMI_{args['hdmi']}")
            msg = f"TV {nome} no HDMI {args['hdmi']}."
        elif acao == "aviso":
            await cliente.send_message(args["texto"])
            msg = "Aviso mostrado na TV."
        elif acao == "play":
            await cliente.play()
            msg = "Play."
        elif acao == "pause":
            await cliente.pause()
            msg = "Pausado."
        else:
            msg = (f"TV {nome}: ligada, volume {await cliente.get_volume()}, "
                   f"{'mudo' if await cliente.get_muted() else 'com som'}, "
                   f"app {await cliente.get_current_app() or 'carregando'}.")
        return {"ok": True, "tv": nome, "mensagem": msg}
    except PyLGTVCmdException as ex:
        raise ErroTV(f"A TV recusou o comando: {getattr(ex, 'message', ex)}")
    finally:
        await cliente.disconnect()
