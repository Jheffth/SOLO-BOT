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
    assert "cenário)" in restante and "posição da câmera" in restante
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


def test_posicao_da_camera_e_item_proprio_e_troca_a_camera_fixa():
    limpo, elementos = pb.elementos_extrair("/prompt [[extrair: camera, roupas]]")
    assert elementos == ["roupas", "camera"]
    assert "câmera tem opção própria" in pb._ELEMENTOS_EXTRAIR["pose"][1]
    instrucao = pb.instrucao_seletiva(elementos)
    copiar = instrucao.split("- Todo o resto", 1)[0]
    assert "Posição da câmera:" in copiar and "selfie no espelho" in copiar
    assert "troque as frases fixas de câmera" in instrucao and "9:16" in instrucao
    sem = pb.instrucao_seletiva(["roupas"])
    assert "A posição da câmera NÃO vem da imagem" in sem


def test_camera_reconhecida_no_pedido_escrito():
    assert "camera" in pb.elementos_extrair("copie o ângulo da câmera e a roupa da foto")[1]


def test_posehot_com_camera_ganha_campo_de_camera():
    modelo = pb.modelo_pose(elementos=["pose", "camera"])
    assert "Câmera: [CÂMERA:" in modelo
    assert "Câmera: [CÂMERA:" not in pb.modelo_pose(elementos=["pose"])
    assert "Se 'camera' estiver marcado" in pb.instrucao_pose_seletiva(["pose", "camera"])

