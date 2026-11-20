"""Avisos e respostas dos sistemas na voz da modelo selecionada (nucleo/models_persona.py)."""
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import config
from nucleo import avisos, grok, intencao, models, models_persona, roteador
from test_avisos import ROT, _hora, pronto  # noqa: F401  (fixture)
from test_fluxos import _tg

VOZ = {"principal": True, "ativa": True, "provedor": "voicestudio", "voice_id": "v1"}


@pytest.fixture()
def models_falso(monkeypatch):
    chamadas = {"gravados": [], "instrucoes": [], "pacotes": []}
    monkeypatch.setattr(models, "selecionado", lambda conta_id: "isa")
    monkeypatch.setattr(models, "pacote", lambda conta, ident: chamadas["pacotes"].append(ident) or
                        {"nome": {"isa": "Isabella", "kel": "Kellen"}.get(ident, ident), "vozes_por_conta": [VOZ]})
    monkeypatch.setattr(models, "_montar_contexto", lambda *a, **k: {"memorias_usadas": [], "contexto_id": "c1"})
    monkeypatch.setattr(models, "montar_prompt", lambda conta, p, ctx: (f"Você é {p['nome']}.", "", []))
    monkeypatch.setattr(models, "_gravar", lambda conta, ident, tipo, texto, **k: chamadas["gravados"].append((ident, texto, k)))
    return chamadas


def _grok(monkeypatch, chamadas, saida):
    monkeypatch.setattr(grok, "gerar", lambda instr, texto, **k: chamadas["instrucoes"].append((instr, texto)) or saida)


def test_conferencia_dos_numeros_e_comandos():
    original = "⏳ Oração matinal — 14 min para o prazo\n💰 Total: R$ 35,83\nUse /hoje para ver os detalhes."
    assert models_persona.conferir(original, "Amor 🌸\n• Oração matinal: 14 min\n• Total: R$ 35,83\nUse /hoje") == ""
    assert "14" in models_persona.conferir(original, "Amor\n• Total: R$ 35,83\n/hoje")
    assert "novos" in models_persona.conferir(original, "Amor, 14 min, R$ 35,83 e 15 beijos /hoje")
    assert "comandos" in models_persona.conferir(original, "Amor, 14 min e R$ 35,83")
    assert models_persona.conferir("Continue. O Sistema tem mais tempo que você.", "Levanta, amor, eu tô te esperando.") == ""


def test_reescreve_na_persona_e_grava_no_historico(models_falso, monkeypatch):
    _grok(monkeypatch, models_falso, "Bom dia, meu Arquiteto 🌸\n• DAS Mei: R$ 82,05, vence hoje\nFALA: Bom dia, amor, hoje vence o DAS.")
    conta = SimpleNamespace(id=1, admin=False)
    r = models_persona.reescrever(conta, "Finances", "📋 Pagamentos\n* DAS Mei — R$ 82,05 · vence hoje")
    assert r["texto"].startswith("Bom dia, meu Arquiteto") and "FALA" not in r["texto"]
    assert r["falado"] == "Bom dia, amor, hoje vence o DAS." and r["voz"] == VOZ
    instr, pedido = models_falso["instrucoes"][0]
    assert "Você é Isabella" in instr and "TAREFA AGORA" in instr and "Finances" in instr and "R$ 82,05" in pedido
    ident, texto, extra = models_falso["gravados"][0]
    assert ident == "isa" and texto == r["texto"] and extra["usuario"] == "[Aviso do Finances]" and extra["origem"] == "iniciativa"


def test_numero_trocado_volta_ao_texto_do_sistema(models_falso, monkeypatch):
    _grok(monkeypatch, models_falso, "Amor, o DAS de R$ 82,00 vence hoje.")
    assert models_persona.reescrever(SimpleNamespace(id=1, admin=False), "Finances", "DAS Mei — R$ 82,05 · vence hoje") is None
    assert models_falso["gravados"] == []


def test_em_cena_a_anfitria_da_o_aviso_citando_as_outras(models_falso, monkeypatch):
    from nucleo import models_cena
    monkeypatch.setattr(models_cena, "cena_ativa", lambda conta, ident: {"ativa": True, "presentes": [
        {"modelo_id": "isa", "nome": "Isabella"}, {"modelo_id": "kel", "nome": "Kellen", "anfitria": True}]})
    _grok(monkeypatch, models_falso, "Isabella, olha só: ele tem 14 min para orar.")
    r = models_persona.reescrever(SimpleNamespace(id=1, admin=True), "Rotinas", "⏳ Oração matinal — 14 min para o prazo")
    assert r and models_falso["pacotes"] == ["kel"]
    instr, _ = models_falso["instrucoes"][0]
    assert "Você é Kellen" in instr and "anfitriã" in instr and "Isabella" in instr
    assert models_falso["gravados"][0][0] == "kel"


def test_aplicar_mantem_opcoes_e_poe_a_voz_dela(monkeypatch):
    monkeypatch.setattr(models_persona, "reescrever", lambda conta, sistema, texto, usuario=None:
                        {"texto": "Amor 💕\n" + texto, "falado": "Amor, olha isso.", "voz": VOZ, "nome": "Isabella"})
    opcoes = [{"titulo": "", "acoes": [{"rotulo": "Pago", "dados": "fin:pago|1"}]}]
    saida = models_persona.aplicar(SimpleNamespace(id=1), "Finances", "💰 Finances",
                                   [{"texto": "💰 Finances\nDAS — R$ 82,05", "opcoes": opcoes, "falado": "roteiro antigo", "tom": "sussurro"}])
    assert len(saida) == 1
    m = saida[0]
    assert m["texto"].startswith("Amor 💕\nDAS — R$ 82,05") and m["texto"].endswith("_💰 Finances_")
    assert m["opcoes"] == opcoes and m["modelo_voz"] == VOZ and m["falado"] == "Amor, olha isso."
    assert m["persona"] and m["literal"] and "tom" not in m


