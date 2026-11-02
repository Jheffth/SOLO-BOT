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


# Uso por provedor, guardado por dia na tabela de configurações ("llm_uso:AAAA-MM-DD:provedor" = JSON). Preços em US$ por milhão
# de tokens (entrada, saída); o do DeepSeek é o de fora do pico, então o custo mostrado é uma estimativa.
PRECOS = {"grok": (2.0, 6.0), "deepseek": (0.15, 0.60), "gemini": (0.0, 0.0)}
_TRAVA_USO = threading.Lock()


def _registrar_uso(entrada, saida):
    _ULTIMO.uso = (int(entrada or 0), int(saida or 0))


def _contar(provedor, ok):
    entrada, saida = getattr(_ULTIMO, "uso", (0, 0))
    try:
        import json as _json
        from datetime import datetime
        from database import SessionLocal, gravar_config, ler_config
        chave = f"llm_uso:{datetime.utcnow():%Y-%m-%d}:{provedor}"
        with _TRAVA_USO:
            try:
                atual = _json.loads(ler_config(chave) or "{}")
            except ValueError:
                atual = {}
            atual = {"req": atual.get("req", 0) + 1, "ok": atual.get("ok", 0) + (1 if ok else 0),
                     "in": atual.get("in", 0) + entrada, "out": atual.get("out", 0) + saida}
            db = SessionLocal()
            try:
                gravar_config(db, chave, _json.dumps(atual))
            finally:
                db.close()
    except Exception:  # noqa: BLE001
        log.debug("Não registrei o uso do provedor", exc_info=True)


def uso(dias=30):
    """{"hoje": {provedor: {...}}, "periodo": {provedor: {...}}} com req, ok, in, out e custo estimado em US$."""
    import json as _json
    from datetime import datetime, timedelta
    from database import Configuracao, SessionLocal
    hoje = f"{datetime.utcnow():%Y-%m-%d}"
    desde = f"{datetime.utcnow() - timedelta(days=dias - 1):%Y-%m-%d}"
    saida = {"hoje": {}, "periodo": {}}
    db = SessionLocal()
    try:
        for c in db.query(Configuracao).filter(Configuracao.chave.like("llm_uso:%")).all():
            _, dia, prov = (c.chave.split(":") + ["", ""])[:3]
            if dia < desde or prov not in PROVEDORES:
                continue
            try:
                d = _json.loads(c.valor or "{}")
            except ValueError:
                continue
            for escopo in (("periodo",) + (("hoje",) if dia == hoje else ())):
                t = saida[escopo].setdefault(prov, {"req": 0, "ok": 0, "in": 0, "out": 0})
                for k in t:
                    t[k] += int(d.get(k, 0))
    finally:
        db.close()
    for escopo in saida.values():
        for prov, t in escopo.items():
            p_in, p_out = PRECOS[prov]
            t["usd"] = round(t["in"] / 1e6 * p_in + t["out"] / 1e6 * p_out, 4)
    return saida


PROVEDORES = ("grok", "deepseek", "gemini")
_CACHE = {"t": 0.0, "v": ""}


def provedor_ativo():
    """O provedor de texto em uso: o que o Arquiteto escolheu com /ia, senão o LLM_PROVEDOR do .env, senão o Grok."""
    if time.monotonic() - _CACHE["t"] > 15:
        valor = ""
        try:
            from database import ler_config
            valor = (ler_config("llm_provedor") or "").strip().lower()
        except Exception:  # noqa: BLE001
            valor = ""
        _CACHE.update(t=time.monotonic(), v=valor)
    for v in (_CACHE["v"], config.LLM_PROVEDOR):
        if v in PROVEDORES:
            return v
    return "grok"


def definir_provedor(valor):
    from database import SessionLocal, gravar_config
    db = SessionLocal()
    try:
        gravar_config(db, "llm_provedor", valor)
    finally:
        db.close()
    _CACHE.update(t=0.0, v=valor)


def tem_chave(provedor):
    from nucleo import llm_provedores
    return bool(config.GROK_API_KEY) if provedor == "grok" else bool(llm_provedores.chave(provedor))


def gerar(instrucao, texto, json_saida=False, max_tokens=1536, temperatura=.7, timeout=18, historico=None,
          imagens=None, modelo=None):
    """Escolhe o provedor (ver provedor_ativo) e, se ele falhar, tenta os de LLM_FALLBACK que tiverem chave."""
    ativo = provedor_ativo()
    ordem = [ativo] + [p for p in config.LLM_FALLBACK if p in PROVEDORES and p != ativo and tem_chave(p)]
    for p in ordem:
        _ULTIMO.uso = (0, 0)
        if p == "grok":
            saida = _gerar_grok(instrucao, texto, json_saida, max_tokens, temperatura, timeout, historico, imagens, modelo)
        else:
            from nucleo import llm_provedores
            _ULTIMO.motivo = ""
            saida = getattr(llm_provedores, p)(instrucao, texto, json_saida, max_tokens, temperatura, timeout, historico, imagens,
                                               registrar_motivo, _registrar_uso)
        _contar(p, bool(saida))
        if saida:
            if p != ativo:
                log.info("Provedor %s falhou; respondeu o reserva %s", ativo, p)
            return saida
    return None


def _gerar_grok(instrucao, texto, json_saida=False, max_tokens=1536, temperatura=.7, timeout=18, historico=None,
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
        _u = dados.get("usage") or {}
        _registrar_uso(_u.get("input_tokens"), _u.get("output_tokens"))
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
