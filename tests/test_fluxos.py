"""Os fluxos de ponta a ponta: conta, canais, sistemas e a conversa."""
import database
from database import SessionLocal

TG = {"x-telegram-bot-api-secret-token": "tg-secreto"}


def _tg(cliente, texto, chat=777, uid=[0]):
    uid[0] += 1
    return cliente.post("/api/telegram/webhook", headers=TG, json={
        "update_id": uid[0], "message": {"chat": {"id": chat, "type": "private"},
                                         "from": {"username": "jeff"}, "text": texto}})


def _toque(cliente, dados, chat=777, uid=[1000]):
    uid[0] += 1
    return cliente.post("/api/telegram/webhook", headers=TG, json={
        "update_id": uid[0], "callback_query": {"id": "cb", "data": dados,
                                                "message": {"chat": {"id": chat}}}})


def _wa(cliente, texto, jid="5561988887777@s.whatsapp.net", mid=[0]):
    mid[0] += 1
    return cliente.post("/api/whatsapp/webhook/wa-secreto", json={
        "event": "messages.upsert", "data": {"key": {"remoteJid": jid, "id": f"m{mid[0]}", "fromMe": False},
                                             "pushName": "Jeff", "message": {"conversation": texto}}})


def _ligar_telegram(c):
    codigo = c.post("/api/conta/canais/telegram/codigo").json()["codigo"]
    _tg(c, f"/start {codigo}")


# ── conta ─────────────────────────────────────────────────────────
def test_cadastro_entrar_e_senha_errada(cliente):
    assert cliente.post("/api/auth/cadastro", json={"nome": "A", "email": "x@y.z", "senha": "12345678"}).status_code == 422
    r = cliente.post("/api/auth/cadastro", json={"nome": "Ana", "email": "Ana@Solo.dev", "senha": "12345678"})
    assert r.status_code == 200 and r.json()["email"] == "ana@solo.dev"
    assert cliente.post("/api/auth/cadastro", json={"nome": "Ana", "email": "ana@solo.dev", "senha": "12345678"}).status_code == 409
    cliente.post("/api/auth/sair")
    cliente.cookies.clear()
    assert cliente.get("/api/auth/eu").status_code == 401
    assert cliente.post("/api/auth/entrar", json={"email": "ana@solo.dev", "senha": "errada00"}).status_code == 401
    assert cliente.post("/api/auth/entrar", json={"email": "ana@solo.dev", "senha": "12345678"}).status_code == 200
    assert cliente.get("/api/auth/eu").json()["nome"] == "Ana"


