# -*- coding: utf-8 -*-
"""
TV LG (webOS) da casa, comandada pelo bot através da ponte local.

O bot roda na VPS e a TV fica na rede de casa. Quem fala com a TV é a ponte
(`ponte_tv/ponte.py`, no notebook): ela abre a conexão de saída, busca o próximo
comando em `/api/ponte-tv/proximo` e devolve o resultado. Nenhuma porta do
roteador fica aberta. Este arquivo guarda a fila, valida as ações e entende os
pedidos em português ("desliga a tv da sala", "volume 20", "abre o youtube na tv").

Ações para o agente (sempre com `tv` opcional = apelido, "sala", "quarto"…):
  tv.ligar · tv.desligar · tv.volume {modo: subir|descer|mudo|som|definir, valor 0–100}
  tv.abrir_app {app: youtube|netflix|globoplay|prime} · tv.entrada {hdmi: 1–4}
  tv.aviso {texto} · tv.play · tv.pause · tv.estado
"""
import itertools
import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

import config

log = logging.getLogger("solobot.tv")

ACOES_AGENTE = {
    "tv.ligar": "Liga a TV (Wake-on-LAN).",
    "tv.desligar": "Desliga a TV.",
    "tv.volume": "Volume: modo subir, descer, mudo, som ou definir (valor de 0 a 100).",
    "tv.abrir_app": "Abre um app: youtube, netflix, globoplay ou prime.",
    "tv.entrada": "Troca para a entrada HDMI 1 a 4.",
    "tv.aviso": "Mostra um aviso (toast) na tela, até 200 caracteres.",
    "tv.play": "Continua o que está tocando.",
    "tv.pause": "Pausa o que está tocando.",
    "tv.estado": "Diz se está ligada, o volume e o app aberto.",
    "tv.favorito_abrir": "Abre um favorito pelo nome, já no título (Netflix) ou no vídeo (YouTube).",
    "tv.favorito_salvar": "Guarda um favorito: nome e link da Netflix ou do YouTube.",
    "tv.favoritos": "Lista os favoritos guardados na ponte.",
    "tv.favorito_apagar": "Tira um favorito pelo nome.",
}
APPS = ("youtube", "netflix", "globoplay", "prime")
VOLUME_MODOS = ("subir", "descer", "mudo", "som", "definir")
AVISO_MAX = 200
NOME_MAX = 60
LINKS = (
    ("https://www.netflix.com/watch/{}",
     re.compile(r"netflix\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:watch|title)/(\d{5,12})", re.I)),
    ("https://youtu.be/{}",
     re.compile(r"(?:youtube\.com/(?:watch\?(?:[^#\s]*&)?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})", re.I)),
)
ESPERA_RESULTADO = 30       # segundos que o bot espera a ponte responder
VALIDADE_COMANDO = 30       # comando não buscado nesse tempo é descartado (nada de ligar a TV horas depois)
PONTE_ONLINE = 60           # sem buscar há mais que isso, a ponte é considerada desligada
PALAVRAS_MAX = 10           # pedido falado de TV é curto; frase maior que só cita a TV segue para a conversa


class ErroTV(Exception):
    """Erro com mensagem pronta para o usuário."""


def ativo() -> bool:
    return bool(config.PONTE_TV_TOKEN)


