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
    I.configurar(conta, ligada=True, maximo=3, bom_dia=False)
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


# ── Bom dia com foto e galeria ───────────────────────────────────
import base64

from nucleo import bella_galeria as G

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


def _galeria(tmp_path, monkeypatch, niveis=("bom_dia",), n=2):
    monkeypatch.setattr(config, "BELLA_GALERIA_DIR", str(tmp_path))
    for nivel in niveis:
        pasta = tmp_path / "bella" / nivel
        pasta.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (pasta / f"f{i}.jpg").write_bytes(JPEG)


def test_galeria_sorteia_sem_repetir_e_ignora_niveis_intimos(tmp_path, monkeypatch, cliente):
    _galeria(tmp_path, monkeypatch, ("bom_dia", "nu", "topless"), 2)
    assert G.contar("bella") == {"bom_dia": 2, "normal": 0, "sensual": 0}      # nu/topless nunca são servidos
    assert G.escolher("bella", ("nu",)) is None and G.escolher("bella", ("topless",)) is None
    a = G.escolher("bella", ("bom_dia",), rng=random.Random(1))
    b = G.escolher("bella", ("bom_dia",), rng=random.Random(1))
    assert a["tipo"] == "imagem" and base64.b64decode(a["base64"]) == JPEG
    assert a and b and G._usadas("bella_galeria_usadas:bella")[-2:] != [] and len(set(G._usadas("bella_galeria_usadas:bella")[-2:])) == 2


def test_arquivo_falso_ou_pasta_vazia_nao_quebra(tmp_path, monkeypatch, cliente):
    monkeypatch.setattr(config, "BELLA_GALERIA_DIR", str(tmp_path))
    (tmp_path / "bella" / "bom_dia").mkdir(parents=True)
    (tmp_path / "bella" / "bom_dia" / "x.jpg").write_bytes(b"isto nao e uma foto")
    assert G.escolher("bella", ("bom_dia",)) is None
    assert G.escolher("bella", ("normal",)) is None


def test_bom_dia_sai_as_08_uma_vez_com_foto(cliente, caixa, tmp_path, monkeypatch):
    _galeria(tmp_path, monkeypatch)
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, ["Bom dia, meu amor. Acordei pensando em você.", "outra"])
    I.configurar(conta, ligada=False, bom_dia=True, bom_dia_hora="08:00")        # só o bom dia nesta prova
    d = I.carregar(conta)
    d["bom_dia_ultimo"] = ""
    I.salvar(conta, d)
    db = SessionLocal()
    try:
        assert I.tick(db, _utc(7, 59)) == 0                                      # ainda não
        assert I.tick(db, _utc(8, 1)) == 1
        assert I.tick(db, _utc(8, 2)) == 0 and I.tick(db, _utc(9, 0)) == 0       # só uma vez no dia
        assert I.carregar(conta)["bom_dia_ultimo"] == "2026-10-29"
        assert I.carregar(conta)["enviadas"] == 0 and I.carregar(conta)["sem_resposta"] == 0   # não gasta o limite
        d = I.carregar(conta)
        d["bom_dia_ultimo"] = ""
        I.salvar(conta, d)
        assert I.tick(db, _utc(12, 0)) == 0                                      # mais de 3 h depois: perdeu
    finally:
        db.close()


def test_bom_dia_espera_o_silencio_e_pode_ser_desligado(cliente, caixa, tmp_path, monkeypatch):
    _galeria(tmp_path, monkeypatch)
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, ["Bom dia!", "x"])
    I.configurar(conta, bom_dia=True)
    d = I.carregar(conta)
    d["bom_dia_ultimo"] = ""
    I.salvar(conta, d)
    db = SessionLocal()
    try:
        from database import Conta
        cont = db.get(Conta, conta)
        cont.avisos_silencio_de, cont.avisos_silencio_ate = "07:00", "08:30"
        db.commit()
        assert I.tick(db, _utc(8, 5)) == 0                                       # em silêncio: espera
        assert I.tick(db, _utc(8, 31)) == 1                                      # acabou o silêncio: sai (dentro das 3 h)
        cont.avisos_silencio_de = cont.avisos_silencio_ate = None
        db.commit()
        I.configurar(conta, bom_dia=False)
        d = I.carregar(conta)
        d["bom_dia_ultimo"] = ""
        I.salvar(conta, d)
        assert I.tick(db, _utc(8, 40)) == 0
    finally:
        db.close()


