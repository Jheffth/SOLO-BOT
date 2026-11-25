"""
NOTÍCIAS REAIS PARA AS MODELOS — o Solo Bot busca; a modelo só conta, no jeito dela.

  · Fontes sem chave: busca do Google Notícias (RSS, por assunto, últimos 2 dias) e, de reserva, os RSS do G1 e do ge.
  · Temas de interesse do Arquiteto: tecnologia, concursos, PRF e futebol.
  · `pedido(texto)` reconhece quando ele pede notícia ("quais as notícias de hoje?", "saiu edital da PRF?",
    "quem ganhou o jogo ontem?"); `nota(texto)` busca e devolve a nota interna que vai junto da fala dele.
    A modelo usa SÓ o que veio da busca (o DeepSeek não tem internet) e cita a fonte.
  · `manchete_de_interesse()` dá uma notícia real de um dos temas para a modelo puxar assunto sozinha.
  · Cache de 15 min por busca; se as fontes não responderem, a nota diz isso e ela não inventa.
"""
import logging
import random
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import quote_plus

import httpx

log = logging.getLogger("solobot.noticias")

GOOGLE = "https://news.google.com/rss/search?q={q}+when:2d&hl=pt-BR&gl=BR&ceid=BR:pt-419"
CACHE_SEGUNDOS = 15 * 60
POR_BUSCA = 6

TEMAS = {                                     # do mais específico ao mais geral
    "prf": {"nome": "PRF", "busca": "PRF \"Polícia Rodoviária Federal\"", "feeds": [],
            "palavras": r"\bprf\b|policia rodoviaria"},
    "tecnologia": {"nome": "tecnologia", "busca": "tecnologia OR \"inteligência artificial\"",
                   "feeds": ["https://g1.globo.com/rss/g1/tecnologia/"],
                   "palavras": r"tecnologia|tech|inteligencia artificial|\bia\b|chatgpt|openai|celular|iphone|android|"
                               r"google|apple|samsung|microsoft|nvidia|games?\b|videogame"},
    "concursos": {"nome": "concursos", "busca": "concurso público edital",
                  "feeds": ["https://g1.globo.com/rss/g1/concursos-e-emprego/"],
                  "palavras": r"concursos?|edita(?:l|is)|banca|cebraspe|cespe|\bfgv\b|vagas? publicas?|servidor publico"},
    "futebol": {"nome": "futebol", "busca": "futebol",
                "feeds": ["https://ge.globo.com/rss/ge/futebol/"],
                "palavras": r"futebol|brasileirao|libertadores|sul-americana|copa do brasil|champions|selecao|"
                            r"flamengo|corinthians|palmeiras|sao paulo|vasco|gremio|internacional|cruzeiro|atletico|"
                            r"botafogo|fluminense|santos|bahia|fortaleza|placar|\bgol(?:s|aco)?\b|rodada|campeonato"},
}

# Pedido de notícia: palavra de notícia, ou um tema + verbo de novidade ("saiu edital da PRF?", "como foi o Flamengo?").
_PEDE = re.compile(r"\b(?:noticias?|manchetes?|atualidades|jornal de hoje|"
                   r"o que (?:ta|esta|anda) rolando (?:no mundo|hoje|no brasil|por ai|nas noticias)|"
                   r"o que aconteceu (?:hoje|ontem|no mundo|no brasil)|quem ganhou|resultado d[oa]s? jogos?|"
                   r"como (?:foi|ficou) o jogo)\b")
_NOVIDADE = re.compile(r"\b(?:novidades?|novo|nova|saiu|sai|vai sair|teve|tem algo|aconteceu|como (?:foi|ficou|esta)|"
                       r"resultado|ganhou|perdeu|empatou|anunciou|lancou|lancamento|previsao)\b")
_SOBRE_ELA = re.compile(r"\b(?:seu dia|sua vida|voce|contigo|com voce|de voce|da gente|nossa)\b")
_VAZIAS = set("""a o as os um uma uns umas de do da dos das no na nos nas em por para pra pro com e ou que qual quais
quanto quem como me te se ja hoje ontem agora ai la aqui isso esse essa este esta tem teve tinha sobre algo alguma
alguem coisa coisas noticia noticias novidade novidades manchete manchetes atualidades saiu sai vai rolando ta esta
anda conta conte fala fale diz diga mostra mostre manda mande quero queria gostaria pode poderia voce bella amor
mundo brasil sabe sabia viu""".split())


def _norm(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (texto or "").lower()) if unicodedata.category(c) != "Mn")


def tema_de(texto: str) -> Optional[str]:
    t = _norm(texto)
    for chave, tema in TEMAS.items():
        if re.search(tema["palavras"], t):
            return chave
    return None


