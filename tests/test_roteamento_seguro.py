"""Comandos com prefixo e respostas coladas não podem virar lançamentos."""
import httpx
import pytest

from nucleo import modulos
from test_fluxos import _ligar_telegram, _tg, _wa


@pytest.fixture()
def fin(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/interno/manifesto", headers={"X-Solo-Token": "tok-fin"}, json={
        "versao": "teste", "comandos": [
            {"comando": c, "descricao": c} for c in ("/saldo", "/extrato", "/r", "/desfazer")],
        "exemplos": ["recebi 92,60 uber"]})
    _ligar_telegram(logado)
    codigo = logado.post("/api/conta/canais/whatsapp/codigo").json()
    _wa(logado, codigo["mensagem"])
    return logado


@pytest.mark.parametrize("enviar", [_tg, _wa])
@pytest.mark.parametrize("pedido,esperado", [
    ("/fin saldo", "/saldo"), ("/fin Saldo Nubank", "/saldo Nubank"),
    ("/fin /saldo", "/saldo"), ("/fin extrato 30", "/extrato 30"),
    ("/fin desfazer", "/desfazer"), ("/fin r 92,60 Uber diária", "/r 92,60 Uber diária"),
    ("/fin recebi R$ 92,60 na conta Uber", "recebi R$ 92,60 na conta Uber"),
    ("/fin", "/ajuda"),
])
def test_comandos_anunciados_e_frases_livres(fin, sistemas, enviar, pedido, esperado):
    antes = len(sistemas.recebidos)
    enviar(fin, pedido)
    assert len(sistemas.recebidos) == antes + 1
    assert sistemas.recebidos[-1][0] == "fin" and sistemas.recebidos[-1][2]["texto"] == esperado


@pytest.mark.parametrize("enviar", [_tg, _wa])
@pytest.mark.parametrize("prefixo", ["", "/fin "])
def test_resposta_do_usuario_com_exemplo_nao_vira_despesa(fin, sistemas, caixa, enviar, prefixo):
    enviar(fin, "/fin")
    antes = len(sistemas.recebidos)
    texto = ("⚠️ Solo Finances não respondeu. Tente de novo em instantes.\n/fin saldo\n"
             "💰 Finances\n❌ Não identifiquei o valor.\n\n"
             "Tente: gastei 80 almoço nubank\nou: /d 80 almoço nubank")
    enviar(fin, prefixo + texto)
    assert len(sistemas.recebidos) == antes
    assert "resposta do bot copiada" in caixa[-1][2]


def test_lancamento_multilinha_legitimo_e_preservado(fin, sistemas):
    texto = "Recebi R$ 92,60 na conta Uber\nDescrição: diária de motorista."
    _tg(fin, "/fin " + texto)
    assert sistemas.recebidos[-1][2]["texto"] == texto


@pytest.mark.parametrize("enviar", [_tg, _wa])
def test_prefixo_do_rotinas_tambem_normaliza_comando(fin, sistemas, enviar):
    fin.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    fin.post("/interno/manifesto", headers={"X-Solo-Token": "tok-rot"}, json={
        "versao": "teste", "comandos": [{"comando": "/hoje", "descricao": "Hoje"}]})
    enviar(fin, "/rot hoje")
    assert sistemas.recebidos[-1][0] == "rot" and sistemas.recebidos[-1][2]["texto"] == "/hoje"


def test_prefixo_no_canal_siri(fin, sistemas):
    chave = fin.post("/api/conta/atalho").json()["chave"]
    fin.post("/api/atalho", headers={"X-Solo-Chave": chave}, json={"texto": "/fin saldo"})
    assert sistemas.recebidos[-1][2]["texto"] == "/saldo"


@pytest.mark.parametrize("erro", ["Solo Finances demorou para responder.",
                                 "Não consegui conectar ao Solo Finances."])
def test_erros_de_rede_colados_tambem_nao_executam_exemplo(fin, sistemas, caixa, erro):
    antes = len(sistemas.recebidos)
    _tg(fin, erro + "\nTente: gastei 80 almoço nubank")
    assert len(sistemas.recebidos) == antes
    assert "resposta do bot copiada" in caixa[-1][2]


@pytest.mark.parametrize("erro,trecho", [
    (httpx.ReadTimeout, "demorou para responder"),
    (httpx.ConnectTimeout, "Não consegui conectar"),
    (httpx.ConnectError, "Não consegui conectar"),
])
def test_falha_de_comunicacao_nao_reenvia_lancamento(monkeypatch, erro, trecho):
    chamadas = []
    def falhar(url, token, corpo, timeout=None):
        chamadas.append(corpo)
        raise erro("detalhe privado")
    monkeypatch.setattr(modulos, "_post", falhar)
    with pytest.raises(modulos.ErroModulo) as falha:
        modulos.chamar(modulos.por_chave("fin"), "mensagem", {"texto": "recebi 92,60 Uber"})
    assert len(chamadas) == 1
    assert trecho in str(falha.value) and "detalhe privado" not in str(falha.value)
