"""Referência avulsa da Bella: uso único, erros e isolamento."""
import base64
import pytest
from fastapi import HTTPException
from test_bella_grok import autenticar, _prompt_valido
from nucleo import grok, prompts_bella as pb
from routers import bella

@pytest.mark.parametrize("falha", [False, True])
def test_anexo_so_no_pedido_atual(monkeypatch, falha):
    autenticar(monkeypatch)
    monkeypatch.setattr(pb, "_REFERENCIAS", {})
    vistos = []
    def gerar(*args, **kw):
        vistos.append(kw.get("imagens"))
        if falha and len(vistos) == 1:
            return "RECUSA: referência não aceita"
        return _prompt_valido()
    monkeypatch.setattr(grok, "gerar", gerar)
    monkeypatch.setattr(bella, "_guardar_fala", lambda *a: "voz")
    pedido = bella.PedidoConversa(texto="prompt dessa roupa, banheiro", modo="safada",
        imagem_mime="image/jpeg", imagem_base64=base64.b64encode(b"imagem-teste").decode())
    if falha:
        with pytest.raises(HTTPException) as erro:
            bella.conversa(pedido, "teste", None)
        assert erro.value.status_code == 422
    else:
        assert bella.conversa(pedido, "teste", None)["texto"].endswith(pb.TAG_FINAL)
    assert vistos[0] == [("image/jpeg", pedido.imagem_base64)]
    assert not pb._REFERENCIAS
    bella.conversa(bella.PedidoConversa(texto="/prompt escritório", modo="safada"), "teste", None)
    assert vistos[1] is None

@pytest.mark.parametrize("imagem,mime", [("!", "image/jpeg"), ("", "image/jpeg"), ("YWJj", "image/gif")])
def test_anexo_invalido(monkeypatch, imagem, mime):
    autenticar(monkeypatch)
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: pytest.fail("imagem inválida chegou ao modelo"))
    with pytest.raises(HTTPException) as erro:
        bella.conversa(bella.PedidoConversa(texto="prompt", modo="safada", imagem_base64=imagem, imagem_mime=mime), "teste", None)
    assert erro.value.status_code == 422
