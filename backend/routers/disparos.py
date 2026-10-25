"""Contatos e envio manual de áudio por administrador, com idempotência persistente."""
import base64
import hashlib
import re
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from canais import evolution
from database import Conta, ContatoAudio, EnvioAudio, get_db
from nucleo import fala
from seguranca import conta_admin

router = APIRouter(prefix="/api/admin/audios", tags=["envio-audio"])


class Contato(BaseModel):
    model_config = {"extra": "forbid"}
    nome: str = Field(min_length=1, max_length=80)
    numero: str = Field(min_length=8, max_length=35)


class PedidoEnvio(BaseModel):
    model_config = {"extra": "forbid"}
    pedido_id: UUID
    contato_id: int = Field(gt=0)
    texto: str = Field(min_length=1, max_length=1200)


def numero_valido(numero):
    if not re.fullmatch(r"[+0-9() .-]+", numero):
        raise HTTPException(422, "Informe somente o número com DDI e DDD, sem links ou grupos.")
    numero = re.sub(r"[+() .-]", "", numero)
    if not re.fullmatch(r"[1-9][0-9]{7,14}", numero):
        raise HTTPException(422, "Informe um número internacional com DDI e DDD, por exemplo +55 11 99999-9999.")
    return numero


def _contato(c):
    return {"id": c.id, "nome": c.nome, "numero": c.numero}


def _envio(e):
    return {"pedido_id": e.pedido_id, "nome": e.nome, "numero": e.numero, "estado": e.estado,
            "detalhe": e.detalhe, "criado_em": e.criado_em.isoformat(), "mensagem_id": e.mensagem_id}


@router.get("")
def painel(conta: Conta = Depends(conta_admin), db: Session = Depends(get_db)):
    contatos = db.query(ContatoAudio).filter_by(conta_id=conta.id).order_by(ContatoAudio.nome, ContatoAudio.id).all()
    envios = db.query(EnvioAudio).filter_by(conta_id=conta.id).order_by(EnvioAudio.id.desc()).limit(10).all()
    return {"contatos": [_contato(c) for c in contatos], "envios": [_envio(e) for e in envios],
            "whatsapp_configurado": evolution.disponivel(), "voz_configurada": fala.disponivel()}


@router.post("/contatos", status_code=201)
def adicionar(p: Contato, conta: Conta = Depends(conta_admin), db: Session = Depends(get_db)):
    nome = p.nome.strip()
    if not nome or any(ord(c) < 32 for c in nome):
        raise HTTPException(422, "Informe um nome para o contato.")
    if db.query(ContatoAudio).filter_by(conta_id=conta.id).count() >= 200:
        raise HTTPException(422, "O limite é de 200 contatos salvos.")
    c = ContatoAudio(conta_id=conta.id, nome=nome, numero=numero_valido(p.numero))
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Esse número já está salvo na sua lista.") from None
    db.refresh(c)
    return _contato(c)


@router.delete("/contatos/{contato_id}")
def remover(contato_id: int, conta: Conta = Depends(conta_admin), db: Session = Depends(get_db)):
    c = db.query(ContatoAudio).filter_by(id=contato_id, conta_id=conta.id).first()
    if not c:
        raise HTTPException(404, "Contato não encontrado.")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/envios/{pedido_id}")
def consultar(pedido_id: UUID, conta: Conta = Depends(conta_admin), db: Session = Depends(get_db)):
    e = db.query(EnvioAudio).filter_by(conta_id=conta.id, pedido_id=str(pedido_id)).first()
    if not e:
        raise HTTPException(404, "Este pedido não foi encontrado. Nenhum reenvio foi feito.")
    if e.estado in ("gerando", "enviando") and datetime.utcnow() - e.atualizado_em > timedelta(minutes=15):
        e.estado = "incerto"
        e.detalhe = "O processamento não terminou de forma confirmada. Confira a conversa no WhatsApp antes de enviar novamente."
        db.commit()
    return _envio(e)


@router.post("/enviar")
def enviar(p: PedidoEnvio, conta: Conta = Depends(conta_admin), db: Session = Depends(get_db)):
    texto = p.texto.strip()
    if not texto or any(ord(c) < 32 and c not in "\n\r\t" for c in texto):
        raise HTTPException(422, "Escreva a mensagem que deseja enviar.")
    digest = hashlib.sha256(texto.encode()).hexdigest()
    existente = db.query(EnvioAudio).filter_by(conta_id=conta.id, pedido_id=str(p.pedido_id)).first()
    if existente:
        if existente.contato_id != p.contato_id or existente.texto_hash != digest:
            raise HTTPException(409, "Este identificador já pertence a outra mensagem. Inicie uma nova mensagem.")
        return _envio(existente)
    c = db.query(ContatoAudio).filter_by(id=p.contato_id, conta_id=conta.id).first()
    if not c:
        raise HTTPException(404, "Selecione um contato da sua lista.")
    if not evolution.disponivel() or evolution.estado_simples() != "open":
        raise HTTPException(409, "Conecte o WhatsApp em Administração → Conexões antes de enviar.")
    if not fala.disponivel():
        raise HTTPException(409, "Configure o motor de voz antes de enviar.")
    recentes = db.query(EnvioAudio).filter(EnvioAudio.conta_id == conta.id,
                                         EnvioAudio.criado_em >= datetime.utcnow() - timedelta(minutes=1)).count()
    if recentes >= 6:
        raise HTTPException(429, "Aguarde um minuto antes de iniciar outro envio.")
    e = EnvioAudio(conta_id=conta.id, pedido_id=str(p.pedido_id), contato_id=c.id,
                   nome=c.nome, numero=c.numero, texto_hash=digest, estado="gerando")
    db.add(e)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        vencedor = db.query(EnvioAudio).filter_by(conta_id=conta.id, pedido_id=str(p.pedido_id)).first()
        if vencedor and vencedor.contato_id == p.contato_id and vencedor.texto_hash == digest:
            return _envio(vencedor)
        raise HTTPException(409, "Não foi possível registrar este pedido; nenhum envio foi iniciado por esta chamada.") from None
    try:
        audio = fala.sintetizar(texto, "whatsapp")
        if not audio or audio.get("mime") not in ("audio/mpeg", "audio/ogg", "audio/opus"):
            raise ValueError("áudio ausente")
        codigo = audio.get("base64")
        if not isinstance(codigo, str) or len(codigo) > 14 * 1024 * 1024:
            raise ValueError("áudio inválido")
        tamanho = len(base64.b64decode(codigo, validate=True))
        if not 0 < tamanho <= 10 * 1024 * 1024:
            raise ValueError("áudio inválido")
    except Exception:
        e.estado = "falhou"
        e.detalhe = "Não consegui gerar o áudio. Nenhuma mensagem foi enviada. Confira o motor de voz."
        db.commit()
        return _envio(e)
    e.estado = "enviando"
    e.detalhe = "Áudio gerado; enviando ao WhatsApp."
    db.commit()
    try:
        resultado = evolution.enviar_audio_confirmado(e.numero, codigo)
        e.estado = resultado["estado"]
        e.detalhe = resultado["detalhe"]
        e.mensagem_id = resultado.get("mensagem_id")
    except Exception:
        e.estado = "incerto"
        e.detalhe = "Não consegui confirmar o resultado. Confira a conversa no WhatsApp antes de criar outro pedido."
    db.commit()
    return _envio(e)