def validar(acao: str, args: Optional[dict]) -> dict:
    """Mesma regra da ponte: só passam ações e valores permitidos."""
    args = dict(args or {})
    if acao not in ACOES_AGENTE:
        raise ErroTV(f"Ação de TV desconhecida: {acao}.")
    if acao == "tv.volume":
        modo = args.get("modo")
        if modo not in VOLUME_MODOS:
            raise ErroTV("Volume: use subir, descer, mudo, som ou definir.")
        if modo != "definir":
            return {"modo": modo}
        try:
            valor = int(args.get("valor"))
        except (TypeError, ValueError):
            raise ErroTV("Volume: diga um número de 0 a 100.")
        if not 0 <= valor <= 100:
            raise ErroTV("Volume: diga um número de 0 a 100.")
        return {"modo": modo, "valor": valor}
    if acao == "tv.abrir_app":
        app = str(args.get("app", "")).strip().lower()
        if app not in APPS:
            raise ErroTV(f"Esse app eu não abro. Posso abrir: {', '.join(APPS)}.")
        return {"app": app}
    if acao == "tv.entrada":
        try:
            hdmi = int(args.get("hdmi"))
        except (TypeError, ValueError):
            raise ErroTV("Entrada: diga HDMI 1, 2, 3 ou 4.")
        if not 1 <= hdmi <= 4:
            raise ErroTV("Entrada: diga HDMI 1, 2, 3 ou 4.")
        return {"hdmi": hdmi}
    if acao == "tv.aviso":
        texto = re.sub(r"\s+", " ", str(args.get("texto", ""))).strip()
        if not texto:
            raise ErroTV("Aviso: falta o texto.")
        return {"texto": texto[:AVISO_MAX]}
    if acao in ("tv.favorito_abrir", "tv.favorito_salvar", "tv.favorito_apagar"):
        nome = re.sub(r"\s+", " ", str(args.get("nome", ""))).strip(" .,:;!?\"'")
        if not re.search(r"[0-9A-Za-zÀ-ÿ]", nome) or len(nome) > NOME_MAX:
            raise ErroTV(f"Favorito: diga um nome de até {NOME_MAX} letras.")
        if acao != "tv.favorito_salvar":
            return {"nome": nome}
        for modelo, padrao in LINKS:          # só o código vai para a ponte, num link limpo
            m = padrao.search(str(args.get("link") or ""))
            if m:
                return {"nome": nome, "link": modelo.format(m.group(1))}
        raise ErroTV("Favorito: mande um link da Netflix (netflix.com/watch/… ou /title/…) ou de um vídeo do YouTube.")
    return {}


# ══════════════════════════════════════════════════════════════════════
# FILA ENTRE O BOT E A PONTE (um processo só: uvicorn sem workers extras)
# ══════════════════════════════════════════════════════════════════════
@dataclass
class _Comando:
    id: int
    acao: str
    args: dict
    tv: Optional[str]
    criado: float = field(default_factory=time.monotonic)
    pronto: threading.Event = field(default_factory=threading.Event)
    resultado: Optional[dict] = None


class Fila:
    def __init__(self):
        self._cond = threading.Condition()
        self._pendentes = []
        self._aguardando = {}
        self._ids = itertools.count(1)
        self.visto_em = 0.0
        self.tvs = []

    def online(self) -> bool:
        return time.monotonic() - self.visto_em < PONTE_ONLINE

    def enviar(self, acao, args, tv, espera=ESPERA_RESULTADO) -> dict:
        cmd = _Comando(next(self._ids), acao, args, tv)
        with self._cond:
            self._pendentes.append(cmd)
            self._aguardando[cmd.id] = cmd
            self._cond.notify_all()
        try:
            if not cmd.pronto.wait(espera):
                return {"ok": False, "mensagem": "A ponte da TV não respondeu a tempo."}
            return cmd.resultado
        finally:
            with self._cond:
                self._aguardando.pop(cmd.id, None)
                if cmd in self._pendentes:
                    self._pendentes.remove(cmd)

    def proximo(self, espera: float, tvs=None) -> Optional[dict]:
        """Chamado pela ponte (long-poll). Devolve o próximo comando válido ou None."""
        fim = time.monotonic() + espera
        with self._cond:
            self.visto_em = time.monotonic()
            if tvs is not None:
                self.tvs = tvs
            while True:
                agora = time.monotonic()
                self._pendentes = [c for c in self._pendentes if agora - c.criado < VALIDADE_COMANDO]
                if self._pendentes:
                    c = self._pendentes.pop(0)
                    return {"id": c.id, "acao": c.acao.split(".", 1)[1], "args": c.args, "tv": c.tv}
                if agora >= fim:
                    return None
                self._cond.wait(fim - agora)
                self.visto_em = time.monotonic()

    def resultado(self, id_: int, ok: bool, mensagem: str) -> bool:
        with self._cond:
            cmd = self._aguardando.get(id_)
        if not cmd:
            return False
        cmd.resultado = {"ok": bool(ok), "mensagem": str(mensagem)[:500]}
        cmd.pronto.set()
        return True


FILA = Fila()


def executar(acao: str, args: Optional[dict] = None, tv: Optional[str] = None) -> str:
    """Executa uma ação de TV pelo agente ou pelo roteador. Devolve o texto da resposta."""
    if not ativo():
        raise ErroTV("O controle da TV não está configurado no servidor (PONTE_TV_TOKEN).")
    args = validar(acao, args)
    tv = (tv or "").strip().lower() or None
    if tv and FILA.tvs and tv not in FILA.tvs:
        raise ErroTV(f"Não conheço a TV “{tv}”. TVs da ponte: {', '.join(FILA.tvs)}.")
    if not FILA.online():
        raise ErroTV("A ponte da TV está desligada. Ligue o notebook de casa com a ponte rodando.")
    r = FILA.enviar(acao, args, tv)
    log.info("tv %s tv=%s ok=%s", acao, tv or "padrão", r["ok"])
    return ("📺 " if r["ok"] else "⚠️ ") + r["mensagem"]