def _fila_imediata(monkeypatch):
    from database import SessionLocal

    def rodar(tarefa):
        db = SessionLocal()
        try:
            tarefa(db)
        finally:
            db.close()
    monkeypatch.setattr(models_persona, "enfileirar", rodar)


def _modo_telegram():
    from database import Sessao, SessionLocal
    db = SessionLocal()
    try:
        s = db.query(Sessao).filter(Sessao.canal == "telegram").first()
        return s.modo if s else None
    finally:
        db.close()


def test_aviso_ao_vivo_vem_na_voz_dela_e_nao_troca_o_modo(pronto, caixa, monkeypatch):
    _hora(monkeypatch, 14)
    _fila_imediata(monkeypatch)
    monkeypatch.setattr(models_persona, "ativa", lambda db, conta: True)
    ditos = []
    monkeypatch.setattr(models_persona, "reescrever", lambda conta, sistema, texto, usuario=None: ditos.append((sistema, texto, usuario)) or
                        {"texto": "Amor, acorda 🌸\n• Oração matinal: 14 min", "falado": None, "voz": None, "nome": "Isabella"})
    r = pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "⏳ Oração matinal — 14 min para o prazo"}).json()
    assert r["entregues"] == 1
    assert "Amor, acorda" in caixa[-1][2] and "Rotinas" in caixa[-1][2]
    assert ditos and ditos[0][0] == "Rotinas" and "⚔️" not in ditos[0][1].split("\n")[0][:2]
    assert _modo_telegram() != "rot"


def test_sem_persona_o_aviso_segue_como_antes(pronto, caixa, monkeypatch):
    _hora(monkeypatch, 14)
    monkeypatch.setattr(models_persona, "ativa", lambda db, conta: False)
    pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "Faltam 15 min"})
    assert "Faltam 15 min" in caixa[-1][2] and _modo_telegram() == "rot"


def test_aviso_guardado_no_silencio_sai_na_voz_dela(pronto, caixa, monkeypatch):
    pronto.patch("/api/conta/avisos", json={"silencio": True, "de": "22:00", "ate": "07:00"})
    _hora(monkeypatch, 23, 30)
    monkeypatch.setattr(models_persona, "ativa", lambda db, conta: True)
    monkeypatch.setattr(models_persona, "reescrever", lambda conta, sistema, texto, usuario=None:
                        {"texto": "Bom dia, amor ☀️\n" + texto, "falado": None, "voz": None, "nome": "Isabella"})
    assert pronto.post("/interno/enviar", headers=ROT, json={"usuario_id": "1", "texto": "Missão das 23h vencida"}).json()["adiados"] == 1
    from database import SessionLocal
    db = SessionLocal()
    assert avisos.despachar_pendentes(db, datetime(2026, 10, 2, 7, 0, tzinfo=ZoneInfo(config.FUSO))) == 1
    db.close()
    assert caixa[-1][2].startswith("Bom dia, amor") and "Missão das 23h vencida" in caixa[-1][2]


def test_resposta_do_sistema_vem_na_voz_dela(pronto, caixa, monkeypatch):
    monkeypatch.setattr(models_persona, "ativa", lambda db, conta: True)
    vistos = []
    monkeypatch.setattr(models_persona, "reescrever", lambda conta, sistema, texto, usuario=None: vistos.append((sistema, usuario)) or
                        {"texto": "Olha o seu dia, amor 💕\n" + texto, "falado": None, "voz": None, "nome": "Isabella"})
    _tg(pronto, "/rot hoje")
    assert "Olha o seu dia, amor" in caixa[-1][2]
    assert vistos[-1][0] == "Rotinas"


def test_conversa_num_modo_de_sistema_volta_para_a_modelo(monkeypatch):
    monkeypatch.setattr(models_persona, "ativa", lambda db, conta: True)
    monkeypatch.setattr(intencao, "comando_literal", lambda *a, **k: intencao.Intencao())
    monkeypatch.setattr(intencao, "eh_consulta", lambda t: False)
    pontos = {}
    monkeypatch.setattr(intencao, "por_palavras", lambda db, t, c: pontos)
    conta = SimpleNamespace(id=1)
    assert roteador._papo_com_a_modelo(None, conta, "estou com saudade de você hoje", [])
    assert not roteador._papo_com_a_modelo(None, conta, "mercado", [])                     # resposta curta: sistema
    assert not roteador._papo_com_a_modelo(None, conta, "gastei 30 reais no almoço", [])   # número: sistema
    assert not roteador._papo_com_a_modelo(None, conta, "/hoje", [])
    pontos["fin"] = 1
    assert not roteador._papo_com_a_modelo(None, conta, "paguei a conta de luz hoje cedo", [])


def test_comando_persona_liga_e_desliga(pronto, caixa):
    _tg(pronto, "/persona desligar")
    assert "formato padrão" in caixa[-1][2]
    from database import Conta, SessionLocal
    db = SessionLocal()
    conta = db.query(Conta).first()
    assert models_persona.ligada(db, conta.id) is False
    db.close()
    _tg(pronto, "/persona ligar")
    assert "persona" in caixa[-1][2].lower() or "modelo" in caixa[-1][2].lower()
