"""Geração de texto xAI, sem ferramentas, sem histórico e sem registrar segredos."""
import logging
import time
import httpx
import config

log = logging.getLogger("solobot.grok")
API = "https://api.x.ai/v1/responses"


def gerar(instrucao, texto, json_saida=False, max_tokens=1536, temperatura=.7, timeout=18, historico=None):
    if not config.GROK_API_KEY:
        return None
    regra = instrucao + ("\nResponda somente um objeto JSON válido, sem cercas Markdown." if json_saida else "")
    corpo = {"model": config.GROK_TEXT_MODEL, "store": False,
             "input": [{"role": "system", "content": regra},
                       *[{"role": papel, "content": conteudo} for papel, conteudo in (historico or [])],
                       {"role": "user", "content": texto}],
             "max_output_tokens": max_tokens, "temperature": temperatura}
    if config.GROK_TEXT_MODEL.startswith(("grok-4.5", "grok-4.6", "grok-4.7")):
        corpo["reasoning"] = {"effort": "low"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as cliente:
            r = cliente.post(API, headers={"Authorization": "Bearer " + config.GROK_API_KEY}, json=corpo)
        r.raise_for_status()
        dados = r.json()
        if dados.get("status") != "completed":
            return None
        saida = "".join(p.get("text", "") for item in dados.get("output", [])
                        if item.get("type") == "message" and item.get("role") == "assistant"
                        for p in item.get("content", []) if p.get("type") == "output_text").strip()
        return saida or None
    except Exception as erro:
        log.warning("Grok texto indisponível: %s", type(erro).__name__)
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
