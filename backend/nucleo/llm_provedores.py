"""Outros provedores de texto além da xAI: DeepSeek (formato OpenAI) e Gemini. Mesma assinatura do grok.gerar, sem segredos nos logs."""
import logging
import httpx
import config

log = logging.getLogger("solobot.llm")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
_CATEGORIAS_GEMINI = ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                      "HARM_CATEGORY_DANGEROUS_CONTENT")


def _detalhe(r):
    try:
        e = r.json().get("error")
        return str(e.get("message") if isinstance(e, dict) else e or "")[:140]
    except Exception:  # noqa: BLE001
        return ""


def _nome_erro(erro, nome):
    return (f"o {nome} demorou demais para responder (tempo esgotado)" if "Timeout" in type(erro).__name__
            else f"falha ao falar com o {nome} ({type(erro).__name__})")


def chave(provedor):
    return {"deepseek": config.DEEPSEEK_API_KEY, "gemini": config.GEMINI_API_KEY or config.GEMINI_API_KEY_RESERVA}.get(provedor, "")


def deepseek(instrucao, texto, json_saida, max_tokens, temperatura, timeout, historico, imagens, registrar):
    if not config.DEEPSEEK_API_KEY:
        registrar("a chave DEEPSEEK_API_KEY não está definida no servidor")
        return None
    regra = instrucao + ("\nResponda somente um objeto JSON válido, sem cercas Markdown." if json_saida else "")
    pedido = texto
    if imagens:
        pedido = [{"type": "text", "text": texto},
                  *[{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}} for mime, b64 in imagens]]
    corpo = {"model": config.DEEPSEEK_MODEL, "stream": False,
             "messages": [{"role": "system", "content": regra},
                          *[{"role": papel, "content": c} for papel, c in (historico or [])],
                          {"role": "user", "content": pedido}],
             "max_tokens": max_tokens, "temperature": min(temperatura, 1.5)}
    if json_saida:
        corpo["response_format"] = {"type": "json_object"}
    if not config.DEEPSEEK_PENSAR:
        corpo["thinking"] = {"type": "disabled"}          # o raciocínio gasta o limite de tokens e atrasa a resposta
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as cliente:
            for _ in range(2):
                r = cliente.post(DEEPSEEK_URL, headers={"Authorization": "Bearer " + config.DEEPSEEK_API_KEY}, json=corpo)
                if r.status_code == 400 and "thinking" in corpo:       # versão que não aceita o campo: tenta sem ele
                    corpo.pop("thinking")
                    continue
                break
        if r.status_code == 402:
            registrar("o DeepSeek está sem saldo (HTTP 402): recarregue em platform.deepseek.com")
            return None
        if r.status_code >= 400:
            d = _detalhe(r)
            registrar(f"o DeepSeek recusou a chamada (HTTP {r.status_code}){': ' + d if d else ''}")
            return None
        escolha = (r.json().get("choices") or [{}])[0]
        if escolha.get("finish_reason") == "length":
            registrar("a resposta do DeepSeek veio incompleta (limite de tokens)")
            return None
        saida = ((escolha.get("message") or {}).get("content") or "").strip()
        if not saida:
            registrar("o DeepSeek devolveu uma resposta vazia" + (" (filtro de conteúdo)" if escolha.get("finish_reason") == "content_filter" else ""))
        return saida or None
    except Exception as erro:  # noqa: BLE001
        log.warning("DeepSeek indisponível: %s", type(erro).__name__)
        registrar(_nome_erro(erro, "DeepSeek"))
        return None


def gemini(instrucao, texto, json_saida, max_tokens, temperatura, timeout, historico, imagens, registrar):
    k = chave("gemini")
    if not k:
        registrar("a chave GEMINI_API_KEY não está definida no servidor")
        return None
    regra = instrucao + ("\nResponda somente um objeto JSON válido, sem cercas Markdown." if json_saida else "")
    partes = [{"text": texto}] + [{"inlineData": {"mimeType": mime, "data": b64}} for mime, b64 in (imagens or [])]
    contents = [{"role": "model" if papel == "assistant" else "user", "parts": [{"text": c}]} for papel, c in (historico or [])]
    contents.append({"role": "user", "parts": partes})
    geracao = {"maxOutputTokens": max_tokens, "temperature": min(temperatura, 2.0)}
    if json_saida:
        geracao["responseMimeType"] = "application/json"
    geracao["thinkingConfig"] = {"thinkingBudget": 0}
    corpo = {"systemInstruction": {"parts": [{"text": regra}]}, "contents": contents, "generationConfig": geracao,
             "safetySettings": [{"category": c, "threshold": "BLOCK_NONE"} for c in _CATEGORIAS_GEMINI]}
    url = GEMINI_URL.format(modelo=config.GEMINI_TEXT_MODEL)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as cliente:
            for _ in range(2):
                r = cliente.post(url, headers={"x-goog-api-key": k}, json=corpo)
                if r.status_code == 400 and "thinkingConfig" in geracao:     # modelo sem esse ajuste: tenta sem
                    geracao.pop("thinkingConfig")
                    continue
                break
        if r.status_code == 429:
            registrar("o Gemini atingiu o limite gratuito (HTTP 429): espere um pouco ou use outro provedor")
            return None
        if r.status_code >= 400:
            d = _detalhe(r)
            registrar(f"o Gemini recusou a chamada (HTTP {r.status_code}){': ' + d if d else ''}")
            return None
        dados = r.json()
        bloqueio = (dados.get("promptFeedback") or {}).get("blockReason")
        if bloqueio:
            registrar(f"o Gemini bloqueou o pedido por segurança ({bloqueio})")
            return None
        cand = (dados.get("candidates") or [{}])[0]
        saida = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", [])).strip()
        if not saida:
            registrar(f"o Gemini não respondeu ({cand.get('finishReason') or 'vazio'}): provavelmente o filtro de conteúdo dele")
        elif cand.get("finishReason") == "MAX_TOKENS":
            registrar("a resposta do Gemini veio incompleta (limite de tokens)")
            return None
        return saida or None
    except Exception as erro:  # noqa: BLE001
        log.warning("Gemini indisponível: %s", type(erro).__name__)
        registrar(_nome_erro(erro, "Gemini"))
        return None
