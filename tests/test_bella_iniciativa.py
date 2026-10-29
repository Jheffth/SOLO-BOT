"""A Bella puxa assunto sozinha: poucos horários sorteados, tipos variados, sem insistir."""
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config
from database import BellaEstado, SessionLocal
from nucleo import bella_iniciativa as I, grok
from test_clonarvoz import _admin
from test_fluxos import _ligar_telegram, _tg


def _utc(h, m=0, dia=(2026, 10, 29)):
    """Um instante UTC que corresponde a h:m no horário de Brasília."""
    local = datetime(*dia, h, m, tzinfo=ZoneInfo(config.FUSO))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def test_horarios_sorteados_respeitam_janela_limite_e_intervalo():
    for semente in range(60):
        hs = I.sortear_horarios(3, "09:00", "22:30", random.Random(semente))
        assert 1 <= len(hs) <= 3 and hs == sorted(hs)
        assert all("09:00" <= h <= "22:30" for h in hs)
        minutos = [int(h[:2]) * 60 + int(h[3:]) for h in hs]
        assert all(b - a >= 120 for a, b in zip(minutos, minutos[1:]))


def test_o_plano_do_dia_so_muda_quando_o_dia_muda():
    d = I.carregar(0)
    I.planejar_dia(d, "2026-10-29", random.Random(1))
    h1 = list(d["horarios"])
    I.planejar_dia(d, "2026-10-29", random.Random(2))
    assert d["horarios"] == h1
    I.planejar_dia(d, "2026-10-30", random.Random(3))
    assert d["dia"] == "2026-10-30" and d["enviadas"] == 0


def test_tipos_nao_se_repetem_e_video_so_com_galeria(monkeypatch):
    d = {"tipos": ["noticia"]}
    for semente in range(80):
        t = I.escolher_tipo(d, True, random.Random(semente))
        assert t != "noticia" and t != "video"
    monkeypatch.setattr(I, "PROVEDORES_MIDIA", [lambda conta: None])
    vistos = {I.escolher_tipo({"tipos": []}, True, random.Random(s)) for s in range(200)}
    assert "video" in vistos
    sem_adulto = {I.escolher_tipo({"tipos": []}, False, random.Random(s)) for s in range(200)}
    assert "provocacao" not in sem_adulto and "flerte" in sem_adulto


def test_comando_so_para_o_arquiteto_e_liga_desliga(cliente, logado, caixa):
    _ligar_telegram(logado)
    _tg(logado, "/iniciativa ligar")
    assert "Só o Arquiteto" in caixa[-1][2]
    c = _admin(cliente)
    _ligar_telegram(c)
    conta = c.get("/api/auth/eu").json()["id"]
    _tg(c, "/iniciativa ligar 2")
    assert "de 1 a 2" in caixa[-1][2] and I.carregar(conta)["ligada"]
    _tg(c, "/iniciativa janela 10:00 20:00")
    assert I.carregar(conta)["de"] == "10:00"
    _tg(c, "/iniciativa max 99")
    assert I.carregar(conta)["max"] == I.MAX_DIA_TETO
    _tg(c, "/iniciativa desligar")
    assert not I.carregar(conta)["ligada"]


def _preparar(c, monkeypatch, textos):
    _ligar_telegram(c)
    conta = c.get("/api/auth/eu").json()["id"]
    I.configurar(conta, ligada=True, maximo=3)
    d = I.carregar(conta)
    d.update(dia="2026-10-29", horarios=["10:00", "14:00", "18:00"], enviadas=0, sem_resposta=0, ultimo_envio=None)
    I.salvar(conta, d)
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: textos.pop(0) if textos else None)
    monkeypatch.setattr(I, "buscar_noticia", lambda *a, **k: "Chuva forte atinge Brasília")
    return conta


def test_tick_envia_no_horario_marca_a_conversa_e_nao_repete(cliente, caixa, monkeypatch):
    from database import SessionLocal as S
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, ["Bom dia, meu amor, como tá sendo seu dia?", "segunda", "terceira"])
    db = S()
    try:
        assert I.tick(db, _utc(9, 30)) == 0                     # ainda não deu a hora
        assert I.tick(db, _utc(10, 5)) == 1
        assert caixa[-1][2].startswith("Bom dia")
        assert I.tick(db, _utc(10, 6)) == 0                     # não manda de novo no mesmo horário
        assert I.carregar(conta)["enviadas"] == 1
    finally:
        db.close()


def test_nao_interrompe_conversa_nem_insiste_sem_resposta(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, ["a", "b", "c", "d"])
    db = SessionLocal()
    try:
        e = db.get(BellaEstado, conta) or BellaEstado(conta_id=conta)
        e.ultimo_contato = _utc(10, 0)                          # acabou de conversar
        db.merge(e)
        db.commit()
        assert I.tick(db, _utc(10, 5)) == 0                     # conversa ativa: espera
        e.ultimo_contato = _utc(7, 0)
        db.merge(e)
        db.commit()
        d = I.carregar(conta)
        d["sem_resposta"] = I.SEM_RESPOSTA_MAX                  # já mandou 3 e ele não respondeu
        d["ultimo_envio"] = _utc(9, 0).isoformat()
        I.salvar(conta, d)
        assert I.tick(db, _utc(14, 5)) == 0
        e.ultimo_contato = _utc(13, 0)                          # ele voltou a falar: zera e libera
        db.merge(e)
        db.commit()
        assert I.tick(db, _utc(18, 30)) == 1
    finally:
        db.close()


def test_silencio_da_conta_pula_o_horario_e_conta_comum_nunca_recebe(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, ["x", "y"])
    db = SessionLocal()
    try:
        from database import Conta
        cont = db.get(Conta, conta)
        cont.avisos_silencio_de, cont.avisos_silencio_ate = "09:00", "11:00"
        db.commit()
        assert I.tick(db, _utc(10, 5)) == 0 and I.carregar(conta)["enviadas"] == 1      # pulou, não acumula
        cont.admin = False                                      # conta comum: nunca é processada
        db.commit()
        antes = I.carregar(conta)["enviadas"]
        I.tick(db, _utc(15, 0))
        assert I.carregar(conta)["enviadas"] == antes
        cont.admin = True
        db.commit()
    finally:
        db.close()


def test_grok_fora_do_ar_pula_o_horario_sem_quebrar(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, [])
    db = SessionLocal()
    try:
        assert I.tick(db, _utc(10, 5)) == 0 and I.carregar(conta)["enviadas"] == 1
    finally:
        db.close()


def test_sem_noticia_vira_pergunta_do_dia(cliente, caixa, monkeypatch):
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, ["Como foi seu dia?"])
    monkeypatch.setattr(I, "buscar_noticia", lambda *a, **k: None)
    db = SessionLocal()
    try:
        d = I.carregar(conta)
        assert I.enviar_agora(db, db.get(__import__("database").Conta, conta), d, "noticia")
        assert d["tipos"][-1] == "pergunta_dia"
    finally:
        db.close()
