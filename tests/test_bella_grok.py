"""Grok opcional: isolamento de provedores, texto, autenticação e voz separada."""
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import config
from nucleo import bella_conversa, grok, programas
from routers import bella

WORD = {"id": "a" * 32, "frase": "Faça {pedido}", "tipo": "word"}


def test_grok_transport(monkeypatch):
    recebidos = []
    class Cliente:
        def __init__(self, **kwargs):
            assert kwargs == {"timeout": 18, "follow_redirects": False}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            recebidos.append((url, kwargs))
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "status": "completed", "output": [
                    {"type": "reasoning", "content": [{"type": "output_text", "text": "privado"}]},
                    {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Um sorriso para você."}]}]})
    monkeypatch.setattr(config, "GROK_API_KEY", "chave-falsa")
    monkeypatch.setattr(grok.httpx, "Client", Cliente)
    assert grok.gerar("regra", "pedido") == "Um sorriso para você."
    url, k = recebidos[0]
    assert url == grok.API and k["headers"] == {"Authorization": "Bearer chave-falsa"}
    assert k["json"]["store"] is False and "tools" not in k["json"]
    assert k["json"]["input"] == [{"role": "system", "content": "regra"}, {"role": "user", "content": "pedido"}]


def test_sem_chave_nao_chama_rede(monkeypatch):
    monkeypatch.setattr(config, "GROK_API_KEY", "")
    monkeypatch.setattr(grok.httpx, "Client", lambda **k: pytest.fail("rede sem chave"))
    assert grok.gerar("regra", "pedido") is None


def test_falha_nao_vaza_chave(monkeypatch, caplog):
    monkeypatch.setattr(config, "GROK_API_KEY", "segredo-falso")
    def falhar(**k): raise RuntimeError("segredo-falso")
    monkeypatch.setattr(grok.httpx, "Client", falhar)
    assert grok.gerar("regra", "pedido") is None
    assert "segredo-falso" not in caplog.text


@pytest.mark.parametrize("modo,provedor", [("normal", "gemini"), ("safada", "grok")])
def test_word_provedor_explicito(monkeypatch, modo, provedor):
    calls = []
    def gerar(prompt, texto, **opcoes):
        calls.append((prompt, json.loads(texto)))
        return json.dumps({"comando_id": WORD["id"], "acao": "escrever", "texto": "Um sorriso só para você.", "confianca": .99})
    escolhido = getattr(programas, provedor)
    outro = programas.grok if provedor == "gemini" else programas.gemini
    monkeypatch.setattr(escolhido, "gerar", gerar)
    monkeypatch.setattr(outro, "gerar", lambda *a, **k: pytest.fail("provedor errado"))
    r = programas.interpretar("Crie uma mensagem", [WORD], modo=modo)
    assert r["acao"] == "escrever" and len(calls) == 1
    if modo == "safada": assert "Sem descrição sexual explícita" in calls[0][0]


def test_sem_fallback_gemini(monkeypatch):
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: None)
    monkeypatch.setattr(programas.gemini, "gerar", lambda *a, **k: pytest.fail("fallback"))
    assert programas.interpretar("Crie uma mensagem", [WORD], modo="safada")["motivo"] == "indisponivel"


@pytest.mark.parametrize("resposta", [None, "", "a" * 2001, "texto\x00inválido"])
def test_conversa_rejeita_saida_invalida(monkeypatch, resposta):
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: resposta)
    assert bella_conversa.responder("Fale comigo") is None


def autenticar(monkeypatch):
    conta = SimpleNamespace(id=123, bella_hash="hash-teste")
    monkeypatch.setattr(bella, "_autenticar", lambda db, chave: conta if chave == "teste" else (_ for _ in ()).throw(HTTPException(401)))
    monkeypatch.setattr(bella, "_JANELAS_CONVERSA", {})
    return conta


def test_rota_separa_texto_e_elevenlabs(monkeypatch):
    conta = autenticar(monkeypatch)
    monkeypatch.setattr(bella_conversa, "responder", lambda texto, *a, **k: "Um sorriso para você.")
    monkeypatch.setattr(bella.roteador, "atender_texto", lambda *a, **k: pytest.fail("conversa chamou sistemas"))
    capturado = []
    monkeypatch.setattr(bella, "_guardar_fala", lambda *a: capturado.append(a) or "id-voz")
    r = bella.conversa(bella.PedidoConversa(texto="Fale uma mensagem", modo="safada"), "teste", None)
    assert r == {"texto": "Um sorriso para você.", "falar": "Um sorriso para você.", "opcoes": [], "voz_id": "id-voz"}
    assert capturado[0][0] is conta and capturado[0][1][0]["falado"] == r["texto"]


