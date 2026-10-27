"""Regressões de latência: texto não espera voz nem repete interpretação."""
from types import SimpleNamespace
import pytest
from canais import entrega, evolution
from nucleo import fala, roteador, intencao
from test_fluxos import _wa


def preparar(monkeypatch):
    eventos = []
    monkeypatch.setattr(roteador, "conta_de", lambda *a: SimpleNamespace(voz="sempre"))
    monkeypatch.setattr(evolution, "enviar", lambda origem, texto: eventos.append(("texto", texto)))
    monkeypatch.setattr(evolution, "enviar_audio", lambda *a: eventos.append(("audio", "")) or {"key": {"id": "ok"}})
    monkeypatch.setattr(roteador, "guardar_escolhas", lambda *a: eventos.append(("escolhas", "")))
    return eventos


def test_texto_e_escolhas_saem_antes_de_gerar_voz(monkeypatch):
    eventos = preparar(monkeypatch)
    resposta = roteador.Resposta().diz("Resultado pronto", [{"titulo": "", "acoes": [{"rotulo": "Abrir", "dados": "a"}]}])
    def sintetizar(*args, **kw):
        assert [e[0] for e in eventos] == ["texto", "escolhas"]
        eventos.append(("sintese", ""))
        resposta.mensagens[-1]["audio"] = {"base64": "QUJD"}
    monkeypatch.setattr(fala, "falar_resposta", sintetizar)
    entrega.entregar(object(), "whatsapp", "destino", resposta)
    assert [e[0] for e in eventos] == ["texto", "escolhas", "sintese", "audio"]


def test_falha_de_voz_nao_atrasa_nem_duplica_texto(monkeypatch):
    eventos = preparar(monkeypatch)
    def falhar(*a, **k):
        assert eventos == [("texto", "Pronto")]
        raise RuntimeError("motor indisponível")
    monkeypatch.setattr(fala, "falar_resposta", falhar)
    entrega.entregar(object(), "whatsapp", "destino", roteador.Resposta().diz("Pronto"))
    assert eventos == [("texto", "Pronto")]


@pytest.mark.parametrize("audio_ok", [True, False])
def test_audio_exclusivo_preserva_preferencia_e_fallback(monkeypatch, audio_ok):
    eventos = preparar(monkeypatch)
    monkeypatch.setattr(fala, "falar_resposta", lambda *a, **k: None)
    monkeypatch.setattr(entrega, "_voz", lambda *a: eventos.append(("audio", "")) or audio_ok)
    resposta = roteador.Resposta().diz("Texto de reserva", audio={"base64": "QUJD"})
    resposta.mensagens[0]["formato"] = "audio"
    entrega.entregar(object(), "whatsapp", "destino", resposta)
    assert [e[0] for e in eventos] == (["audio"] if audio_ok else ["audio", "texto"])


@pytest.mark.parametrize("sucesso", [True, False])
def test_um_sistema_consulta_ia_so_uma_vez(logado, sistemas, caixa, monkeypatch, sucesso):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    codigo = logado.post("/api/conta/canais/whatsapp/codigo").json()["codigo"]
    _wa(logado, "SOLO " + codigo)
    chamadas = []
    def interpretar(*a, **kw):
        chamadas.append(1)
        return intencao.Intencao(app="rot", mensagem="/hoje", confianca=.95) if sucesso else intencao.Intencao()
    monkeypatch.setattr(intencao, "interpretar", interpretar)
    _wa(logado, "qual o planejamento de hoje?")
    assert len(chamadas) == 1
    if sucesso:
        assert sistemas.recebidos[-1][2]["texto"] == "/hoje"


@pytest.mark.parametrize("preferencia", ["nunca", "audio"])
def test_texto_sem_voz_nao_consulta_motor(monkeypatch, preferencia):
    monkeypatch.setattr(fala, "disponivel", lambda: pytest.fail("consultou motor sem precisar de voz"))
    resposta = roteador.Resposta().diz("Pronto")
    fala.falar_resposta(SimpleNamespace(voz=preferencia), "whatsapp", resposta, entrada_audio=False)