# ══════════════════════════════════════════════════════════════════════
# PEDIDOS EM PORTUGUÊS → AÇÃO
# ══════════════════════════════════════════════════════════════════════
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


RE_TV = re.compile(r"(^/tv\b|\btv\b|\btelevis)")
RE_AVISO = re.compile(r"\b(?:aviso|mensagem|mostra|mostre|escreve|escreva)\b[^:]*?(?:na tv[^:]*?)?:\s*(.+)$|^/tv\s+aviso\s+(.+)$")
APP_FALADO = {"youtube": "youtube", "you tube": "youtube", "netflix": "netflix", "globoplay": "globoplay",
              "globo play": "globoplay", "prime": "prime", "amazon": "prime"}


VOCABULARIO = {"a", "o", "e", "da", "do", "de", "na", "no", "em", "pra", "para", "tv", "liga", "ligar", "desliga",
               "desligar", "volume", "som", "mudo", "aumenta", "abaixa", "sobe", "desce", "abre", "abrir", "hdmi",
               "entrada", "pausa", "pause", "play", "estado", "status", "aviso", "favorito", "favoritos",
               "esquecer", *APP_FALADO}
VERBO_ABRIR = r"(?:abre|abrir|abra|coloca|coloque|bota|poe|passa|bota)"
RE_FAV_APP = re.compile(r"\b(?:netflix|youtube|you tube)\s+(?:em|no|na|com)\s+(.+)$")
RE_FAV_TV = re.compile(rf"\b{VERBO_ABRIR}\s+(.+?)\s+(?:na|no)\s+(?:tv|televisao)\b")


def _nome_favorito(trecho: str) -> str:
    """Limpa o nome dito: tira artigo do começo e “na tv (da sala)” do fim."""
    nome = re.sub(r"\s*\b(?:na|no)\s+(?:tv|televisao)\b.*$", "", trecho.strip())
    nome = re.sub(r"^(?:o|a|os|as)\s+", "", nome).strip(" .,!?")
    return "" if re.match(r"^(?:tv|televisao)\b", nome) else nome


def _apelido(t: str, tvs) -> Optional[str]:
    """A TV citada pelo nome. Um nome que não está na ponte também volta, para ser recusado,
    em vez de cair na TV padrão ("desliga a tv do quarto" nunca desliga a da sala)."""
    for a in tvs or []:
        if re.search(rf"\b{re.escape(_norm(a))}\b", t):
            return a
    m = re.match(r"/tv\s+([a-z0-9]+)\s+\S", t) or re.search(r"\b(?:tv|televisao)\s+(?:da|do|de)\s+([a-z0-9]+)", t)
    if m and m.group(1) not in VOCABULARIO and not m.group(1).isdigit():
        return m.group(1)
    return None