def test_rota_exige_chave_e_falha_clara(monkeypatch):
    autenticar(monkeypatch)
    monkeypatch.setattr(bella_conversa, "responder", lambda texto, *a, **k: None)
    pedido = bella.PedidoConversa(texto="Fale comigo", modo="safada")
    with pytest.raises(HTTPException) as erro: bella.conversa(pedido, "errada", None)
    assert erro.value.status_code == 401
    with pytest.raises(HTTPException) as erro: bella.conversa(pedido, "teste", None)
    assert erro.value.status_code == 503


def test_contrato_modo_e_limites():
    assert bella.PedidoPrograma(texto="crie", comandos=[WORD]).modo == "normal"
    for dados in [{"texto": "oi", "modo": "livre"}, {"texto": "a" * 2001, "modo": "safada"}, {"texto": "oi", "modo": "safada", "chave_grok": "proibida"}]:
        with pytest.raises(ValidationError): bella.PedidoConversa(**dados)


@pytest.mark.parametrize("status", ["incomplete", "in_progress", "failed"])
def test_nao_entrega_resposta_incompleta(monkeypatch, status):
    class Cliente:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            return httpx.Response(200, request=httpx.Request("POST", url), json={"status": status, "output": []})
    monkeypatch.setattr(config, "GROK_API_KEY", "falsa")
    monkeypatch.setattr(grok.httpx, "Client", Cliente)
    assert grok.gerar("regra", "pedido") is None


def test_rota_word_transmite_opcao(monkeypatch):
    autenticar(monkeypatch)
    monkeypatch.setattr(bella, "_JANELAS_PROGRAMAS", {})
    calls = []
    monkeypatch.setattr(programas, "interpretar", lambda texto, comandos, modo: calls.append(modo) or {"texto": "teste"})
    for modo in ["normal", "safada"]:
        bella.programa(bella.PedidoPrograma(texto="Crie uma mensagem", comandos=[WORD], modo=modo), "teste", None)
    assert calls == ["normal", "safada"]


def test_conteudo_adulto_desligado_por_padrao(monkeypatch):
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", False)
    assert "Sem descrição sexual explícita" in bella_conversa.prompt()


def test_conteudo_adulto_ligado_mantem_limites_fixos(monkeypatch):
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", True)
    p = bella_conversa.prompt()
    assert "Sem descrição sexual explícita" not in p
    for limite in ("menores de 18 anos", "consentimento", "pessoas reais", "exclusividade", "pare"):
        assert limite in p
    assert programas.estilo() == bella_conversa.estilo()


@pytest.fixture
def memoria(monkeypatch):
    monkeypatch.setattr(bella_conversa, "_MEMORIA", {})
    monkeypatch.setattr(config, "BELLA_MEMORIA_TURNOS", 3)
    monkeypatch.setattr(config, "BELLA_MEMORIA_MINUTOS", 30)
    monkeypatch.setattr(config, "BELLA_CONVERSA_MAX_CHARS", 900)


def _grok_registra(monkeypatch, respostas):
    vistos = []
    fila = iter(respostas)
    def gerar(instrucao, texto, **opcoes):
        vistos.append((instrucao, texto, opcoes.get("historico")))
        return next(fila)
    monkeypatch.setattr(grok, "gerar", gerar)
    return vistos


def test_resposta_ate_900_aceita_e_acima_do_limite_rejeita(memoria, monkeypatch):
    _grok_registra(monkeypatch, ["a" * 900, "a" * 1008, "a" * 1009])
    assert bella_conversa.responder("oi") == "a" * 900
    assert bella_conversa.responder("oi") == "a" * 1008
    assert bella_conversa.responder("oi") is None
    assert "até 900 caracteres" in bella_conversa.prompt()


def test_memoria_envia_trocas_anteriores_na_ordem(memoria, monkeypatch):
    vistos = _grok_registra(monkeypatch, ["r1", "r2", "r3"])
    for fala in ("m1", "m2", "m3"):
        bella_conversa.responder(fala, conta_id=7)
    assert vistos[0][2] == [] and vistos[1][2] == [("user", "m1"), ("assistant", "r1")]
    assert vistos[2][2] == [("user", "m1"), ("assistant", "r1"), ("user", "m2"), ("assistant", "r2")]


def test_memoria_limita_turnos_e_isola_contas(memoria, monkeypatch):
    vistos = _grok_registra(monkeypatch, ["r"] * 6)
    for i in range(4):
        bella_conversa.responder(f"m{i}", conta_id=1)
    assert [h[1] for h in vistos[3][2] if h[0] == "user"] == ["m0", "m1", "m2"]
    bella_conversa.responder("outra", conta_id=2)
    assert vistos[4][2] == []
    bella_conversa.responder("m4", conta_id=1)
    assert [h[1] for h in vistos[5][2] if h[0] == "user"] == ["m1", "m2", "m3"]


