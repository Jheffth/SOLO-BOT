"""Geração de texto xAI, sem ferramentas, sem histórico e sem registrar segredos."""
import logging
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