def interpretar(texto: str, tvs=None) -> Optional[tuple]:
    """Entende um pedido de TV. Devolve (acao, args, apelido) ou None se não for sobre a TV."""
    bruto = (texto or "").strip()
    t = _norm(bruto)
    pede_favorito = re.match(rf"{VERBO_ABRIR}\b", t) and RE_FAV_APP.search(t)    # "abre a netflix em The Chosen"
    if not RE_TV.search(t) and not pede_favorito:
        return None
    if not t.startswith("/tv") and len(t.split()) > PALAVRAS_MAX:
        return None           # frase longa que só cita a TV ("vi na tv que…") não vira comando

    # Favoritos guardados na ponte (valem para todas as TVs)
    salvar = re.match(r"^/tv\s+favorito\s+(.+?)\s+(\S*(?:netflix|youtu)\S*)\s*$", bruto, re.I)
    if salvar:
        return "tv.favorito_salvar", {"nome": salvar.group(1), "link": salvar.group(2)}, None
    if re.match(r"^/tv\s+favoritos?\s*$", t):
        return "tv.favoritos", {}, None
    apagar = re.match(r"^/tv\s+(?:esquecer|apagar favorito|tirar favorito)\s+(.+)$", bruto, re.I)
    if apagar:
        return "tv.favorito_apagar", {"nome": apagar.group(1)}, None

    apelido = _apelido(t, tvs if tvs is not None else FILA.tvs)

    m = RE_AVISO.search(t)
    if m:
        inicio = (m.start(1) if m.group(1) else m.start(2))
        return "tv.aviso", {"texto": bruto[inicio:].strip()}, apelido
    # O som vem antes de ligar/desligar: "desliga o som da tv" não pode desligar a TV.
    if re.search(r"\b(tira|sai|desliga)\b[^.]*\bmudo\b|\bdesmuta|\b(volta|devolve|liga) o som\b|\bcom som\b", t):
        return "tv.volume", {"modo": "som"}, apelido
    if re.search(r"\b(mudo|muta|mutar|silencia|silenciar|sem som|(tira|corta|desliga) o som)\b", t):
        return "tv.volume", {"modo": "mudo"}, apelido
    if re.search(r"\b(desliga|desligar|desligue|apaga|apague|apagar)\b", t):
        return "tv.desligar", {}, apelido
    if re.search(r"\b(liga|ligar|ligue|acende|acenda)\b", t):
        return "tv.ligar", {}, apelido
    numero = re.search(r"\bvolume\D{0,12}(\d{1,3})\b|\b(\d{1,3})\s*de volume\b", t)
    if numero:
        return "tv.volume", {"modo": "definir", "valor": int(numero.group(1) or numero.group(2))}, apelido
    if re.search(r"\b(aumenta|aumentar|sobe|subir|mais alto)\b", t):
        return "tv.volume", {"modo": "subir"}, apelido
    if re.search(r"\b(abaixa|abaixar|diminui|diminuir|desce|descer|mais baixo)\b", t):
        return "tv.volume", {"modo": "descer"}, apelido
    fav = RE_FAV_APP.search(t)
    if fav and _nome_favorito(fav.group(1)):
        return "tv.favorito_abrir", {"nome": _nome_favorito(fav.group(1))}, apelido
    for falado, app in APP_FALADO.items():
        if re.search(rf"\b{falado}\b", t):
            return "tv.abrir_app", {"app": app}, apelido
    fav = RE_FAV_TV.search(t)
    if fav and _nome_favorito(fav.group(1)) and not re.search(r"\b(?:hdmi|volume|som)\b", t):
        # "abre The Chosen na tv": a ponte procura o favorito e, se não houver, diz quais existem
        return "tv.favorito_abrir", {"nome": _nome_favorito(fav.group(1))}, apelido
    hdmi = re.search(r"\bhdmi\s*(\d)\b", t)
    if hdmi:
        return "tv.entrada", {"hdmi": int(hdmi.group(1))}, apelido
    if re.search(r"\b(pausa|pause|pausar|pare)\b", t):
        return "tv.pause", {}, apelido
    if re.search(r"\b(play|continua|continuar|despausa|retoma|retomar|solta)\b", t):
        return "tv.play", {}, apelido
    if re.search(r"\b(estado|status|como esta)\b", t):
        return "tv.estado", {}, apelido
    return None


def ajuda() -> str:
    linhas = ["📺 *TV LG*"]
    estado = "ligada" if FILA.online() else "desligada"
    linhas.append(f"Ponte de casa: {estado}" + (f" · TVs: {', '.join(FILA.tvs)}" if FILA.tvs else ""))
    linhas += ["", "Exemplos:", "▸ `desliga a tv` · `liga a tv do quarto`",
               "▸ `volume 15` na tv · `aumenta o volume da tv` · `tv no mudo`",
               "▸ `abre o netflix na tv` (youtube, netflix, globoplay, prime)",
               "▸ `tv hdmi 2` · `pausa a tv` · `play na tv` · `/tv estado`",
               "▸ `/tv aviso O jantar está pronto`",
               "", "Favoritos (Netflix e YouTube):",
               "▸ `/tv favorito The Chosen https://www.netflix.com/watch/…` — guarda",
               "▸ `abre The Chosen na tv` · `abre a netflix em The Chosen` — abre já no título",
               "▸ `/tv favoritos` — lista · `/tv esquecer The Chosen` — tira",
               "_Se a Netflix pedir o perfil, escolha no controle: a Bella não mexe em perfil nem PIN._"]
    return "\n".join(linhas)


def atender(texto: str) -> Optional[str]:
    """Para o roteador: resposta ao pedido de TV, ou None se o texto não for de TV."""
    t = _norm(texto).strip()
    pedido = interpretar(texto)
    if not pedido:
        return ajuda() if t.startswith("/tv") else None
    acao, args, tv = pedido
    try:
        return executar(acao, args, tv)
    except ErroTV as ex:
        return f"⚠️ {ex}"
