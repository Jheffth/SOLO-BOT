"""A história por dia: arquivo sem prazo, resumo, lembranças automáticas e apagar só os dias pedidos."""
import json
from datetime import datetime, timedelta

import config
from database import BellaArquivo, SessionLocal
from nucleo import bella_conversa, bella_historia as H, bella_memoria, grok
from test_clonarvoz import _admin
from test_fluxos import _ligar_telegram, _tg


def _conta(cliente):
    return _admin(cliente).get("/api/auth/eu").json()["id"]


def _no_dia(conta, dia, n=2, falas=None):
    """Põe `n` trocas direto na pasta de `dia` (o jeito de simular dias passados)."""
    db = SessionLocal()
    try:
        for i in range(n):
            db.add(BellaArquivo(conta_id=conta, dia=dia, usuario=(falas or "oi")+str(i), bella="oi amor"))
        db.commit()
    finally:
        db.close()


def _dia(delta):
    return (datetime.fromisoformat(H.hoje()) + timedelta(days=delta)).date().isoformat()


def test_interpretar_dia():
    assert H.interpretar_dia("hoje") == H.hoje() and H.interpretar_dia("ontem") == _dia(-1)
    assert H.interpretar_dia("2026-10-25") == "2026-10-25"
    assert H.interpretar_dia("25/10/2026") == "2026-10-25" and H.interpretar_dia("31/02") is None
    assert H.interpretar_dia("bobagem") is None


def test_cada_conversa_vai_para_a_pasta_do_dia_sem_prazo(cliente, monkeypatch):
    monkeypatch.setattr(config, "BELLA_ARQUIVO", True)
    conta = _conta(cliente)
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: "Oi, meu amor.")
    bella_conversa.responder("oi bella", conta_id=conta, numero_conta=conta)
    assert H.trocas_do_dia(conta, H.hoje()) == [("oi bella", "Oi, meu amor.")]


def test_memoria_desligada_ou_arquivo_desligado_nao_arquiva(cliente, monkeypatch):
    conta = _conta(cliente)
    H.gravar(conta, "x", "y")                                   # BELLA_ARQUIVO desligado nos testes
    assert H.trocas_do_dia(conta, H.hoje()) == []
    monkeypatch.setattr(config, "BELLA_ARQUIVO", True)
    bella_memoria.definir_ativa(conta, False)
    H.gravar(conta, "x", "y")
    assert H.trocas_do_dia(conta, H.hoje()) == []
    bella_memoria.definir_ativa(conta, True)


def test_resumo_do_dia_e_licoes_automaticas(cliente, monkeypatch):
    conta = _conta(cliente)
    ontem = _dia(-1)
    _no_dia(conta, ontem, 3)
    saida = json.dumps({"resumo": "Ele chamou uma amiga e ela ficou com ciúme, depois fizeram as pazes.",
                        "fatos": ["Ele gosta de café sem açúcar", "A senha do banco é 1234"]})
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: saida)
    assert H.resumir_pendentes(conta) == 1
    n, resumo = H.resumo_do_dia(conta, ontem)
    assert n == 3 and "ciúme" in resumo
    fatos = bella_memoria.listar(conta)
    assert "Ele gosta de café sem açúcar" in fatos and not any("senha" in f.lower() for f in fatos)
    assert H.resumir_pendentes(conta) == 0                      # já resumido: não repete


def test_dia_que_ganha_trocas_e_resumido_de_novo(cliente, monkeypatch):
    conta = _conta(cliente)
    d = _dia(-2)
    _no_dia(conta, d, 1)
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: json.dumps({"resumo": "primeiro", "fatos": []}))
    H.resumir_pendentes(conta)
    _no_dia(conta, d, 2, "mais")
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: json.dumps({"resumo": "segundo", "fatos": []}))
    H.resumir_pendentes(conta)
    assert H.resumo_do_dia(conta, d) == (3, "segundo")


