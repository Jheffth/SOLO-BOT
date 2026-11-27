"""Avisos para números de WhatsApp avulsos (ex.: venda da Ótica Elite)."""
import pytest

from canais import evolution
from nucleo import avisos_numeros, models_persona

FIN = {"X-Solo-Token": "tok-fin"}


@pytest.fixture()
def whats(monkeypatch):
    enviados = []
    monkeypatch.setattr(evolution, "estado_simples", lambda: "open")

    def enviar(numero, texto):
        enviados.append((numero, texto))
        return {"estado": "enviado", "mensagem_id": f"id{len(enviados)}", "detalhe": "ok"}
    monkeypatch.setattr(evolution, "enviar_texto_confirmado", enviar)
    return enviados


def _pedido(**extra):
    corpo = {"numeros": ["(61) 99999-1111", "+55 61 98888-2222"], "texto": "🛒 Pedido #12 pago — R$ 389,90",
             "referencia": "pedido-12-pago"}
    corpo.update(extra)
    return corpo


def test_entrega_para_cada_numero_com_selo(cliente, whats):
    r = cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido())
    assert r.status_code == 200, r.text
    assert r.json() == {"aceitos": 2, "repetidos": 0, "recusados": [], "persona": False}
    assert [n for n, _ in whats] == ["5561999991111", "5561988882222"]
    assert all("Pedido #12 pago — R$ 389,90" in t and t.startswith("💰 *Finances*") for _, t in whats)


def test_repetir_o_pedido_nao_duplica(cliente, whats):
    cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido())
    r = cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido()).json()
    assert r["aceitos"] == 0 and r["repetidos"] == 2 and len(whats) == 2
    r = cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido(numeros=["61999991111", "61977773333"])).json()
    assert r["aceitos"] == 1 and r["repetidos"] == 1 and whats[-1][0] == "5561977773333"


def test_numero_invalido_volta_recusado(cliente, whats):
    r = cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido(numeros=["abc", "123", "61999991111"])).json()
    assert r["aceitos"] == 1 and r["recusados"] == ["abc", "123"]


def test_token_invalido_e_limites(cliente, whats, monkeypatch):
    assert cliente.post("/interno/avisar-numeros", headers={"X-Solo-Token": "x"}, json=_pedido()).status_code == 403
    muitos = [f"619999{i:05d}" for i in range(11)]
    assert cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido(numeros=muitos)).status_code == 429
    monkeypatch.setattr(avisos_numeros, "LIMITE_POR_MINUTO", 3)
    cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido())
    r = cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido(referencia="outro"))
    assert r.status_code == 429 and len(whats) == 2


def test_whatsapp_desconectado_pede_nova_tentativa_sem_registrar(cliente, whats, monkeypatch):
    monkeypatch.setattr(evolution, "estado_simples", lambda: "close")
    assert cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido()).status_code == 503
    monkeypatch.setattr(evolution, "estado_simples", lambda: "open")
    assert cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido()).json()["aceitos"] == 2


def test_na_voz_da_modelo(cliente, whats, monkeypatch):
    import database
    db = database.SessionLocal()
    db.add(database.Conta(nome="Arquiteto", usuario="arq", senha_hash="x", admin=True))
    db.commit()
    db.close()
    monkeypatch.setattr(models_persona, "ativa", lambda db, conta: True)
    monkeypatch.setattr(models_persona, "enfileirar", lambda tarefa: tarefa(database.SessionLocal()))
    vistos = []

    def aplicar(conta, sistema, selo, mensagens, usuario=None):
        vistos.append((conta.usuario, sistema))
        return [{"texto": "Amor, saiu venda! 🛒 Pedido #12 pago — R$ 389,90", "persona": True}]
    monkeypatch.setattr(models_persona, "aplicar", aplicar)
    r = cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido(persona=True)).json()
    assert r["persona"] is True and r["aceitos"] == 2
    assert vistos == [("arq", "Finances")]                       # reescreve uma vez só
    assert all(t.startswith("Amor, saiu venda!") for _, t in whats) and len(whats) == 2


def test_persona_falha_vai_o_texto_do_sistema(cliente, whats, monkeypatch):
    import database
    db = database.SessionLocal()
    db.add(database.Conta(nome="Arquiteto", usuario="arq", senha_hash="x", admin=True))
    db.commit()
    db.close()
    monkeypatch.setattr(models_persona, "ativa", lambda db, conta: True)
    monkeypatch.setattr(models_persona, "enfileirar", lambda tarefa: tarefa(database.SessionLocal()))
    monkeypatch.setattr(models_persona, "aplicar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("grok fora")))
    cliente.post("/interno/avisar-numeros", headers=FIN, json=_pedido(persona=True))
    assert len(whats) == 2 and all("Pedido #12 pago" in t for _, t in whats)


def test_sistema_so_de_avisos_fica_fora_dos_menus_e_aparece_no_painel(cliente, whats):
    import config
    from nucleo import modulos
    antes = list(config.MODULOS)
    try:
        modulos.recarregar(antes + [{"chave": "elite", "nome": "Ótica Elite", "emoji": "🕶️", "url": "http://elite",
                                      "token": "tok-elite", "so_avisos": True}])
        assert "elite" not in [m.chave for m in modulos.todos()]
        r = cliente.post("/interno/avisar-numeros", headers={"X-Solo-Token": "tok-elite"}, json=_pedido())
        assert r.json()["aceitos"] == 2 and whats[0][1].startswith("🕶️ *Ótica Elite*")
        assert [m.chave for m in modulos.so_avisos()] == ["elite"]

        # Painel: o Arquiteto vê a Elite com o estado dos avisos; contas comuns não.
        import database
        r = cliente.post("/api/auth/cadastro", json={"nome": "Jefferson", "usuario": "arq", "email": "a@solo.dev", "senha": "senha-forte-1"})
        assert r.status_code == 200, r.text
        db = database.SessionLocal()
        db.query(database.Conta).filter(database.Conta.usuario == "arq").update({"admin": True})
        db.commit()
        db.close()
        sist = cliente.get("/api/conta").json()["sistemas"]
        elite = next(x for x in sist if x["chave"] == "elite")
        assert elite["so_avisos"] and elite["conectado"] and elite["comandos"] == []
        assert elite["avisos"]["enviados_7d"] == 2 and elite["avisos"]["falhas_7d"] == 0 and elite["avisos"]["ultimo_em"]
        assert all(not x.get("so_avisos") for x in sist if x["chave"] != "elite")
        adm = cliente.get("/api/admin/status")
        if adm.status_code == 200:
            linha = next(x for x in adm.json()["sistemas"] if x["chave"] == "elite")
            assert linha["so_avisos"] and linha["avisos"]["total"] == 2
        db = database.SessionLocal()
        db.query(database.Conta).filter(database.Conta.usuario == "arq").update({"admin": False})
        db.commit()
        db.close()
        assert all(x["chave"] != "elite" for x in cliente.get("/api/conta").json()["sistemas"])
    finally:
        modulos.recarregar(antes)
