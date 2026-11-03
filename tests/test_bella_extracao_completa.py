"""Seleção completa com cenário desmarcado e referência obrigatória."""
import base64
import pytest
from fastapi import HTTPException
from nucleo import prompts_bella as pb
from routers import bella
from test_bella_grok import autenticar, _prompt_valido

SELECAO = ["modelo", "roupas", "pose", "penteado", "cor", "olhos", "maquiagem", "pintura", "efeitos", "acessorios", "tatuagens", "expressao"]
PEDIDO = "/promptmodelo [[extrair: " + ", ".join(SELECAO) + "]]"


def test_selecao_12_sem_cenario_nao_contradiz_cabelo():
    limpo, elementos = pb.elementos_extrair(PEDIDO)
    assert elementos == SELECAO
    instrucao = pb.instrucao_seletiva(elementos)
    copiar, restante = instrucao.split("- Todo o resto", 1)
    for elemento in elementos:
        assert pb._ELEMENTOS_EXTRAIR[elemento][0] + ":" in copiar
    assert "NÃO copie a cor do cabelo" not in copiar
    assert "NÃO copie o formato (corte" not in copiar
    assert "NÃO copie o rosto, a pele" not in copiar
    assert "NÃO copie o formato dos olhos" not in copiar
    assert "(cenário)" in restante
    assert "frase fixa contradisser" in instrucao


def test_pedido_completo_vai_com_foto_e_12_categorias(monkeypatch):
    autenticar(monkeypatch)
    vistos = []
    monkeypatch.setattr(pb.grok, "gerar", lambda regra, texto, **kw: vistos.append((regra, texto, kw)) or _prompt_valido())
    monkeypatch.setattr(bella, "_guardar_fala", lambda *a: "voz-teste")
    foto = base64.b64encode(b"foto-teste").decode()
    resposta = bella.conversa(bella.PedidoConversa(texto=PEDIDO, modo="safada", imagem_base64=foto, imagem_mime="image/jpeg"), "teste", None)
    assert resposta["texto"]
    regra, texto, kw = vistos[0]
    assert kw["imagens"] == [("image/jpeg", foto)]
    for elemento in SELECAO:
        assert pb._ELEMENTOS_EXTRAIR[elemento][0] in texto
    assert "Cenário" not in texto


def test_selecao_sem_imagem_nao_gera_prompt_aleatorio(monkeypatch):
    autenticar(monkeypatch)
    monkeypatch.setattr(pb, "_REFERENCIAS", {})
    monkeypatch.setattr(pb.grok, "gerar", lambda *a, **kw: pytest.fail("gerou sem referência"))
    with pytest.raises(HTTPException) as erro:
        bella.conversa(bella.PedidoConversa(texto=PEDIDO, modo="safada"), "teste", None)
    assert erro.value.status_code == 422
    assert "imagem" in erro.value.detail.lower()


def test_pedido_livre_nao_exige_foto_so_por_mencionar_roupa(monkeypatch):
    autenticar(monkeypatch)
    monkeypatch.setattr(pb, "_REFERENCIAS", {})
    vistos = []
    monkeypatch.setattr(pb.grok, "gerar", lambda regra, texto, **kw: vistos.append(kw) or _prompt_valido())
    monkeypatch.setattr(bella, "_guardar_fala", lambda *a: "voz-teste")
    assert bella.conversa(bella.PedidoConversa(texto="/promptmodelo use um vestido azul", modo="safada"), "teste", None)["texto"]
    assert vistos[0]["imagens"] is None