def test_bom_dia_sem_foto_vai_so_o_texto_e_comandos(cliente, caixa, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BELLA_GALERIA_DIR", str(tmp_path))
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, ["Bom dia, amor."])
    _tg(c, "/iniciativa bomdia hora 07:30")
    assert I.carregar(conta)["bom_dia_hora"] == "07:30"
    _tg(c, "/iniciativa bomdia testar")
    assert "Mandei um bom dia" in caixa[-1][2] or any("Bom dia, amor." in str(m) for m in caixa[-3:])
    _tg(c, "/galeria")
    assert "Galeria da Bella" in caixa[-1][2] and "bom_dia: 0" in caixa[-1][2]


def test_bom_dia_pode_ser_picante_ou_explicito_so_com_conteudo_adulto(cliente, monkeypatch):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    from nucleo import bella_estado
    bella_estado.definir_automatico(conta)
    vistos = {I.intensidade_bom_dia(conta, True, random.Random(s)) for s in range(200)}
    assert vistos == {"suave", "picante", "explicito"}
    assert {I.intensidade_bom_dia(conta, False, random.Random(s)) for s in range(50)} == {"suave"}
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", True)
    bella_estado.definir_fixa(conta, 4)                                       # ele fixou a temperatura em 4
    assert I.intensidade_bom_dia(conta, True) == "explicito"
    bella_estado.definir_fixa(conta, 2)
    assert I.intensidade_bom_dia(conta, True) == "picante"
    bella_estado.definir_automatico(conta)


def test_foto_do_bom_dia_acompanha_a_intensidade_e_nu_so_se_habilitado(tmp_path, monkeypatch, cliente):
    _galeria(tmp_path, monkeypatch, ("bom_dia", "sensual", "nu"), 1)
    pic = G.escolher("bella", I.NIVEIS_BOM_DIA["picante"], rng=random.Random(0))
    assert pic                                                                 # pegou 'sensual'
    assert G._usadas("bella_galeria_usadas:bella")[-1].startswith("sensual/")
    assert G.escolher("bella", ("nu",)) is None                                # nu desligado por padrão
    monkeypatch.setattr(config, "BELLA_GALERIA_NIVEIS", "bom_dia,normal,sensual,nu")
    assert G.escolher("bella", I.NIVEIS_BOM_DIA["explicito"], rng=random.Random(0))
    assert G._usadas("bella_galeria_usadas:bella")[-1].startswith("nu/")


def test_bom_dia_pode_ir_com_video(cliente, caixa, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BELLA_GALERIA_DIR", str(tmp_path))
    pasta = tmp_path / "bella" / "bom_dia"
    pasta.mkdir(parents=True)
    (pasta / "v.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 64)       # só há um vídeo
    c = _admin(cliente)
    conta = _preparar(c, monkeypatch, ["Bom dia, meu amor."])
    I.configurar(conta, ligada=False, bom_dia=True)
    d = I.carregar(conta)
    d["bom_dia_ultimo"] = ""
    I.salvar(conta, d)
    vistos = []
    monkeypatch.setattr(grok, "gerar", lambda sis, t, **k: vistos.append(sis) or "Bom dia, meu amor.")
    db = SessionLocal()
    try:
        assert I.tick(db, _utc(8, 1)) == 1
    finally:
        db.close()
    assert "um vídeo seu" in vistos[-1]