def test_memoria_expira_e_pode_ser_apagada(memoria, monkeypatch):
    vistos = _grok_registra(monkeypatch, ["r", "r", "r"])
    agora = [1000.0]
    monkeypatch.setattr(bella_conversa.time, "monotonic", lambda: agora[0])
    bella_conversa.responder("a", conta_id=1)
    agora[0] += 29 * 60
    bella_conversa.responder("b", conta_id=1)
    assert vistos[1][2] == [("user", "a"), ("assistant", "r")]
    agora[0] += 31 * 60
    bella_conversa.responder("c", conta_id=1)
    assert vistos[2][2] == []
    bella_conversa.esquecer(1)
    assert bella_conversa._historico(1) == []


def test_memoria_desligada_ou_sem_conta_nao_guarda(memoria, monkeypatch):
    vistos = _grok_registra(monkeypatch, ["r", "r", "r"])
    bella_conversa.responder("a")
    bella_conversa.responder("b")
    assert vistos[1][2] == [] and bella_conversa._MEMORIA == {}
    monkeypatch.setattr(config, "BELLA_MEMORIA_TURNOS", 0)
    bella_conversa.responder("c", conta_id=1)
    assert bella_conversa._MEMORIA == {}


def test_resposta_invalida_nao_entra_na_memoria(memoria, monkeypatch):
    _grok_registra(monkeypatch, [None, "texto\x00ruim"])
    assert bella_conversa.responder("a", conta_id=1) is None
    assert bella_conversa.responder("b", conta_id=1) is None
    assert bella_conversa._MEMORIA == {}


def test_grok_envia_historico_entre_regra_e_pedido(monkeypatch):
    corpos = []
    class Cliente:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            corpos.append(kwargs["json"])
            return httpx.Response(200, request=httpx.Request("POST", url), json={"status": "completed", "output": [
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}]})
    monkeypatch.setattr(config, "GROK_API_KEY", "falsa")
    monkeypatch.setattr(grok.httpx, "Client", Cliente)
    assert grok.gerar("regra", "agora", historico=[("user", "antes"), ("assistant", "resposta")]) == "ok"
    assert [m["role"] for m in corpos[0]["input"]] == ["system", "user", "assistant", "user"]
    assert corpos[0]["input"][-1]["content"] == "agora"


def test_rota_apaga_memoria_da_conta(memoria, monkeypatch):
    conta = autenticar(monkeypatch)
    bella_conversa._lembrar(conta.id, "a", "b")
    assert bella.esquecer_conversa("teste", None) == {"ok": True}
    assert bella_conversa._historico(conta.id) == []


class _ClienteSaldo:
    resposta = None
    chamadas = []
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, url, **kwargs):
        type(self).chamadas.append((url, kwargs.get("headers")))
        return type(self).resposta


def _saldo_cenario(monkeypatch, resposta):
    _ClienteSaldo.resposta = resposta
    _ClienteSaldo.chamadas = []
    monkeypatch.setattr(config, "XAI_MANAGEMENT_KEY", "chave-gestao-falsa")
    monkeypatch.setattr(config, "XAI_TEAM_ID", "time-1")
    monkeypatch.setattr(grok, "_SALDO", {"quando": 0.0, "valor": None})
    monkeypatch.setattr(grok.httpx, "Client", _ClienteSaldo)


def test_saldo_grok_converte_centavos_e_usa_chave_de_gerenciamento(monkeypatch):
    req = httpx.Request("GET", "https://x")
    _saldo_cenario(monkeypatch, httpx.Response(200, request=req, json={"changes": [], "total": {"val": "-1050"}}))
    assert grok.saldo() == {"saldo_usd": 10.5}
    url, cab = _ClienteSaldo.chamadas[0]
    assert url == "https://management-api.x.ai/v1/billing/teams/time-1/prepaid/balance"
    assert cab == {"Authorization": "Bearer chave-gestao-falsa"}
    grok.saldo()
    assert len(_ClienteSaldo.chamadas) == 1          # cache de 60 s
    grok.saldo(forcar=True)
    assert len(_ClienteSaldo.chamadas) == 2


