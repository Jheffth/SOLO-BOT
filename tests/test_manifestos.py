"""Manifestos: o Solo Bot descobre os comandos de cada sistema sozinho."""
from test_fluxos import TG, _ligar_telegram, _tg

FIN = {"X-Solo-Token": "tok-fin"}

V1 = {"versao": "2026.09.30", "comandos": [
    {"comando": "/saldo", "descricao": "Saldo das contas", "exemplo": "/fin saldo nubank"},
    {"comando": "/audio", "descricao": "Resposta falada", "oculto": True}],
    "exemplos": ["gastei 80 almoço nubank"]}

V2 = {**V1, "versao": "2026.10.02", "comandos": V1["comandos"] + [
    {"comando": "/meta", "descricao": "Progresso das metas"}],
    "novidades": ["Agora dá para ver suas metas."]}


def _conectado(c):
    c.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    _ligar_telegram(c)


def test_sistema_empurra_manifesto(logado, sistemas):
    r = logado.post("/interno/manifesto", headers=FIN, json=V1)
    assert r.json() == {"ok": True, "mudou": True, "anunciado": 0}
    assert logado.post("/interno/manifesto", headers=FIN, json=V1).json()["mudou"] is False
    assert logado.post("/interno/manifesto", headers={"X-Solo-Token": "x"}, json=V1).status_code == 403


def test_manifesto_invalido_e_recusado(logado):
    ruim = {"versao": "1", "comandos": [{"comando": "Saldo Geral", "descricao": "x"}]}
    assert logado.post("/interno/manifesto", headers=FIN, json=ruim).status_code == 422


def test_primeiro_manifesto_nao_anuncia_e_versao_nova_anuncia(logado, sistemas, caixa):
    _conectado(logado)
    logado.post("/interno/manifesto", headers=FIN, json=V1)
    n = len(caixa)
    assert len(caixa) == n                                   # o primeiro não vira "novidade"
    r = logado.post("/interno/manifesto", headers=FIN, json=V2).json()
    assert r["anunciado"] == 1
    texto = caixa[-1][2]
    assert "Novidades no 💰 Solo Finances" in texto and "Agora dá para ver suas metas." in texto
    assert "`/fin meta` — Progresso das metas" in texto
    assert "/fin saldo" not in texto                          # comando antigo não é novidade


def test_aviso_desligado_nao_recebe_novidades(logado, sistemas, caixa):
    _conectado(logado)
    logado.patch("/api/conta/canais/telegram", json={"avisos": False})
    logado.post("/interno/manifesto", headers=FIN, json=V1)
    assert logado.post("/interno/manifesto", headers=FIN, json=V2).json()["anunciado"] == 0


def test_ajuda_e_painel_usam_o_manifesto(logado, sistemas, caixa):
    _conectado(logado)
    logado.post("/interno/manifesto", headers=FIN, json=V2)
    _tg(logado, "/ajuda")
    ajuda = caixa[-1][2]
    assert "`/fin saldo` — Saldo das contas" in ajuda and "`/fin meta`" in ajuda
    assert "/fin audio" not in ajuda                           # oculto fica de fora
    fin = next(s for s in logado.get("/api/conta").json()["sistemas"] if s["chave"] == "fin")
    assert [c["comando"] for c in fin["comandos"]] == ["/saldo", "/meta"]
    assert fin["exemplos"] == ["gastei 80 almoço nubank"]


def test_busca_periodica(cliente, sistemas):
    from database import SessionLocal
    from nucleo import manifestos
    db = SessionLocal()
    r = manifestos.buscar_todos(db)
    assert r == {"fin": "ok (nova versão)", "rot": "ok (nova versão)"}
    assert manifestos.buscar_todos(db) == {"fin": "ok", "rot": "ok"}
    assert manifestos.de(db, "rot")["origem"] == "buscado"
    db.close()


def test_admin_sincroniza_e_mostra_versao(cliente, sistemas):
    cliente.post("/api/auth/cadastro", json={"nome": "Arq", "usuario": "arq", "email": "arquiteto@solo.dev", "senha": "12345678"})
    assert cliente.post("/api/admin/manifestos/sincronizar").json()["fin"].startswith("ok")
    s = {x["chave"]: x for x in cliente.get("/api/admin/status").json()["sistemas"]}
    assert s["fin"]["manifesto"]["versao"] == "1" and s["fin"]["manifesto"]["comandos"] == 1
