"""Uma geração explícita por pedido; sem URLs externas ou chaves no cliente."""
import base64
import logging
import httpx
import config

log = logging.getLogger("solobot.grok_imagens")
MAX_BYTES = 8 * 1024 * 1024
API = "https://api.x.ai/v1/images/generations"


class FalhaImagem(Exception):
    pass


def gerar(prompt):
    if not config.GROK_API_KEY:
        raise FalhaImagem("Configure a chave do Grok no servidor para gerar imagens.")
    try:
        with httpx.Client(timeout=120, follow_redirects=False) as cliente:
            r = cliente.post(API, headers={"Authorization": "Bearer " + config.GROK_API_KEY},
                             json={"model": config.GROK_IMAGE_MODEL, "prompt": prompt,
                                   "n": 1, "response_format": "b64_json"})
        if r.status_code in (400, 403, 422):
            raise FalhaImagem("O Grok não aceitou esse pedido de imagem. Ajuste a descrição ou confira o acesso ao modelo.")
        if r.status_code in (401, 402):
            raise FalhaImagem("Confira a chave, o saldo e o acesso ao modelo de imagens no Grok.")
        r.raise_for_status()
        dados = r.json()["data"]
        if len(dados) != 1:
            raise ValueError()
        codigo = dados[0]["b64_json"]
        if not isinstance(codigo, str) or len(codigo) > (MAX_BYTES * 4 // 3 + 4):
            raise ValueError()
        conteudo = base64.b64decode(codigo, validate=True)
        if not 0 < len(conteudo) <= MAX_BYTES:
            raise ValueError()
        if conteudo.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        else:
            raise ValueError()
        return {"imagem_base64": codigo, "imagem_mime": mime}
    except FalhaImagem:
        raise
    except httpx.TimeoutException:
        raise FalhaImagem("A geração demorou além do limite. Não houve reenvio automático; confira seu uso no Grok antes de tentar novamente.") from None
    except Exception as erro:
        log.warning("Geração de imagem falhou: %s", type(erro).__name__)
        raise FalhaImagem("Não consegui receber uma imagem válida do Grok. Não reenviei o pedido automaticamente.") from None