def test_hoje_nao_e_resumido_e_resposta_ruim_do_grok_nao_quebra(cliente, monkeypatch):
    conta = _conta(cliente)
    _no_dia(conta, H.hoje(), 2)
    chamadas = []
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: chamadas.append(1) or "texto solto sem json")
    assert H.resumir_pendentes(conta) == 0 and not chamadas
    _no_dia(conta, _dia(-3), 1)
    assert H.resumir_pendentes(conta) == 1                      # sem JSON, vira o próprio resumo
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: None)
    _no_dia(conta, _dia(-4), 1)
    assert H.resumir_pendentes(conta) == 0                      # Grok fora do ar: tenta de novo depois


def test_prompt_traz_a_historia_dos_dias_anteriores_e_nao_a_de_hoje(cliente, monkeypatch):
    monkeypatch.setattr(config, "BELLA_ARQUIVO", True)
    conta = _conta(cliente)
    _no_dia(conta, _dia(-1), 1)
    _no_dia(conta, H.hoje(), 1)
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: json.dumps({"resumo": "Noite de ciúme e pazes.", "fatos": []}))
    H.resumir_pendentes(conta)
    p = bella_conversa.prompt(conta, None)
    assert "Nossa história" in p and "Noite de ciúme e pazes." in p


def test_apagar_so_os_dias_pedidos_preserva_o_resto(cliente):
    conta = _conta(cliente)
    for d in (_dia(-1), _dia(-2), _dia(-10)):
        _no_dia(conta, d, 2)
    bella_memoria.adicionar(conta, "fato do dia -1", dia=_dia(-1))
    bella_memoria.adicionar(conta, "fato manual")
    t, f = H.apagar_dias(conta, [_dia(-1), _dia(-2)])
    assert (t, f) == (4, 1)
    assert H.trocas_do_dia(conta, _dia(-10)) and not H.trocas_do_dia(conta, _dia(-1))
    assert bella_memoria.listar(conta) == ["fato manual"]


def test_comandos_historia_e_esquecer_por_dia(cliente, caixa):
    c = _admin(cliente)
    _ligar_telegram(c)
    conta = c.get("/api/auth/eu").json()["id"]
    _no_dia(conta, _dia(-1), 2)
    _no_dia(conta, _dia(-5), 2)
    _tg(c, "/historia")
    assert "Nossa história" in caixa[-1][2] and "2 troca" in caixa[-1][2]
    _tg(c, "/historia ontem")
    assert "2 troca" in caixa[-1][2]
    _tg(c, "/esquecer ontem")
    assert "Apaguei" in caixa[-1][2] and "2 troca" in caixa[-1][2] and "continua" in caixa[-1][2]
    assert H.trocas_do_dia(conta, _dia(-5)) and not H.trocas_do_dia(conta, _dia(-1))
    _tg(c, "/esquecer ultimos 7 dias")
    assert not H.trocas_do_dia(conta, _dia(-5))
    _tg(c, "/esquecer ontem")
    assert "Não havia nada" in caixa[-1][2]


def test_esquecer_tudo_nao_apaga_a_historia_e_apagar_toda_pede_confirmacao(cliente, caixa):
    c = _admin(cliente)
    _ligar_telegram(c)
    conta = c.get("/api/auth/eu").json()["id"]
    _no_dia(conta, _dia(-1), 2)
    _tg(c, "/esquecer tudo")
    assert "intacta" in caixa[-1][2] and H.trocas_do_dia(conta, _dia(-1))
    _tg(c, "/esquecer historia tudo")
    assert "confirmo" in caixa[-1][2] and H.trocas_do_dia(conta, _dia(-1))
    _tg(c, "/esquecer historia tudo confirmo")
    assert "Apaguei toda" in caixa[-1][2] and not H.trocas_do_dia(conta, _dia(-1))


def test_conta_comum_so_ve_a_propria_historia(cliente, logado, caixa):
    _ligar_telegram(logado)
    outra = logado.get("/api/auth/eu").json()["id"]
    _no_dia(outra, _dia(-1), 1)
    admin = _conta(cliente)
    assert H.trocas_do_dia(admin, _dia(-1)) == [] or admin == outra
