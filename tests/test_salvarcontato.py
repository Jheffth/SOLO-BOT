"""/salvarcontato: o contato compartilhado no WhatsApp (ou no Telegram) entra na lista de "Enviar áudio"."""
import pytest

from database import ContatoAudio, SessionLocal
from nucleo import contatos_audio, roteador
from test_clonarvoz import _admin
from test_fluxos import TG, _ligar_telegram, _tg, _wa

JID = "5561988887777@s.whatsapp.net"
VCARD_MARIA = ("BEGIN:VCARD\nVERSION:3.0\nN:Souza;Maria;;;\nFN:Maria Souza\n"
               "item1.TEL;waid=5511912345678:+55 11 91234-5678\nitem1.X-ABLabel:Celular\nEND:VCARD")


@pytest.fixture(autouse=True)
def _limpo():
    roteador._SALVAR_CONTATO.clear()
    yield
    roteador._SALVAR_CONTATO.clear()


def _ligar_whatsapp(c):
    _wa(c, c.post("/api/conta/canais/whatsapp/codigo").json()["mensagem"], jid=JID)


def _cartao(c, *cartoes, de_mim=False, mid=[0]):
    mid[0] += 1
    if len(cartoes) == 1:
        mensagem = {"contactMessage": cartoes[0]}
    else:
        mensagem = {"contactsArrayMessage": {"displayName": f"{len(cartoes)} contatos", "contacts": list(cartoes)}}
    return c.post("/api/whatsapp/webhook/wa-secreto", json={
        "event": "messages.upsert", "data": {"key": {"remoteJid": JID, "id": f"ct{mid[0]}", "fromMe": de_mim},
                                             "pushName": "Jeff", "message": mensagem}})


def _salvos():
    db = SessionLocal()
    try:
        return sorted((x.nome, x.numero) for x in db.query(ContatoAudio).all())
    finally:
        db.close()


# ── o cartão de contato (vCard) ─────────────────────────────────
def test_vcard_do_whatsapp_usa_o_waid_e_o_nome_exibido():
    assert contatos_audio.do_vcard(VCARD_MARIA, "Maria") == ("Maria", "+5511912345678")
    assert contatos_audio.do_vcard(VCARD_MARIA) == ("Maria Souza", "+5511912345678")


def test_vcard_sem_whatsapp_usa_o_tel_e_completa_o_ddi():
    vcard = "BEGIN:VCARD\r\nVERSION:3.0\r\nN:Lima;Ana\\, a vizinha;;;\r\nTEL;TYPE=CELL:(11) 98765-4321\r\nEND:VCARD"
    nome, numero = contatos_audio.do_vcard(vcard)
    assert nome == "Ana, a vizinha Lima"
    assert contatos_audio.numero_de_contato(numero) == "5511987654321"
    assert contatos_audio.numero_de_contato("+1 (202) 555-0123") == "12025550123"
    assert contatos_audio.numero_de_contato("011 98765-4321") == "5511987654321"
    with pytest.raises(contatos_audio.NumeroInvalido):
        contatos_audio.numero_de_contato("1234")


# ── WhatsApp ────────────────────────────────────────────────────
def test_admin_salva_o_contato_compartilhado_no_whatsapp(cliente, caixa):
    c = _admin(cliente)
    _ligar_whatsapp(c)
    _wa(c, "/salvarcontato", jid=JID)
    assert "Me mande o contato" in caixa[-1][2] and "📎" in caixa[-1][2]
    _cartao(c, {"displayName": "Maria", "vcard": VCARD_MARIA})
    assert _salvos() == [("Maria", "5511912345678")]
    assert "Maria" in caixa[-1][2] and "+5511912345678" in caixa[-1][2] and "Enviar áudio" in caixa[-1][2]
    # o pedido vale para UMA mensagem: o próximo cartão só ganha a dica
    _cartao(c, {"displayName": "Outro", "vcard": VCARD_MARIA.replace("5511912345678", "5511900000000")})
    assert len(_salvos()) == 1 and "/salvarcontato" in caixa[-1][2]
    # e a lista do painel é a mesma
    assert [x["nome"] for x in c.get("/api/admin/audios").json()["contatos"]] == ["Maria"]