def test_admin_pelo_email(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Arq", "email": "arquiteto@solo.dev", "senha": "12345678"})
    assert r.json()["admin"] is True


def test_admin_bloqueado_para_comum(logado):
    assert logado.get("/api/admin/status").status_code == 403


# ── canais ────────────────────────────────────────────────────────
def test_telegram_deep_link_vincula(logado, caixa):
    r = logado.post("/api/conta/canais/telegram/codigo").json()
    assert r["link"].startswith("https://t.me/SoloBot?start=")
    _tg(logado, f"/start {r['codigo']}")
    assert "agora é da sua Conta Solo" in caixa[-1][2]
    canais = logado.get("/api/conta").json()["canais"]
    assert canais[0]["conectado"] and canais[0]["rotulo"] == "@jeff"
    # uso único
    _tg(logado, f"/start {r['codigo']}", chat=888)
    assert "não vale mais" in caixa[-1][2]


def test_whatsapp_mensagem_pronta_vincula(logado, caixa):
    r = logado.post("/api/conta/canais/whatsapp/codigo").json()
    assert r["mensagem"].startswith("SOLO ") and "wa.me/5561999990000" in r["link"]
    _wa(logado, r["mensagem"].lower())
    assert "agora é da sua Conta Solo" in caixa[-1][2]


def test_castigo_apos_cinco_erros(logado, caixa):
    for _ in range(5):
        _wa(logado, "SOLO 000000", jid="5500@s.whatsapp.net")
    r = logado.post("/api/conta/canais/whatsapp/codigo").json()
    _wa(logado, r["mensagem"], jid="5500@s.whatsapp.net")
    assert "Muitas tentativas" in caixa[-1][2]


def test_desconhecido_recebe_boas_vindas(cliente, caixa):
    _tg(cliente, "oi", chat=12345)
    assert "Crie sua Conta Solo" in caixa[-1][2]


def test_webhooks_recusam_sem_segredo(cliente):
    assert cliente.post("/api/telegram/webhook", json={}).status_code == 403
    assert cliente.post("/api/whatsapp/webhook/errado", json={}).status_code == 403


# ── conectar sistemas (de dentro para fora) ───────────────────────
def test_conectar_sistema(logado, sistemas):
    assert logado.get("/api/conectar/fin").json()["nome"] == "Solo Finances"
    r = logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    assert r.status_code == 200, r.text
    assert r.json()["nome_remoto"] == "jefferson" and r.json()["retorno"] == "https://fin.example/bots"
    # código de uso único
    assert logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"}).status_code == 400
    s = {x["chave"]: x for x in logado.get("/api/conta").json()["sistemas"]}
    assert s["fin"]["conectado"] and not s["rot"]["conectado"]


def test_conectar_exige_sessao(cliente, sistemas):
    assert cliente.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"}).status_code == 401
    assert sistemas.codigos["fin"]  # nada foi consumido


def test_usuario_do_sistema_muda_de_conta(logado, sistemas):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/api/auth/sair"); logado.cookies.clear()
    logado.post("/api/auth/cadastro", json={"nome": "Outra", "email": "o@solo.dev", "senha": "12345678"})
    sistemas.codigos["fin"]["CODFIN2"] = ("4", "jefferson")
    r = logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN2"}).json()
    assert r["trocou_de_conta"] is True
    db = SessionLocal()
    assert db.query(database.VinculoSistema).count() == 1
    db.close()


# ── a conversa ────────────────────────────────────────────────────
def test_hub_pergunta_e_encaminha_pendente(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)

    _tg(logado, "comprei pão 8")
    assert "Para qual sistema" in caixa[-1][2]
    teclado = caixa[-1][3]["inline_keyboard"][0]
    assert [b["callback_data"] for b in teclado] == ["hub:app|fin", "hub:app|rot"]

    _toque(logado, "hub:app|fin")
    assert caixa[-1][2].startswith("💰 *Finances*") and "eco:comprei pão 8" in caixa[-1][2]
    assert sistemas.recebidos[-1][2]["usuario_id"] == "4"

    _tg(logado, "60 uber")                      # continua no modo Finances
    assert "eco:60 uber" in caixa[-1][2] and sistemas.recebidos[-1][0] == "fin"


def test_prefixo_troca_modo_e_sair_volta(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _tg(logado, "/rot hoje")
    assert "eco:hoje" in caixa[-1][2] and caixa[-1][3]["inline_keyboard"][1][0]["callback_data"] == "rot:ok|r|12"
    _toque(logado, "rot:ok|r|12")
    assert ("toque", "cb", "ok!", None) in caixa
    assert sistemas.recebidos[-1][1:] == ("acao", {**sistemas.recebidos[-1][2], "dados": "ok|r|12"})
    _tg(logado, "/fin")
    assert "eco:/ajuda" in caixa[-1][2]
    _tg(logado, "/sair")
    assert "De volta ao hub" in caixa[-1][2]


def test_um_sistema_so_vai_direto(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    _tg(logado, "banho")
    assert "eco:banho" in caixa[-1][2]


def test_sistema_nao_conectado(logado, sistemas, caixa):
    _ligar_telegram(logado)
    _tg(logado, "/fin saldo")
    assert "ainda não conectou" in caixa[-1][2]


def test_whatsapp_lista_numerada(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    r = logado.post("/api/conta/canais/whatsapp/codigo").json()
    _wa(logado, r["mensagem"])
    _wa(logado, "/rot hoje")
    assert "*1.* ✅ — Banho" in caixa[-1][2]
    _wa(logado, "1")
    assert "feito:ok|r|12" in caixa[-1][2]
    _wa(logado, "1")                            # uso único: vira texto comum
    assert "eco:1" in caixa[-1][2]


def test_idempotencia(logado, caixa):
    _ligar_telegram(logado)
    n = len(caixa)
    corpo = {"update_id": 99999, "message": {"chat": {"id": 777, "type": "private"}, "text": "/conta"}}
    logado.post("/api/telegram/webhook", headers=TG, json=corpo)
    logado.post("/api/telegram/webhook", headers=TG, json=corpo)
    assert len(caixa) == n + 1


def test_atividade_nao_guarda_texto(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    _ligar_telegram(logado)
    _tg(logado, "/fin gastei 4200 no cartão")
    _tg(logado, "salário 9000")
    resumos = [a["resumo"] for a in logado.get("/api/conta").json()["atividade"]]
    assert "/fin" in resumos and "mensagem" in resumos
    assert not any("9000" in r or "4200" in r for r in resumos)


# ── avisos (sistema → pessoa) ─────────────────────────────────────
def test_aviso_chega_e_ativa_modo(logado, sistemas, caixa):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    _ligar_telegram(logado)
    r = logado.post("/interno/enviar", headers={"X-Solo-Token": "tok-rot"},
                    json={"usuario_id": "1", "texto": "☀️ Bom dia! 3 missões hoje."})
    assert r.json()["entregues"] == 1
    assert caixa[-1][2].startswith("⚔️ *Rotinas*")
    _tg(logado, "pendentes")                    # responder ao aviso cai no Rotinas
    assert sistemas.recebidos[-1][0] == "rot"


def test_aviso_token_errado(cliente):
    r = cliente.post("/interno/enviar", headers={"X-Solo-Token": "nada"}, json={"usuario_id": "1", "texto": "x"})
    assert r.status_code == 403


def test_desconectar_sistema_avisa(logado, sistemas):
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    assert logado.delete("/api/conta/sistemas/fin").status_code == 200
    assert sistemas.recebidos[-1][:2] == ("fin", "desvinculado")


def test_paginas_servidas(cliente):
    for p in ("/", "/painel", "/conectar", "/admin"):
        assert cliente.get(p).status_code == 200


def _wa_eu(cliente, texto, jid, mid=[5000]):
    mid[0] += 1
    return cliente.post("/api/whatsapp/webhook/wa-secreto", json={
        "event": "messages.upsert", "data": {"key": {"remoteJid": jid, "id": f"e{mid[0]}", "fromMe": True},
                                             "message": {"conversation": texto}}})


def test_eco_do_proprio_aparelho(logado, sistemas, caixa):
    dono = "5561999990000@s.whatsapp.net"
    r = logado.post("/api/conta/canais/whatsapp/codigo").json()
    _wa_eu(logado, r["mensagem"], dono)                 # código passa, mesmo fromMe
    assert "agora é da sua Conta Solo" in caixa[-1][2]
    n = len(caixa)
    _wa_eu(logado, "💰 Finances resposta do bot", dono)  # eco da resposta: ignora
    _wa_eu(logado, "oi amigo, tudo bem?", "5511888887777@s.whatsapp.net")  # conversa pessoal
    _wa_eu(logado, "/menu", "5511888887777@s.whatsapp.net")  # comando para um amigo não vinculado
    assert len(caixa) == n
    _wa_eu(logado, "/conta", dono)
    assert len(caixa) == n + 1
