"""Geração de texto xAI, sem ferramentas, sem histórico e sem registrar segredos."""
import contextvars
import logging
import time
import httpx
import config

log = logging.getLogger("solobot.grok")
API = "https://api.x.ai/v1/responses"

# Modo de testes: por pedido (nunca global). Quando ligado, usa GROK_API_KEY_TESTE e anota o resultado da chamada
# (tokens, custo se a xAI informar, ou o motivo da recusa) para a Bella mostrar. Nunca guarda a chave.
_TESTE = contextvars.ContextVar("grok_teste", default=None)


def iniciar_teste():
    """Liga o modo de testes no pedido atual. Devolve o dicionário que acumula o resultado."""
    estado = {"chamadas": 0, "tokens_in": 0, "tokens_out": 0, "custo_usd": None, "erro": None}
    _TESTE.set(estado)
    return estado


def encerrar_teste():
    _TESTE.set(None)


def nota_teste(estado):
    """Uma linha para a tela: o que a API de testes respondeu. Só texto, sem segredos."""
    if estado["erro"]:
        return "🧪 API Grok de Testes: " + estado["erro"]
    if not estado["chamadas"]:
        return "🧪 API Grok de Testes ligada, mas este pedido não chamou o Grok."
    custo = f", custo informado US$ {estado['custo_usd']:.4f}" if estado["custo_usd"] is not None else ", a xAI não informou custo"
    return (f"🧪 API Grok de Testes: ok ({estado['chamadas']} chamada(s), {estado['tokens_in']} tokens de entrada, "
            f"{estado['tokens_out']} de saída{custo}).")


def _motivo(r):
    try:
        corpo = r.json()
        detalhe = corpo.get("error") or corpo.get("message") or ""
        if isinstance(detalhe, dict):
            detalhe = detalhe.get("message", "")
        detalhe = str(detalhe)[:160]
    except Exception:
        detalhe = ""
    dica = {401: "chave recusada", 403: "sem permissão ou sem créditos/saldo nessa chave",
            402: "sem créditos/saldo", 429: "limite de uso atingido"}.get(r.status_code, "")
    return f"recusada (HTTP {r.status_code}{', ' + dica if dica else ''}){': ' + detalhe if detalhe else ''}"


def gerar(instrucao, texto, json_saida=False, max_tokens=1536, temperatura=.7, timeout=18, historico=None,
          imagens=None, modelo=None):
    teste = _TESTE.get()
    chave = config.GROK_API_KEY_TESTE if teste is not None else config.GROK_API_KEY
    if not chave:
        if teste is not None:
            teste["erro"] = "defina GROK_API_KEY_TESTE no .env do servidor."
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
            r = cliente.post(API, headers={"Authorization": "Bearer " + chave}, json=corpo)
        if teste is not None and r.status_code >= 400:
            teste["erro"] = _motivo(r)
        r.raise_for_status()
        dados = r.json()
        if teste is not None:
            teste["chamadas"] += 1
            uso = dados.get("usage") or {}
            teste["tokens_in"] += int(uso.get("input_tokens") or 0)
            teste["tokens_out"] += int(uso.get("output_tokens") or 0)
            ticks = uso.get("cost_in_usd_ticks")
            if isinstance(ticks, (int, float)):
                teste["custo_usd"] = (teste["custo_usd"] or 0) + ticks / 1e10
        if dados.get("status") != "completed":
            return None
        saida = "".join(p.get("text", "") for item in dados.get("output", [])
                        if item.get("type") == "message" and item.get("role") == "assistant"
                        for p in item.get("content", []) if p.get("type") == "output_text").strip()
        return saida or None
    except Exception as erro:
        log.warning("Grok texto indisponível: %s", type(erro).__name__)
        if teste is not None and not teste["erro"]:
            teste["erro"] = f"falhou sem resposta da xAI ({type(erro).__name__})."
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