@pytest.mark.parametrize("status,trecho", [(401, "recusou"), (403, "recusou"), (404, "time"), (500, "Não consegui")])
def test_saldo_grok_erros_claros_sem_vazar_chave(monkeypatch, caplog, status, trecho):
    _saldo_cenario(monkeypatch, httpx.Response(status, request=httpx.Request("GET", "https://x")))
    r = grok.saldo()
    assert trecho in r["erro"] and "chave-gestao-falsa" not in str(r) and "chave-gestao-falsa" not in caplog.text


def test_saldo_grok_desligado_sem_chaves(monkeypatch):
    monkeypatch.setattr(config, "XAI_MANAGEMENT_KEY", "")
    monkeypatch.setattr(grok.httpx, "Client", lambda **k: pytest.fail("rede sem chave"))
    assert grok.saldo_disponivel() is False and "erro" in grok.saldo()


def test_rota_admin_grok(monkeypatch):
    from routers import admin
    monkeypatch.setattr(config, "XAI_MANAGEMENT_KEY", "")
    assert admin.painel_grok(None) == {"disponivel": False}
    monkeypatch.setattr(config, "XAI_MANAGEMENT_KEY", "k")
    monkeypatch.setattr(config, "XAI_TEAM_ID", "t")
    chamadas = []
    monkeypatch.setattr(grok, "saldo", lambda forcar=False: chamadas.append(forcar) or {"saldo_usd": 3.0})
    assert admin.painel_grok(None, atualizar=True) == {"disponivel": True, "saldo_usd": 3.0} and chamadas == [True]


# ── Bella cria prompts (realismo sensual) ─────────────────────────
def _prompt_valido(extra=""):
    from nucleo import prompts_bella
    return prompts_bella.MODELO_REALISMO.replace("[CENÁRIO E GESTO: onde está, o que a mão faz, ombros soltos]", "de pé na cozinha " + extra)


def test_pedido_de_prompt_e_reconhecido():
    from nucleo import prompts_bella as pb
    assert pb.pedido_de("/prompt cozinha, cosplay") == "cozinha, cosplay"
    assert pb.pedido_de("Bella, crie um prompt de odalisca na cobertura") == "de odalisca na cobertura"
    assert pb.pedido_de("gera outro prompt: bar à noite") == "bar à noite"
    assert pb.pedido_de("/prompt") == "" and pb.pedido_de("crie um prompt aleatório") == ""
    assert pb.pedido_de("como está o tempo") is None and pb.pedido_de("o prompt do sistema") is None
    assert pb.pedido_de("próximo aleatório", "x") is None          # sem prompt recente
    pb._lembrar("x")
    assert pb.pedido_de("próximo aleatório", "x") == ""


def test_criar_prompt_usa_grok_e_valida(monkeypatch):
    from nucleo import grok, prompts_bella as pb
    vistos = []
    monkeypatch.setattr(grok, "gerar", lambda instr, texto, **kw: vistos.append((instr, texto, kw)) or _prompt_valido())
    texto = pb.criar("cozinha com cosplay", "c1")
    assert texto and "cozinha" in texto
    assert texto.endswith("não cruzar as pernas.\n" + pb.TAG_FINAL) and texto.count("Spicy mode") == 1
    instr, entrada, kw = vistos[0]
    assert entrada == "Pedido: cozinha com cosplay" and "MODELO:" in instr and "18+" in instr and kw["max_tokens"] >= 2048
    pb.criar("", "c1")
    assert "aleatório" in vistos[1][1]
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: "curto demais")
    assert pb.criar("x") is None
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: None)
    assert pb.criar("x") is None
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: "```text\n" + _prompt_valido() + "\n```")
    assert not pb.criar("x").startswith("```")
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: _prompt_valido() + "\n" + pb.TAG_FINAL)    # o Grok repetiu a tag
    assert pb.criar("x").count("Spicy mode") == 1


def test_rota_conversa_cria_prompt_e_fala_curto(monkeypatch):
    from nucleo import prompts_bella as pb
    monkeypatch.setattr(pb, "criar", lambda pedido, chave=None, categoria="realismo": "PROMPT:" + pedido)
    conta = SimpleNamespace(id=7)
    monkeypatch.setattr(bella, "_autenticar", lambda db, chave: conta)
    monkeypatch.setattr(bella, "_limitar", lambda *a: None)
    guardado = {}
    monkeypatch.setattr(bella, "_guardar_fala", lambda c, mensagens, falar, x: guardado.update(m=mensagens, f=falar) or "vid")
    r = bella.conversa(bella.PedidoConversa(texto="crie um prompt de bar", modo="safada"), "k", None)
    assert r["texto"] == "PROMPT:de bar" and r["falar"] == pb.FALADO and guardado["f"] == pb.FALADO