def test_varios_de_uma_vez_e_sem_repetir(cliente, caixa):
    c = _admin(cliente)
    _ligar_whatsapp(c)
    _wa(c, "/salvarcontato", jid=JID)
    _cartao(c, {"displayName": "Maria", "vcard": VCARD_MARIA})
    _wa(c, "/salvarcontato", jid=JID)
    joao = "BEGIN:VCARD\nVERSION:3.0\nFN:João\nTEL;type=CELL;waid=5521987654321:+55 21 98765-4321\nEND:VCARD"
    _cartao(c, {"displayName": "Maria de novo", "vcard": VCARD_MARIA}, {"displayName": "João", "vcard": joao})
    assert _salvos() == [("João", "5521987654321"), ("Maria", "5511912345678")]
    texto = caixa[-1][2]
    assert "João" in texto and "já estava na lista como *Maria*" in texto


def test_cartao_sem_numero_deixa_tentar_de_novo(cliente, caixa):
    c = _admin(cliente)
    _ligar_whatsapp(c)
    _wa(c, "/salvarcontato", jid=JID)
    _cartao(c, {"displayName": "Sem número", "vcard": "BEGIN:VCARD\nVERSION:3.0\nFN:Sem número\nEND:VCARD"})
    assert _salvos() == [] and "Não achei nenhum contato" in caixa[-1][2]
    _cartao(c, {"displayName": "Maria", "vcard": VCARD_MARIA})
    assert _salvos() == [("Maria", "5511912345678")]


def test_cancelar_e_salvar_direto(cliente, caixa):
    c = _admin(cliente)
    _ligar_whatsapp(c)
    _wa(c, "/salvarcontato", jid=JID)
    _wa(c, "/salvarcontato cancelar", jid=JID)
    _cartao(c, {"displayName": "Maria", "vcard": VCARD_MARIA})
    assert _salvos() == []
    _wa(c, "/salvarcontato Dona Cida (11) 3333-4444", jid=JID)
    assert _salvos() == [("Dona Cida", "551133334444")]
    _wa(c, "/salvarcontato Fulano 12", jid=JID)
    assert "Use `/salvarcontato Nome" in caixa[-1][2] and len(_salvos()) == 1


def test_conta_comum_nao_salva(logado, caixa):
    _ligar_whatsapp(logado)
    _wa(logado, "/salvarcontato", jid=JID)
    assert "administradora" in caixa[-1][2]
    _cartao(logado, {"displayName": "Maria", "vcard": VCARD_MARIA})
    assert _salvos() == [] and "leio texto" in caixa[-1][2]


def test_desconhecido_que_manda_contato_nao_recebe_nada(cliente, caixa):
    _cartao(cliente, {"displayName": "Maria", "vcard": VCARD_MARIA})
    assert caixa == [] and _salvos() == []


def test_cartao_do_proprio_aparelho_so_vale_com_pedido(cliente, caixa):
    c = _admin(cliente)
    _ligar_whatsapp(c)
    n = len(caixa)
    _cartao(c, {"displayName": "Maria", "vcard": VCARD_MARIA}, de_mim=True)
    assert len(caixa) == n and _salvos() == []     # sem pedido, o eco do aparelho é ignorado
    _wa(c, "/salvarcontato", jid=JID)
    _cartao(c, {"displayName": "Maria", "vcard": VCARD_MARIA}, de_mim=True)
    assert _salvos() == [("Maria", "5511912345678")]


# ── Telegram ────────────────────────────────────────────────────
def test_telegram_tambem_salva(cliente, caixa):
    c = _admin(cliente)
    _ligar_telegram(c)
    _tg(c, "/salvarcontato")
    c.post("/api/telegram/webhook", headers=TG, json={"update_id": 99001, "message": {
        "chat": {"id": 777, "type": "private"}, "from": {"username": "jeff"},
        "contact": {"phone_number": "5511912345678", "first_name": "Maria", "last_name": "Souza"}}})
    assert _salvos() == [("Maria Souza", "5511912345678")]
    assert "Maria Souza" in caixa[-1][2]


def test_ajuda_mostra_o_comando_so_para_o_admin(cliente, caixa):
    c = _admin(cliente)
    _ligar_telegram(c)
    _tg(c, "/ajuda")
    assert "/salvarcontato" in caixa[-1][2]
