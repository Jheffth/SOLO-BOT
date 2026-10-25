"""Geração explícita, sem vazamento de chave, URL externa ou execução de sistemas."""
import base64
from threading import BoundedSemaphore
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import config
from nucleo import grok_imagens
from routers import bella

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()


def rede(monkeypatch, status=200, codigo=PNG):
    chamadas = []
    class Cliente:
        def __init__(self, **opcoes):
            assert opcoes == {"timeout": 120, "follow_redirects": False}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **opcoes):
            chamadas.append((url, opcoes))
            return httpx.Response(status, request=httpx.Request("POST", url), json={"data": [{"b64_json": codigo}]})
    monkeypatch.setattr(config, "GROK_API_KEY", "chave-teste")
    monkeypatch.setattr(grok_imagens.httpx, "Client", Cliente)
    return chamadas


def test_gera_uma_imagem_sem_url(monkeypatch):
    chamadas = rede(monkeypatch)
    assert grok_imagens.gerar("Uma cidade") == {"imagem_base64": PNG, "imagem_mime": "image/png"}
    assert len(chamadas) == 1
    url, dados = chamadas[0]
    assert url == "https://api.x.ai/v1/images/generations"
    assert dados["headers"]["Authorization"] == "Bearer chave-teste"
    assert dados["json"] == {"model": config.GROK_IMAGE_MODEL, "prompt": "Uma cidade", "n": 1, "response_format": "b64_json"}


@pytest.mark.parametrize("status", [400, 401, 402, 403, 422, 429, 500])
def test_falhas_nao_reenviam(monkeypatch, status):
    chamadas = rede(monkeypatch, status=status)
    with pytest.raises(grok_imagens.FalhaImagem): grok_imagens.gerar("Uma cidade")
    assert len(chamadas) == 1


@pytest.mark.parametrize("codigo", ["inválido", base64.b64encode(b"<svg>externo</svg>").decode(), "a" * (12 * 1024 * 1024), ""], ids=["base64-invalido", "svg", "excesso", "vazio"])
def test_rejeita_payloads_invalidos(monkeypatch, codigo):
    rede(monkeypatch, codigo=codigo)
    with pytest.raises(grok_imagens.FalhaImagem): grok_imagens.gerar("Uma cidade")


def test_sem_chave_sem_rede(monkeypatch):
    chamadas = rede(monkeypatch)
    monkeypatch.setattr(config, "GROK_API_KEY", "")
    with pytest.raises(grok_imagens.FalhaImagem): grok_imagens.gerar("Uma cidade")
    assert chamadas == []


def preparar_rota(monkeypatch):
    monkeypatch.setattr(bella, "_JANELAS_IMAGENS", {})
    monkeypatch.setattr(bella, "_IMAGENS_VAGAS", BoundedSemaphore(2))
    def autenticar(db, chave):
        if chave != "teste": raise HTTPException(401)
        return SimpleNamespace(id=123)
    monkeypatch.setattr(bella, "_autenticar", autenticar)
    vistos = set()
    def repetido(db, canal, identificador):
        assert canal == "bella-img"
        if identificador in vistos: return True
        vistos.add(identificador)
        return False
    monkeypatch.setattr(bella.roteador, "ja_processada", repetido)


def test_rota_autenticada_e_pedido_unico(monkeypatch):
    preparar_rota(monkeypatch)
    chamadas = []
    monkeypatch.setattr(grok_imagens, "gerar", lambda prompt: chamadas.append(prompt) or {"imagem_base64": PNG, "imagem_mime": "image/png"})
    pedido = bella.PedidoImagem(pedido_id=uuid4(), prompt="Uma cidade")
    with pytest.raises(HTTPException) as erro: bella.imagem(pedido, "errada", None)
    assert erro.value.status_code == 401 and chamadas == []
    assert bella.imagem(pedido, "teste", None)["imagem_mime"] == "image/png"
    with pytest.raises(HTTPException) as erro: bella.imagem(pedido, "teste", None)
    assert erro.value.status_code == 409 and chamadas == ["Uma cidade"]


def test_limite_concorrente_e_liberacao(monkeypatch):
    preparar_rota(monkeypatch)
    vagas = BoundedSemaphore(1)
    monkeypatch.setattr(bella, "_IMAGENS_VAGAS", vagas)
    vagas.acquire()
    pedido = bella.PedidoImagem(pedido_id=uuid4(), prompt="Uma cidade")
    with pytest.raises(HTTPException) as erro: bella.imagem(pedido, "teste", None)
    assert erro.value.status_code == 429
    vagas.release()
    def falha(prompt): raise grok_imagens.FalhaImagem("Erro de teste")
    monkeypatch.setattr(grok_imagens, "gerar", falha)
    with pytest.raises(HTTPException) as erro: bella.imagem(pedido, "teste", None)
    assert erro.value.status_code == 502
    assert vagas.acquire(blocking=False)
    vagas.release()


def test_contrato_sem_destinos_ou_modelo_livres():
    for extra in [{"url": "https://externo"}, {"modelo": "outro"}, {"prompt": "x" * 1801}]:
        with pytest.raises(ValidationError): bella.PedidoImagem(**{"pedido_id": uuid4(), "prompt": "Uma cidade", **extra})