def test_referencia_vai_ao_grok_so_para_roupa(monkeypatch):
    from nucleo import grok, prompts_bella as pb
    pb._REFERENCIAS.clear()
    assert "JPG" in pb.guardar_referencia("c", "image/gif", b"x")
    assert pb.guardar_referencia("c", "image/jpg", b"\xff\xd8abc") is None
    vistos = []
    monkeypatch.setattr(grok, "gerar", lambda instr, texto, **kw: vistos.append((instr, texto, kw)) or _prompt_valido())
    assert pb.criar("bar à noite", "c")
    instr, entrada, kw = vistos[0]
    assert "SOMENTE a roupa" in instr and kw["imagens"][0][0] == "image/jpeg" and entrada == "Pedido: bar à noite"
    assert pb.criar("", "c") and "roupa da imagem" in vistos[1][1]
    assert pb.criar("sem referência cozinha", "c") and vistos[2][2]["imagens"] is None and "SOMENTE a roupa" not in vistos[2][0]
    assert pb.referencia("c") is None                                 # "sem referência" descartou
    assert pb.criar("outro", "c") and vistos[3][2]["imagens"] is None


def test_referencia_expira_e_recusa(monkeypatch):
    from nucleo import grok, prompts_bella as pb
    pb._REFERENCIAS.clear()
    pb.guardar_referencia("c", "image/png", b"abc")
    monkeypatch.setattr(pb, "_REFERENCIA_MIN", 0)
    assert pb.referencia("c") is None
    monkeypatch.setattr(pb, "_REFERENCIA_MIN", 15)
    pb.guardar_referencia("c", "image/png", b"abc")
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: "RECUSA: a pessoa parece menor de idade")
    with pytest.raises(pb.Recusa):
        pb.criar("x", "c")
    assert pb.pedido_da_legenda("bar à noite") == "bar à noite" and pb.pedido_da_legenda("crie um prompt bar") == "bar"


def test_grok_envia_imagem(monkeypatch):
    enviados = []
    class Cliente:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, **kw):
            enviados.append(kw["json"])
            return httpx.Response(200, request=httpx.Request("POST", url), json={"status": "completed", "output": [
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}]})
    monkeypatch.setattr(config, "GROK_API_KEY", "k")
    monkeypatch.setattr(grok.httpx, "Client", Cliente)
    assert grok.gerar("regra", "veja", imagens=[("image/png", "QUJD")], modelo="grok-visao") == "ok"
    corpo = enviados[0]
    assert corpo["model"] == "grok-visao"
    assert corpo["input"][-1]["content"] == [{"type": "input_text", "text": "veja"},
                                             {"type": "input_image", "image_url": "data:image/png;base64,QUJD"}]


def test_solicitacao_modelo_nova_e_categoria_do_proximo():
    from nucleo import prompts_bella as pb
    assert pb.solicitacao("/promptmodelo cabelo ruivo, pele morena") == ("modelo", "cabelo ruivo, pele morena")
    assert pb.solicitacao("/promptmodelo") == ("modelo", "")
    assert pb.solicitacao("crie um prompt de modelo nova aleatória") == ("modelo", "")
    assert pb.solicitacao("/prompt bar") == ("realismo", "bar")
    pb._lembrar("m1", "modelo")
    assert pb.solicitacao("próximo aleatório", "m1") == ("modelo", "")
    pb._lembrar("m1", "realismo")
    assert pb.solicitacao("próximo aleatório", "m1") == ("realismo", "")


def test_criar_modelo_nova_usa_instrucao_propria(monkeypatch):
    from nucleo import grok, prompts_bella as pb
    pb._REFERENCIAS.clear()
    pb.guardar_referencia("m2", "image/png", b"abc")
    vistos = []
    nova = pb.MODELO_NOVA.replace("[SEXO E IDADE: mulher de 19 anos]", "mulher de 19 anos")
    monkeypatch.setattr(grok, "gerar", lambda instr, texto, **kw: vistos.append((instr, texto, kw)) or nova)
    texto = pb.criar("cabelo ruivo", "m2", "modelo")
    instr, entrada, kw = vistos[0]
    assert "mulher (sexo feminino) de 19 anos" in instr and "SOMENTE a roupa" not in instr
    assert kw["imagens"] is None and entrada == "Pedido: cabelo ruivo"        # modelo nova ignora a referência de roupa
    assert texto.endswith(pb.TAG_FINAL) and pb._recente("m2") == "modelo"
    pb.criar("", "m2", "modelo")
    assert "tudo aleatório" in vistos[1][1]
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: "RECUSA: pedido de menor de idade")
    with pytest.raises(pb.Recusa):
        pb.criar("uma adolescente", "m2", "modelo")
