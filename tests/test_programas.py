import json

import pytest

from nucleo import programas
from routers import bella


WORD = {"id": "a" * 32, "frase": "Faça {pedido}", "tipo": "word"}


@pytest.mark.parametrize("mudancas", [
    {"comando_id": "b" * 32}, {"acao": "executar"}, {"acao": "salvar"},
    {"confianca": True}, {"confianca": .8}, {"texto": ""}, {"texto": "x" * 6001},
    {"texto": "texto\x00invalido"}, {"texto": ["nao e texto"]},
])
def test_nao_aceita_acao_ou_conteudo_invalido(monkeypatch, mudancas):
    d = {"comando_id": WORD["id"], "acao": "escrever", "texto": "Amor e flor", "confianca": .98, **mudancas}
    monkeypatch.setattr(programas.gemini, "gerar", lambda *a, **k: json.dumps(d))
    assert programas.interpretar("Faça uma rima com amor", [WORD])["comando_id"] is None


def test_gera_texto_sem_receber_caminhos_ou_documentos(monkeypatch):
    recebidos = []
    def gerar(instrucao, texto, **opcoes):
        recebidos.append(json.loads(texto))
        return json.dumps({"comando_id": WORD["id"], "acao": "escrever", "texto": "O amor é uma flor.\nFloresce com calor.", "confianca": .99})
    monkeypatch.setattr(programas.gemini, "gerar", gerar)
    r = programas.interpretar("Faça uma rima com amor", [WORD])
    assert r["acao"] == "escrever" and r["texto"].startswith("O amor")
    assert recebidos == [{"pedido": "Faça uma rima com amor", "comandos": [WORD]}]


def test_programa_generico_so_pode_abrir(monkeypatch):
    comando = {**WORD, "tipo": "programa"}
    monkeypatch.setattr(programas.gemini, "gerar", lambda *a, **k: json.dumps({
        "comando_id": WORD["id"], "acao": "escrever", "texto": "texto", "confianca": 1}))
    assert programas.interpretar("abrir editor", [comando])["acao"] is None


@pytest.mark.parametrize("bruto", [None, "", "nao json", "[]", '{"comando_id":null}'])
def test_falha_de_ia_nao_inventa_acao(monkeypatch, bruto):
    monkeypatch.setattr(programas.gemini, "gerar", lambda *a, **k: bruto)
    assert programas.interpretar("rima", [WORD])["comando_id"] is None


def test_indisponibilidade_diferente_de_pedido_ambiguo(monkeypatch):
    monkeypatch.setattr(programas.gemini, "gerar", lambda *a, **k: None)
    assert programas.interpretar("rima", [WORD])["motivo"] == "indisponivel"
    monkeypatch.setattr(programas.gemini, "gerar", lambda *a, **k: '{}')
    assert programas.interpretar("rima", [WORD])["motivo"] == "incerto"


def test_api_exige_chave_e_catalogo_limitado(logado, monkeypatch):
    monkeypatch.setattr(bella, "_JANELAS_PROGRAMAS", {})
    monkeypatch.setattr(programas.gemini, "gerar", lambda *a, **k: json.dumps({
        "comando_id": WORD["id"], "acao": "escrever", "texto": "Amor e flor.", "confianca": 1}))
    corpo = {"texto": "Faça uma rima com amor", "comandos": [WORD]}
    assert logado.post("/api/bella/programa", json=corpo).status_code == 401
    chave = logado.post("/api/conta/bella").json()["chave"]
    h = {"X-Bella-Chave": chave}
    r = logado.post("/api/bella/programa", headers=h, json=corpo)
    assert r.status_code == 200 and r.json()["texto"] == "Amor e flor."
    assert logado.post("/api/bella/programa", headers=h, json={**corpo, "caminho": "C:/Word.exe"}).status_code == 422
    assert logado.post("/api/bella/programa", headers=h, json={**corpo, "comandos": [{**WORD, "caminho": "C:/Word.exe"}]}).status_code == 422
    assert logado.post("/api/bella/programa", headers=h, json={**corpo, "comandos": [WORD, WORD]}).status_code == 422
    logado.delete("/api/conta/bella")
    assert logado.post("/api/bella/programa", headers=h, json=corpo).status_code == 401
