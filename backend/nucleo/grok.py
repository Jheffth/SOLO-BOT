"""Geração de texto xAI, sem ferramentas, sem histórico e sem registrar segredos."""
import logging
import threading
import time
import httpx
import config

log = logging.getLogger("solobot.grok")
API = "https://api.x.ai/v1/responses"
_ULTIMO = threading.local()


def registrar_motivo(texto):
    _ULTIMO.motivo = texto


def motivo():
    """Por que a última chamada desta thread não deu resposta (sem segredos), ou "" se não houve falha."""
    return getattr(_ULTIMO, "motivo", "") or ""


def gerar(instrucao, texto, json_saida=False, max_tokens=1536, temperatura=.7, timeout=18, historico=None,
          imagens=None, modelo=None):
    _ULTIMO.motivo = ""
    if not config.GROK_API_KEY:
        _ULTIMO.motivo = "a chave GROK_API_KEY não está definida no servidor"
        return None
    regra = instrucao + ("\nResponda somente um objeto JSON válido, sem cercas Markdown." if json_saida else "")
    modelo = modelo or config.GROK_TEXT_MODEL
    pedido = texto
    if imagens:       # [(mime, base64)]: o Grok olha as imagens junto com o texto
        pedido = [{"type": "input_text", "text": texto},
                  *[{"type": "input_image", "image_url": f"data:{mime};base64,{b64}"} for mime, b64 in imagens]]
    corpo = {"model": modelo, "store": False,
             "input": [{"role": "system", "content": regra},
                       *[{"role": papel, "content": conteudo} for papel, conteudo in (historico or [])],
                       {"role": "user", "content": pedido}],
             "max_output_tokens": max_tokens, "temperature": temperatura}
    if modelo.startswith(("grok-4.5", "grok-4.6", "grok-4.7")):
        corpo["reasoning"] = {"effort": "low"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as cliente:
            r = cliente.post(API, headers={"Authorization": "Bearer " + config.GROK_API_KEY}, json=corpo)
        if r.status_code >= 400:
            try:
                detalhe = str(r.json().get("error") or r.json().get("message") or "")[:140]
            except Exception:
                detalhe = ""
            _ULTIMO.motivo = f"a xAI recusou a chamada (HTTP {r.status_code}){': ' + detalhe if detalhe else ''}"
        r.raise_for_status()
        dados = r.json()
        if dados.get("status") != "completed":
            razao = (dados.get("incomplete_details") or {}).get("reason") or dados.get("status")
            _ULTIMO.motivo = f"a resposta do Grok veio incompleta ({razao}); o limite de tokens pode ter acabado"
            return None
        saida = "".join(p.get("text", "") for item in dados.get("output", [])
                        if item.get("type") == "message" and item.get("role") == "assistant"
                        for p in item.get("content", []) if p.get("type") == "output_text").strip()
        if not saida:
            _ULTIMO.motivo = "o Grok devolveu uma resposta vazia"
        return saida or None
    except Exception as erro:
        log.warning("Grok texto indisponível: %s", type(erro).__name__)
        if not _ULTIMO.motivo:
            _ULTIMO.motivo = ("o Grok demorou demais para responder (tempo esgotado)" if "Timeout" in type(erro).__name__
                              else f"falha ao falar com o Grok ({type(erro).__name__})")
        return None


MANAGEMENT_API = "https://management-api.x.ai"
_SALDO = {"quando": 0.0, "valor": None}


def saldo_disponivel():
    return bool(config.XAI_MANAGEMENT_KEY and config.XAI_TEAM_ID)


def saldo(forcar=False):
    """Saldo pré-pago em dólares: {"saldo_usd": 12.34} ou {"erro": "..."}. Cache de 60 s; nunca levanta."""
    if not saldo_disponivel():
        return {"erro": "Defina XAI_MANAGEMENT_KEY e XAI_TEAM_ID no .env."}
    if not forcar and _SALDO["valor"] and time.monotonic() - _SALDO["quando"] < 60:
        return _SALDO["valor"]
    url = f"{MANAGEMENT_API}/v1/billing/teams/{config.XAI_TEAM_ID}/prepaid/balance"
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as cliente:
            r = cliente.get(url, headers={"Authorization": "Bearer " + config.XAI_MANAGEMENT_KEY})
        if r.status_code in (401, 403):
            return {"erro": "A xAI recusou a chave de gerenciamento. Confira XAI_MANAGEMENT_KEY (não é a chave normal do Grok)."}
        if r.status_code == 404:
            return {"erro": "A xAI não encontrou o time. Confira XAI_TEAM_ID."}
        r.raise_for_status()
        centavos = int(str(r.json()["total"]["val"]))
        valor = {"saldo_usd": abs(centavos) / 100}
    except Exception as erro:
        log.warning("Saldo do Grok indisponível: %s", type(erro).__name__)
        return {"erro": "Não consegui consultar o saldo na xAI agora."}
    _SALDO.update(quando=time.monotonic(), valor=valor)
    return valor