def pedido(texto: str) -> Optional[dict]:
    """{'tema', 'consulta'} quando a mensagem pede notícia; senão None."""
    t = _norm(texto)
    if not t or t.startswith("/") and not t.startswith("/noticias"):
        return None
    tema = tema_de(t)
    if not (_PEDE.search(t) or t.startswith("/noticias") or (tema and _NOVIDADE.search(t))):
        return None
    if not tema and _SOBRE_ELA.search(t) and not _PEDE.search(t):
        return None                                   # "me conta as novidades do seu dia": conversa, não jornal
    palavras = [p for p in re.findall(r"[a-z0-9]+", t) if p not in _VAZIAS and len(p) > 1 and p != "noticias"]
    especifico = [p for p in palavras if not re.fullmatch(TEMAS[tema]["palavras"], p)] if tema else palavras
    consulta = " ".join(palavras[:8]) if especifico else ""
    return {"tema": tema, "consulta": consulta}


# ── busca ──
_CACHE = {}
_TRAVA = threading.Lock()


def _baixar(url: str) -> bytes:
    r = httpx.get(url, timeout=6, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (SoloBot; leitor de RSS)"})
    r.raise_for_status()
    return r.content


def _ler(url: str) -> List[dict]:
    agora = time.monotonic()
    with _TRAVA:
        guardado = _CACHE.get(url)
    if guardado and agora - guardado[0] < CACHE_SEGUNDOS:
        return guardado[1]
    try:
        raiz = ET.fromstring(_baixar(url))
    except Exception:  # noqa: BLE001  fonte fora do ar ou formato inesperado: sem notícias dessa fonte
        log.info("Notícias: fonte sem resposta (%s)", url.split("?")[0])
        return []
    itens = []
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        fonte = (item.findtext("source") or "").strip()
        if " - " in titulo:                           # Google Notícias: "Título - Veículo"
            resto, veiculo = titulo.rsplit(" - ", 1)
            if not fonte or veiculo.strip() == fonte:
                titulo, fonte = resto, fonte or veiculo
        if not 15 <= len(titulo) <= 240:
            continue
        quando = ""
        try:
            quando = parsedate_to_datetime(item.findtext("pubDate") or "").strftime("%d/%m %H:%M")
        except (TypeError, ValueError):
            pass
        itens.append({"titulo": titulo.strip(), "fonte": fonte.strip() or _fonte_do_link(url), "quando": quando,
                      "link": (item.findtext("link") or "").strip()})
    with _TRAVA:
        _CACHE[url] = (agora, itens)
    return itens


def _fonte_do_link(url: str) -> str:
    return "ge" if "ge.globo" in url else "g1" if "g1.globo" in url else ""


def buscar(tema: Optional[str] = None, consulta: str = "", n: int = POR_BUSCA) -> List[dict]:
    """Notícias de um tema e/ou de uma consulta livre. Sem tema nem consulta: um pouco de cada tema de interesse."""
    if not tema and not consulta:
        itens = []
        for chave in TEMAS:
            itens += buscar(chave, n=2)
        return itens[:max(n, 8)]
    termos = consulta or TEMAS[tema]["busca"]
    if consulta and tema and TEMAS[tema]["nome"].lower() not in consulta:
        termos = f"{consulta} {TEMAS[tema]['nome']}"
    itens = _ler(GOOGLE.format(q=quote_plus(termos)))
    if not itens and tema:
        for feed in TEMAS[tema]["feeds"]:
            itens += _ler(feed)
    vistos, unicos = set(), []
    for item in itens:
        chave = _norm(item["titulo"])[:80]
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(item)
    return unicos[:n]


def nota(texto: str) -> str:
    """Nota interna com as notícias reais para a fala dele ('' se não for pedido de notícia)."""
    p = pedido(texto)
    if not p:
        return ""
    itens = buscar(p["tema"], p["consulta"])
    assunto = p["consulta"] or (TEMAS[p["tema"]]["nome"] if p["tema"] else "os assuntos de que ele gosta")
    if not itens:
        return ("[NOTÍCIAS — INTERNO, não cite esta nota] O sistema buscou notícias recentes sobre "
                f"{assunto} e não encontrou nada (ou as fontes não responderam agora). Diga isso a ele com naturalidade "
                "e não invente nenhuma notícia, placar, data ou número.")
    linhas = "\n".join(f"- {i['titulo']} · {i['fonte'] or 'fonte não informada'}" + (f" · {i['quando']}" if i["quando"] else "")
                       for i in itens)
    return ("[NOTÍCIAS REAIS — busca feita agora pelo sistema; INTERNO, não cite esta nota] Ele pediu notícias sobre "
            f"{assunto}. Resultados (título · veículo · quando):\n{linhas}\n"
            "Conte do seu jeito, numa lista curta com as mais relevantes, dizendo o veículo de cada uma. Use SÓ o que está "
            "aqui: não invente detalhes, números, placares, datas nem desdobramentos que não estejam nos títulos. "
            "Se nada responder exatamente ao que ele perguntou, diga que não achou isso e conte o que achou de mais próximo.")


def manchete_de_interesse() -> Optional[dict]:
    """Uma notícia real de um tema de interesse, para a modelo puxar assunto sozinha."""
    temas = list(TEMAS)
    random.shuffle(temas)
    for chave in temas:
        itens = buscar(chave, n=6)
        if itens:
            escolhida = dict(random.choice(itens[:4]))
            escolhida["tema"] = TEMAS[chave]["nome"]
            return escolhida
    return None


def limpar_cache():
    with _TRAVA:
        _CACHE.clear()
