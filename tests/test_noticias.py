"""Notícias reais para as modelos (nucleo/noticias.py)."""
from types import SimpleNamespace

import pytest

from nucleo import noticias

GOOGLE_RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>PRF divulga edital com 1.200 vagas - CNN Brasil</title><link>https://n/1</link>
<pubDate>Tue, 24 Nov 2026 10:00:00 GMT</pubDate><source url="https://cnn">CNN Brasil</source></item>
<item><title>Cebraspe confirma banca do concurso da PRF - Folha Dirigida</title><link>https://n/2</link>
<pubDate>Mon, 23 Nov 2026 18:30:00 GMT</pubDate></item>
<item><title>curto</title></item>
<item><title>PRF divulga edital com 1.200 vagas - CNN Brasil</title><link>https://n/3</link></item>
</channel></rss>"""


@pytest.fixture()
def rss(monkeypatch):
    pedidos = []
    monkeypatch.setattr(noticias, "_baixar", lambda url: pedidos.append(url) or GOOGLE_RSS)
    return pedidos


@pytest.mark.parametrize("texto,tema", [
    ("Bella, quais as notícias de hoje?", None),
    ("saiu edital da PRF?", "prf"),
    ("me conta as novidades de tecnologia", "tecnologia"),
    ("quem ganhou o jogo do Flamengo ontem?", "futebol"),
    ("tem novidade de concurso?", "concursos"),
    ("/noticias prf", "prf"),
])
def test_reconhece_pedidos_de_noticia(texto, tema):
    p = noticias.pedido(texto)
    assert p is not None and p["tema"] == tema


@pytest.mark.parametrize("texto", [
    "me conta as novidades do seu dia", "te amo", "gastei 30 no almoço", "transfira 380 reais para o Mercado Pago",
    "o que você acha de mim?", "/hoje",
])
def test_conversa_comum_nao_vira_busca(texto):
    assert noticias.pedido(texto) is None


def test_busca_le_titulo_veiculo_e_data_sem_repetir(rss):
    itens = noticias.buscar("prf")
    assert [i["titulo"] for i in itens] == ["PRF divulga edital com 1.200 vagas", "Cebraspe confirma banca do concurso da PRF"]
    assert itens[0]["fonte"] == "CNN Brasil" and itens[1]["fonte"] == "Folha Dirigida" and itens[0]["quando"] == "24/11 10:00"
    assert "news.google.com" in rss[0] and "when%3A2d" not in rss[0]


def test_cache_de_15_minutos(rss):
    noticias.buscar("prf")
    noticias.buscar("prf")
    assert len(rss) == 1


def test_nota_traz_os_fatos_e_proibe_inventar(rss):
    n = noticias.nota("saiu edital da PRF?")
    assert "PRF divulga edital com 1.200 vagas · CNN Brasil" in n and "não invente" in n and "INTERNO" in n


def test_sem_fonte_a_nota_manda_nao_inventar():
    n = noticias.nota("quais as notícias de hoje?")
    assert "não encontrou nada" in n and "não invente" in n


def test_pergunta_especifica_busca_os_termos_dele(rss):
    noticias.nota("quem ganhou o jogo do Flamengo ontem?")
    assert "flamengo" in rss[-1].lower() and "ganhou" in rss[-1].lower()


def test_modelo_recebe_a_nota_junto_da_fala(monkeypatch, rss):
    from nucleo import bella_conversa, models
    vistos = []
    monkeypatch.setattr(models, "selecionado", lambda conta_id: "isa")
    monkeypatch.setattr(models, "responder", lambda texto, numero_conta, canal=None, nota_interna="", **k:
                        vistos.append((texto, nota_interna)) or "Amor, saiu sim! 💋")
    assert bella_conversa.responder("Bella, saiu edital da PRF?", conta_id=1) == "Amor, saiu sim! 💋"
    texto, nota = vistos[0]
    assert texto == "Bella, saiu edital da PRF?" and "PRF divulga edital" in nota


def test_conversa_comum_nao_busca(monkeypatch, rss):
    from nucleo import bella_conversa, models
    vistos = []
    monkeypatch.setattr(models, "selecionado", lambda conta_id: "isa")
    monkeypatch.setattr(models, "responder", lambda texto, numero_conta, canal=None, nota_interna="", **k:
                        vistos.append(nota_interna) or "oi")
    bella_conversa.responder("estou com saudade", conta_id=1)
    assert vistos == [""] and rss == []


def test_pedido_de_noticia_e_conversa_nao_sistema():
    from nucleo import roteador
    assert roteador._pede_noticia("Júlia, quais as notícias de hoje?")
    assert not roteador._pede_noticia("quanto tenho no Nubank?")


def test_iniciativa_da_modelo_com_noticia_real(monkeypatch):
    from nucleo import bella_iniciativa, models
    monkeypatch.setattr(noticias, "manchete_de_interesse", lambda: {"titulo": "Nova IA brasileira é lançada", "fonte": "g1",
                                                                    "tema": "tecnologia"})
    chamadas = []
    monkeypatch.setattr(models, "iniciar", lambda conta, tipo, dados, noticia=None: chamadas.append((tipo, noticia)) or None)
    bella_iniciativa._enviar_models(None, SimpleNamespace(id=1), {}, SimpleNamespace(canal="whatsapp", origem="x"), "noticia")
    assert chamadas == [("noticia", {"titulo": "Nova IA brasileira é lançada", "fonte": "g1", "tema": "tecnologia"})]


def test_iniciativa_sem_noticia_segue_espontanea(monkeypatch):
    from nucleo import bella_iniciativa, models
    monkeypatch.setattr(noticias, "manchete_de_interesse", lambda: None)
    chamadas = []
    monkeypatch.setattr(models, "iniciar", lambda conta, tipo, dados, noticia=None: chamadas.append((tipo, noticia)) or None)
    bella_iniciativa._enviar_models(None, SimpleNamespace(id=1), {}, SimpleNamespace(canal="whatsapp", origem="x"), "noticia")
    assert chamadas == [("espontanea", None)]


def test_instrucao_da_iniciativa_cita_a_noticia(monkeypatch):
    from nucleo import grok, models
    conta = SimpleNamespace(id=1, admin=True)
    monkeypatch.setattr(models, "selecionado", lambda conta_id: "isa")
    monkeypatch.setattr(models, "pacote", lambda conta, ident: {"nome": "Isabella", "iniciativa": {"ativa": True},
                        "vozes_por_conta": [{"principal": True, "ativa": True}], "classificacao": "adulto", "conteudo_adulto_habilitado": True})
    monkeypatch.setattr(models, "_montar_contexto", lambda *a, **k: {"perfil_modelo": {}, "blocos": [], "historico": [],
                        "memorias_usadas": [], "estado": {}})
    monkeypatch.setattr(models, "_gravar", lambda *a, **k: None)
    vistos = []
    monkeypatch.setattr(grok, "gerar", lambda instr, texto, **k: vistos.append(instr) or "Viu isso, amor?")
    texto = models.iniciar(conta, "noticia", {"ligada": True}, noticia={"titulo": "Nova IA brasileira é lançada",
                                                                         "fonte": "g1", "tema": "tecnologia"})
    assert texto == "Viu isso, amor?" and "Nova IA brasileira é lançada" in vistos[0] and "não invente" in vistos[0]
