"""Envio manual com DB isolado e provedores simulados; nenhum WhatsApp real."""
import base64
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from canais import evolution
from database import Base, Conta, ContatoAudio, EnvioAudio
from nucleo import fala
from routers import disparos
from seguranca import conta_admin


@pytest.fixture()
def ambiente(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    conta = Conta(nome="Admin", usuario="admin", senha_hash="fixture", admin=True)
    outra = Conta(nome="Outra", usuario="outra", senha_hash="fixture", admin=True)
    db.add_all([conta, outra]); db.commit()
    tts, envios = [], []
    monkeypatch.setattr(evolution, "disponivel", lambda: True)
    monkeypatch.setattr(evolution, "estado_simples", lambda: "open")
    monkeypatch.setattr(fala, "disponivel", lambda: True)
    def gerar(texto, canal):
        tts.append((texto, canal))
        return {"base64": base64.b64encode(b"ID3fixture").decode(), "mime": "audio/mpeg"}
    def enviar(numero, codigo):
        envios.append((numero, codigo))
        return {"estado": "enviado", "mensagem_id": "mensagem-teste", "detalhe": "Aceito"}
    monkeypatch.setattr(fala, "sintetizar", gerar)
    monkeypatch.setattr(evolution, "enviar_audio_confirmado", enviar)
    yield db, conta, outra, tts, envios, factory
    db.close(); engine.dispose()


def contato(a, nome="Pessoa", numero="+55 (11) 99999-9999"):
    return disparos.adicionar(disparos.Contato(nome=nome, numero=numero), a[1], a[0])


def pedido(c, texto="Olá! Esta é minha mensagem.", id=None):
    return disparos.PedidoEnvio(pedido_id=id or uuid4(), contato_id=c["id"], texto=texto)


def test_contatos_persistentes_e_isolados(ambiente):
    a=ambiente; c=contato(a)
    assert c["numero"] == "5511999999999"
    assert disparos.painel(a[1], a[0])["contatos"] == [c]
    assert disparos.painel(a[2], a[0])["contatos"] == []
    with pytest.raises(HTTPException) as erro: contato(a)
    assert erro.value.status_code == 409
    with pytest.raises(HTTPException): disparos.remover(c["id"], a[2], a[0])
    assert disparos.remover(c["id"], a[1], a[0]) == {"ok": True}
    assert a[3] == a[4] == []


@pytest.mark.parametrize("numero", ["https://wa.me/5511999999999", "120333@g.us", "00000000", "1234567", "1" * 16, "ABC12345678"])
def test_numero_invalido(numero):
    with pytest.raises(HTTPException): disparos.numero_valido(numero)


def test_numero_internacional():
    assert disparos.numero_valido("+1 (202) 555-0123") == "12025550123"


def test_envio_texto_integral_e_idempotente(ambiente):
    a=ambiente; c=contato(a); p=pedido(c)
    r=disparos.enviar(p, a[1], a[0])
    assert r["estado"] == "enviado" and r["numero"] == c["numero"]
    assert a[3] == [(p.texto, "whatsapp")] and len(a[4]) == 1
    assert disparos.enviar(p, a[1], a[0]) == r
    assert len(a[3]) == len(a[4]) == 1
    registro=a[0].query(EnvioAudio).one()
    assert registro.texto_hash and not hasattr(registro, "texto")
    assert disparos.consultar(p.pedido_id, a[1], a[0])["estado"] == "enviado"
    with pytest.raises(HTTPException) as erro: disparos.consultar(p.pedido_id, a[2], a[0])
    assert erro.value.status_code == 404
    with pytest.raises(HTTPException) as erro: disparos.enviar(pedido(c, texto="Outro texto", id=p.pedido_id), a[1], a[0])
    assert erro.value.status_code == 409


def test_pedido_em_andamento_nao_dispara_segunda_vez(ambiente, monkeypatch):
    a=ambiente; c=contato(a); p=pedido(c)
    original=fala.sintetizar
    def gerar(texto, canal):
        with a[5]() as db:
            assert disparos.enviar(p, a[1], db)["estado"] == "gerando"
        return original(texto, canal)
    monkeypatch.setattr(fala, "sintetizar", gerar)
    assert disparos.enviar(p, a[1], a[0])["estado"] == "enviado"
    assert len(a[3]) == len(a[4]) == 1


@pytest.mark.parametrize("tipo", ["ausente", "base64", "mime", "exception"])
def test_falha_sintese_nao_envia(ambiente, monkeypatch, tipo):
    a=ambiente; c=contato(a)
    def gerar(*args):
        if tipo == "exception": raise RuntimeError("falha")
        return None if tipo == "ausente" else {"base64": "invalido!" if tipo == "base64" else "SUQz", "mime": "text/html" if tipo == "mime" else "audio/mpeg"}
    monkeypatch.setattr(fala, "sintetizar", gerar)
    p=pedido(c)
    assert disparos.enviar(p, a[1], a[0])["estado"] == "falhou"
    assert disparos.enviar(p, a[1], a[0])["estado"] == "falhou"
    assert a[4] == []


def test_desconectado_nao_gasta_voz(ambiente, monkeypatch):
    a=ambiente; c=contato(a)
    monkeypatch.setattr(evolution, "estado_simples", lambda: "close")
    with pytest.raises(HTTPException) as erro: disparos.enviar(pedido(c), a[1], a[0])
    assert erro.value.status_code == 409 and a[3] == a[4] == []


def test_contato_de_outra_conta_nao_envia(ambiente):
    a=ambiente; c=contato(a)
    with pytest.raises(HTTPException): disparos.enviar(pedido(c), a[2], a[0])
    assert a[3] == a[4] == []


def test_falha_no_envio_e_resultado_incerto_nao_repetem(ambiente, monkeypatch):
    a=ambiente; c=contato(a); chamadas=[]
    def enviar(*args): chamadas.append(args); raise RuntimeError("conexão caiu")
    monkeypatch.setattr(evolution, "enviar_audio_confirmado", enviar)
    p=pedido(c)
    assert disparos.enviar(p, a[1], a[0])["estado"] == "incerto"
    assert disparos.consultar(p.pedido_id, a[1], a[0])["estado"] == "incerto"
    assert disparos.enviar(p, a[1], a[0])["estado"] == "incerto"
    assert len(chamadas) == 1


def test_pendente_antigo_fica_incerto(ambiente):
    a=ambiente; c=contato(a); p=pedido(c)
    disparos.enviar(p, a[1], a[0])
    r=a[0].query(EnvioAudio).one(); r.estado="enviando"; r.atualizado_em=datetime.utcnow()-timedelta(minutes=16); a[0].commit()
    assert disparos.consultar(p.pedido_id, a[1], a[0])["estado"] == "incerto"
    assert len(a[4]) == 1


@pytest.mark.parametrize("status,dados,estado", [(201,{"key":{"id":"abc"}},"enviado"),(200,{},"incerto"),(0,{},"incerto"),(503,{},"incerto"),(400,{},"falhou"),(401,{},"falhou")])
def test_transporte_confirma_so_com_id(monkeypatch, status, dados, estado):
    chamadas=[]
    def chamar(*args, **kwargs): chamadas.append((args, kwargs)); return status,dados
    monkeypatch.setattr(evolution, "_chamar", chamar)
    assert evolution.enviar_audio_confirmado("5511999999999", "SUQz")["estado"] == estado
    assert len(chamadas)==1
    assert chamadas[0][0][2] == {"number":"5511999999999","audio":"SUQz","encoding":True,"delay":200}


def test_todas_rotas_restritas_ao_admin():
    for route in disparos.router.routes:
        assert conta_admin in [d.call for d in route.dependant.dependencies]
    with pytest.raises(HTTPException) as erro: conta_admin(Conta(admin=False))
    assert erro.value.status_code == 403
    with pytest.raises(ValidationError): disparos.PedidoEnvio(pedido_id=uuid4(), contato_id=1, texto="x"*1201)
    with pytest.raises(ValidationError): disparos.PedidoEnvio(pedido_id=uuid4(), contato_id=1, texto="x", numero="outro")


def test_rotas_registradas_e_tabelas(ambiente):
    from main import app
    assert "/api/admin/audios/enviar" in {r.path for r in app.routes}
    from sqlalchemy import inspect
    assert {"contatos_audio","envios_audio"} <= set(inspect(ambiente[0].bind).get_table_names())


def test_limite_de_novos_pedidos(ambiente):
    a=ambiente; c=contato(a)
    for _ in range(6): assert disparos.enviar(pedido(c), a[1], a[0])["estado"] == "enviado"
    with pytest.raises(HTTPException) as erro: disparos.enviar(pedido(c), a[1], a[0])
    assert erro.value.status_code == 429 and len(a[3]) == len(a[4]) == 6
