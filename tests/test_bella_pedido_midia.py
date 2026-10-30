"""Quando o Arquiteto pede foto ou vídeo: o agrado, o humor e o termômetro decidem (o código, nunca o modelo)."""
import random

import config
from database import BellaEstado, SessionLocal
from nucleo import bella_conversa, bella_estado, bella_galeria as G, grok
from test_clonarvoz import _admin

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64


def _montar(tmp_path, monkeypatch, niveis=("normal", "sensual", "nu"), niveis_ativos=None):
    monkeypatch.setattr(config, "BELLA_GALERIA_DIR", str(tmp_path))
    if niveis_ativos:
        monkeypatch.setattr(config, "BELLA_GALERIA_NIVEIS", niveis_ativos)
    for n in niveis:
        pasta = tmp_path / "bella" / n
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "a.jpg").write_bytes(JPEG)
        (pasta / "b.mp4").write_bytes(MP4)


def _estado(**kw):
    base = {"emocao": "alegre", "agrado": 20, "nivel": 0}
    base.update(kw)
    return base


def test_detectar_pedido():
    for frase, esperado in (("me manda um vídeo", "video"), ("Manda uma fotinha pra mim", "foto"), ("quero ver um videozinho", "video"),
                            ("mostra uma selfie", "foto"), ("assisti um vídeo hoje", None), ("a foto ficou linda", None), ("oi", None)):
        assert G.detectar_pedido(frase) == esperado, frase


def test_agrado_baixo_nega_e_agrado_alto_libera_por_nivel(tmp_path, monkeypatch, cliente):
    _montar(tmp_path, monkeypatch, niveis_ativos="bom_dia,normal,sensual,nu")
    rng = random.Random(3)
    acao, motivo, _ = G.decidir(_estado(agrado=0), "video", False, rng)
    assert (acao, motivo) == ("negar", "agrado")
    acao, m, nivel = G.decidir(_estado(agrado=10), "video", False, rng)
    assert acao == "enviar" and nivel == "normal" and m["tipo"] == "video"          # só o normal exige pouco
    niveis = {G.decidir(_estado(agrado=40), "foto", False, random.Random(s))[2] for s in range(40)}
    assert niveis == {"normal", "sensual"}                                         # nu exige agrado 85 e grau 3
    niveis = {G.decidir(_estado(agrado=90, nivel=3), "foto", False, random.Random(s))[2] for s in range(60)}
    assert "nu" in niveis


def test_nu_desligado_por_padrao_mesmo_com_pasta_e_agrado(tmp_path, monkeypatch, cliente):
    _montar(tmp_path, monkeypatch)
    niveis = {G.decidir(_estado(agrado=100, nivel=5), "foto", False, random.Random(s))[2] for s in range(60)}
    assert "nu" not in niveis and niveis <= {"normal", "sensual"}


def test_chateada_nega_a_menos_que_ele_mande_firme(tmp_path, monkeypatch, cliente):
    _montar(tmp_path, monkeypatch)
    for emocao in ("ciume", "raiva", "carencia", "triste"):
        assert G.decidir(_estado(emocao=emocao, agrado=100), "video", False)[:2] == ("negar", "chateada")
    acao, _, nivel = G.decidir(_estado(emocao="raiva", agrado=0), "video", True)
    assert acao == "enviar"                                                         # ordem firme dispensa o agrado e o humor


def test_galeria_vazia_nao_envia(tmp_path, monkeypatch, cliente):
    monkeypatch.setattr(config, "BELLA_GALERIA_DIR", str(tmp_path))
    assert G.decidir(_estado(agrado=100), "video", False)[0] == "vazio"


def test_so_video_ou_so_foto_conforme_o_pedido(tmp_path, monkeypatch, cliente):
    _montar(tmp_path, monkeypatch, ("normal",))
    for s in range(10):
        assert G.decidir(_estado(), "video", False, random.Random(s))[1]["tipo"] == "video"
        assert G.decidir(_estado(), "foto", False, random.Random(s))[1]["tipo"] == "imagem"


def test_conversa_envia_a_midia_e_gasta_agrado_so_para_o_arquiteto(cliente, tmp_path, monkeypatch):
    _montar(tmp_path, monkeypatch, ("normal",))
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    notas = []
    monkeypatch.setattr(grok, "gerar", lambda sis, t, **k: notas.append(sis) or "Toma, amor.")
    saida = []
    bella_conversa.responder("me manda um vídeo, minha linda", conta_id=conta, numero_conta=conta, saida_midia=saida)
    assert saida and saida[0]["tipo"] == "video" and "VAI mandar" in notas[-1]
    apos = bella_estado.situacao(conta)["agrado"]
    assert apos <= 100 - G.CUSTO["video"] + 12                                      # mandar gastou agrado (e o elogio pôs 12)
    # sem saida_midia (Bella.exe, atalho): nunca anexa nada e não gasta
    notas.clear()
    bella_conversa.responder("me manda um vídeo", conta_id=conta, numero_conta=conta)
    assert "VAI mandar" not in notas[-1]


def test_pedido_negado_vira_provocacao_sem_midia(cliente, tmp_path, monkeypatch):
    _montar(tmp_path, monkeypatch, ("normal",))
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    db = SessionLocal()
    e = db.get(BellaEstado, conta) or BellaEstado(conta_id=conta)
    e.agrado, e.emocao = 20, "raiva"
    db.merge(e)
    db.commit()
    db.close()
    notas = []
    monkeypatch.setattr(grok, "gerar", lambda sis, t, **k: notas.append(sis) or "Hoje não, Jefferson.")
    saida = []
    bella_conversa.responder("manda um vídeo", conta_id=conta, numero_conta=conta, saida_midia=saida)
    assert saida == [] and "não está no clima" in notas[-1]


def test_elogio_sobe_o_agrado(cliente):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    bella_estado.definir_emocao(conta, "alegre")
    antes = bella_estado.avancar(conta, "oi")["agrado"]
    depois = bella_estado.avancar(conta, "você é linda e maravilhosa, meu amor")["agrado"]
    assert depois - antes >= 10
