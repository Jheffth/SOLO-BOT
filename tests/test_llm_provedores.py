"""Escolha do provedor de texto (/ia) e os adaptadores do DeepSeek e do Gemini."""
import config
from nucleo import grok, llm_provedores
from test_fluxos import _ligar_telegram, _tg


class Resp:
    def __init__(self, status=200, dados=None):
        self.status_code, self._d = status, dados or {}

    def json(self):
        return self._d


def _cliente(monkeypatch, resposta, vistos):
    class Cliente:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            vistos.append((url, headers, json))
            return resposta(len(vistos)) if callable(resposta) else resposta
    monkeypatch.setattr(llm_provedores.httpx, "Client", Cliente)


def _limpar(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVEDOR", "grok")
    monkeypatch.setattr(config, "LLM_FALLBACK", [])
    grok._CACHE.update(t=0.0, v="")


def test_deepseek_monta_a_chamada_e_le_a_resposta(monkeypatch):
    _limpar(monkeypatch)
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "ds-falsa")
    monkeypatch.setattr(config, "LLM_PROVEDOR", "deepseek")
    vistos = []
    _cliente(monkeypatch, Resp(200, {"choices": [{"finish_reason": "stop", "message": {"content": " oi, amor "}}]}), vistos)
    saida = grok.gerar("sistema", "olá", historico=[("user", "a"), ("assistant", "b")], imagens=[("image/png", "AAA")], json_saida=True)
    url, headers, corpo = vistos[0]
    assert saida == "oi, amor" and url.startswith("https://api.deepseek.com") and headers["Authorization"] == "Bearer ds-falsa"
    assert corpo["messages"][0]["role"] == "system" and corpo["messages"][1] == {"role": "user", "content": "a"}
    assert corpo["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert corpo["response_format"] == {"type": "json_object"} and corpo["thinking"] == {"type": "disabled"}


def test_deepseek_tenta_sem_thinking_no_400_e_avisa_saldo(monkeypatch):
    _limpar(monkeypatch)
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "ds-falsa")
    monkeypatch.setattr(config, "LLM_PROVEDOR", "deepseek")
    vistos = []
    _cliente(monkeypatch, lambda n: Resp(400) if n == 1 else Resp(200, {"choices": [{"message": {"content": "ok"}}]}), vistos)
    assert grok.gerar("s", "t") == "ok" and "thinking" not in vistos[1][2]
    _cliente(monkeypatch, Resp(402), [])
    assert grok.gerar("s", "t") is None and "sem saldo" in grok.motivo()


def test_gemini_monta_a_chamada_e_explica_bloqueio(monkeypatch):
    _limpar(monkeypatch)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gm-falsa")
    monkeypatch.setattr(config, "LLM_PROVEDOR", "gemini")
    vistos = []
    _cliente(monkeypatch, Resp(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "olá"}]}}]}), vistos)
    assert grok.gerar("sistema", "oi", historico=[("assistant", "x")]) == "olá"
    url, headers, corpo = vistos[0]
    assert "key=" not in url and headers["x-goog-api-key"] == "gm-falsa"
    assert corpo["contents"][0]["role"] == "model" and corpo["systemInstruction"]["parts"][0]["text"] == "sistema"
    assert {s["threshold"] for s in corpo["safetySettings"]} == {"BLOCK_NONE"}
    _cliente(monkeypatch, Resp(200, {"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}}), [])
    assert grok.gerar("s", "t") is None and "bloqueou" in grok.motivo()
    _cliente(monkeypatch, Resp(200, {"candidates": [{"finishReason": "SAFETY"}]}), [])
    assert grok.gerar("s", "t") is None and "filtro de conteúdo" in grok.motivo()


def test_reserva_so_entra_se_configurada_e_com_chave(monkeypatch):
    _limpar(monkeypatch)
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "ds-falsa")
    monkeypatch.setattr(config, "GROK_API_KEY", "")
    monkeypatch.setattr(config, "LLM_PROVEDOR", "grok")
    vistos = []
    _cliente(monkeypatch, Resp(200, {"choices": [{"message": {"content": "do reserva"}}]}), vistos)
    assert grok.gerar("s", "t") is None and not vistos                 # sem reserva configurada
    monkeypatch.setattr(config, "LLM_FALLBACK", ["deepseek", "gemini"])
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY_RESERVA", "")
    assert grok.gerar("s", "t") == "do reserva" and len(vistos) == 1   # o Gemini, sem chave, nunca é chamado


def test_comando_ia_so_para_o_arquiteto_e_troca_o_provedor(cliente, logado, caixa, monkeypatch):
    _limpar(monkeypatch)
    _ligar_telegram(logado)
    _tg(logado, "/ia deepseek")
    assert "Só o Arquiteto" in caixa[-1][2]
    cliente.post("/api/auth/sair")
    r = cliente.post("/api/auth/cadastro", json={"nome": "Arq", "usuario": "arq", "email": "arquiteto@solo.dev", "senha": "12345678"})
    assert r.json()["admin"] is True
    logado = cliente
    _ligar_telegram(logado)
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    _tg(logado, "/ia")
    t = caixa[-1][2]
    assert "Provedor de IA agora: *grok*" in t and "`deepseek` — sem chave" in t
    _tg(logado, "/ia deepseek")
    assert "Falta a chave do deepseek" in caixa[-1][2] and grok.provedor_ativo() == "grok"
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "ds-falsa")
    _tg(logado, "/ia deepseek")
    assert "agora: *deepseek*" in caixa[-1][2] and grok.provedor_ativo() == "deepseek"
    monkeypatch.setattr(config, "GROK_API_KEY", "gk-falsa")
    _tg(logado, "/ia grok")
    assert grok.provedor_ativo() == "grok"


def test_uso_conta_chamadas_tokens_e_custo_por_provedor(cliente, logado, caixa, monkeypatch):
    _limpar(monkeypatch)
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "ds-falsa")
    monkeypatch.setattr(config, "LLM_PROVEDOR", "deepseek")
    vistos = []
    _cliente(monkeypatch, Resp(200, {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 1000000, "completion_tokens": 500000}}), vistos)
    assert grok.gerar("s", "t") == "ok" and grok.gerar("s", "t") == "ok"
    _cliente(monkeypatch, Resp(402), [])
    assert grok.gerar("s", "t") is None
    u = grok.uso(30)
    d = u["hoje"]["deepseek"]
    assert d["req"] == 3 and d["ok"] == 2 and d["in"] == 2000000 and d["out"] == 1000000 and d["usd"] == 0.9     # 2*0.15 + 1*0.60
    cliente.post("/api/auth/sair")
    cliente.post("/api/auth/cadastro", json={"nome": "Arq", "usuario": "arq", "email": "arquiteto@solo.dev", "senha": "12345678"})
    _ligar_telegram(cliente)
    _tg(cliente, "/ia uso")
    t = caixa[-1][2]
    assert "Uso da IA de texto" in t and "deepseek: 3 chamada(s) (1 falha(s))" in t and "~US$ 0.90" in t and "XAI_MANAGEMENT_KEY" in t
