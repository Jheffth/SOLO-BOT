# -*- coding: utf-8 -*-
"""Bella no Windows: chave própria, voz e sessão isoladas dos outros canais."""
import base64
import binascii
import hashlib
import io
import logging
import re
import secrets
import time
import wave
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import config
from database import Conta, get_db
from nucleo import comandos_locais, fala, render, roteador, saudacoes, voz
from routers.atalho import _numero_falado, _sem_marcacao
from seguranca import conta_atual

router = APIRouter(tags=["bella"])
log = logging.getLogger("solobot.bella")
_JANELAS = {}
_JANELAS_SAUDACAO = {}
_JANELAS_TRANSCRICAO = {}
_JANELAS_VOZ_LOCAL = {}
_JANELAS_COMANDOS = {}
CANAL_TRANSCRICAO = "bella-stt"  # canal do registro persistente tem no máximo 16 caracteres
RE_CHAMADA = re.compile(r"^(?:(?:ei|oi|ola|olá)\s+)?(?:bella|bela)\b[\s,:.!?—-]*", re.I)


def _hash(chave):
    return hashlib.sha256(chave.encode()).hexdigest()


def _autenticar(db, chave):
    if not re.fullmatch(r"bella_[A-Za-z0-9_-]{40,80}", chave):
        raise HTTPException(401, "Chave da Bella inválida. Gere outra no painel.")
    conta = db.query(Conta).filter(Conta.bella_hash == _hash(chave)).first()
    if not conta or not conta.ativo:
        raise HTTPException(401, "Chave da Bella inválida. Gere outra no painel.")
    return conta


@router.get("/api/conta/bella")
def estado(conta: Conta = Depends(conta_atual)):
    return {"ativo": bool(conta.bella_hash), "servidor": config.URL_PUBLICA,
            "criado_em": conta.bella_criado_em.isoformat() if conta.bella_criado_em else None,
            "usado_em": conta.bella_usado_em.isoformat() if conta.bella_usado_em else None}


@router.post("/api/conta/bella")
def gerar(conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    chave = "bella_" + secrets.token_urlsafe(32)
    conta.bella_hash, conta.bella_criado_em, conta.bella_usado_em = _hash(chave), datetime.utcnow(), None
    db.commit()
    roteador._registrar(db, conta, None, None, "conta", "Chave da Bella gerada")
    return {"chave": chave, "servidor": config.URL_PUBLICA}


@router.delete("/api/conta/bella")
def revogar(conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    conta.bella_hash = conta.bella_criado_em = conta.bella_usado_em = None
    db.commit()
    return {"ok": True}


class Pedido(BaseModel):
    pedido_id: UUID
    texto: Optional[str] = Field(default=None, max_length=2000)
    audio_base64: Optional[str] = Field(default=None, max_length=4 * 1024 * 1024)
    voz: bool = True
    via_audio: bool = False  # texto transcrito pelo canal Windows antes do roteamento


@router.get("/api/bella/saudacoes")
def catalogo_saudacoes(x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    conta = _autenticar(db, x_bella_chave)
    return saudacoes.catalogo(conta)


class PedidoSaudacao(BaseModel):
    id: int = Field(ge=0, lt=len(saudacoes.FRASES))


@router.post("/api/bella/saudacao")
def saudacao(p: PedidoSaudacao, x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    conta = _autenticar(db, x_bella_chave)
    agora = time.monotonic()
    janela = [t for t in _JANELAS_SAUDACAO.get(conta.id, []) if agora - t < 60]
    if len(janela) >= 30:
        raise HTTPException(429, "Muitas chamadas. Espere um minuto.")
    _JANELAS_SAUDACAO[conta.id] = janela + [agora]
    try:
        return saudacoes.preparar(conta, p.id)
    except Exception:
        log.warning("Bella: não consegui preparar a saudação em áudio")
        atual = saudacoes.catalogo(conta)
        texto = atual["saudacoes"][p.id]["texto"]
        return {"id": p.id, "perfil": atual["perfil"], "texto": texto, "falar": texto}


def _audio(dados):
    try:
        conteudo = base64.b64decode(dados, validate=True)
        if not conteudo or len(conteudo) > voz.MAX_BYTES:
            raise ValueError()
        with wave.open(io.BytesIO(conteudo), "rb") as wav:
            segundos = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
                raise ValueError()
            if not 0 < segundos <= 30 or len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                raise ValueError()
        return conteudo
    except (binascii.Error, ValueError, wave.Error, EOFError, ZeroDivisionError):
        raise HTTPException(422, "Áudio inválido. Use WAV mono de 16 kHz, até 30 segundos.") from None


def _limitar(conta, janelas):
    agora = time.monotonic()
    janela = [t for t in janelas.get(conta.id, []) if agora - t < 60]
    if len(janela) >= 30:
        raise HTTPException(429, "Muitos pedidos. Espere um minuto.")
    janelas[conta.id] = janela + [agora]


def _ouvir(conteudo):
    try:
        texto = voz.transcrever(conteudo, "audio/wav")
    except voz.SemVoz:
        raise HTTPException(503, "A transcrição não está configurada no servidor. Use o campo de texto.") from None
    except voz.FalhaVoz as erro:
        raise HTTPException(502, "Não consegui ouvir. " + str(erro)) from None
    if not texto:
        raise HTTPException(422, "Não ouvi uma fala. Pode tentar de novo.")
    return texto


class PedidoTranscricao(BaseModel):
    pedido_id: UUID
    audio_base64: str = Field(min_length=1, max_length=4 * 1024 * 1024)


@router.post("/api/bella/transcrever")
def transcrever(p: PedidoTranscricao, x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    """Só ouve: o aplicativo decide entre uma ação local e um pedido aos sistemas."""
    conta = _autenticar(db, x_bella_chave)
    conteudo = _audio(p.audio_base64)
    _limitar(conta, _JANELAS_TRANSCRICAO)
    if roteador.ja_processada(db, CANAL_TRANSCRICAO, f"{conta.id}:{p.pedido_id}"):
        raise HTTPException(409, "Este áudio já foi recebido. Grave um novo pedido.")
    conta.bella_usado_em = datetime.utcnow()
    db.commit()
    return {"pedido_id": str(p.pedido_id), "ouvido": _ouvir(conteudo)}


# Frases fixas: nenhum nome de arquivo, caminho ou resultado local vai ao servidor.
FALAS_ARQUIVOS = {
    "ajuda": "Posso buscar, listar e abrir arquivos, e criar pastas. Para mover, renomear ou excluir, peço sua confirmação.",
    "listagem": "Aqui estão os arquivos e pastas. Para abrir um item, diga o número.",
    "busca": "Encontrei estes resultados. Para abrir um deles, diga o número.",
    "escolha": "Qual destas opções você quer? Diga o número.",
    "site_aberto": "Abri o site no seu navegador padrão.",
    "pesquisa_aberta": "Abri os resultados da pesquisa no seu navegador padrão.",
    "pedir_assunto": "Qual assunto você quer pesquisar?",
    "confirmar_mover": "Confira na tela o item e a pasta de destino. Posso mover?",
    "confirmar_renomear": "Confira na tela o arquivo e o novo nome. Posso renomear?",
    "confirmar_excluir": "Confira na tela o item que irá para a Lixeira. Posso excluir?",
    "criada": "Criei a pasta.", "existe": "Essa pasta já existe.", "aberto": "Abri o item.",
    "movido": "Pronto, movi o item.", "renomeado": "Pronto, renomeei o item.",
    "excluido": "Concluí a exclusão pelo Windows.", "cancelado": "Pedido cancelado.",
    "erro": "Não consegui concluir esse comando. Confira a mensagem na tela.",
    "vazio": "Não encontrei itens nas pastas consultadas.",
    "expirou": "Essa escolha expirou. Faça o pedido de arquivo novamente.",
}


class ComandoLocal(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    frase: str = Field(min_length=3, max_length=200)
    tipo: Literal["pasta", "site", "google", "youtube", "maps"] = "pasta"


class PedidoComandoLocal(BaseModel):
    model_config = {"extra": "forbid"}
    texto: str = Field(min_length=1, max_length=2000)
    comandos: list[ComandoLocal] = Field(min_length=1, max_length=53)  # 50 cadastros + 3 pesquisas básicas


@router.post("/api/bella/interpretar-comando")
def interpretar_comando(p: PedidoComandoLocal, x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    """Só interpreta uma frase: nenhum comando é executado ou armazenado no hub."""
    conta = _autenticar(db, x_bella_chave)
    _limitar(conta, _JANELAS_COMANDOS)
    if len({c.id for c in p.comandos}) != len(p.comandos):
        raise HTTPException(422, "Comandos com identificadores repetidos.")
    return comandos_locais.interpretar(p.texto, [c.model_dump() for c in p.comandos])


class PedidoVozLocal(BaseModel):
    model_config = {"extra": "forbid"}
    codigo: str = Field(max_length=30)


@router.post("/api/bella/voz-local")
def voz_local(p: PedidoVozLocal, x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    conta = _autenticar(db, x_bella_chave)
    _limitar(conta, _JANELAS_VOZ_LOCAL)
    texto = FALAS_ARQUIVOS.get(p.codigo)
    if texto is None:
        raise HTTPException(422, "Resposta local não reconhecida.")
    saida = {"falar": texto}
    if fala.disponivel():
        try:
            audio = fala.sintetizar(texto, "whatsapp", guardar=True)
            if audio:
                saida.update(audio_base64=audio["base64"], mime=audio["mime"])
        except Exception:
            log.warning("Bella: resposta local usa voz do Windows")
    return saida


@router.post("/api/bella/mensagem")
def mensagem(p: Pedido, x_bella_chave: str = Header(""), db: Session = Depends(get_db)):
    conta = _autenticar(db, x_bella_chave)
    if bool(p.texto and p.texto.strip()) == bool(p.audio_base64):
        raise HTTPException(422, "Envie um pedido por texto ou áudio.")
    conteudo = _audio(p.audio_base64) if p.audio_base64 else None
    _limitar(conta, _JANELAS)
    if roteador.ja_processada(db, "bella", f"{conta.id}:{p.pedido_id}"):
        raise HTTPException(409, "Este pedido já foi recebido. Confira o resultado no sistema antes de repetir.")
    conta.bella_usado_em = datetime.utcnow()
    db.commit()
    texto = (p.texto or "").strip()
    if conteudo:
        texto = _ouvir(conteudo)
    ouvido = texto
    texto = RE_CHAMADA.sub("", texto).strip()
    origem = f"bella:{conta.id}"
    s = roteador.sessao_de(db, "bella", origem)
    if s.escolhas:
        texto = _numero_falado(texto) or texto
    if not texto:
        saudacao = saudacoes.preparar(conta, secrets.randbelow(len(saudacoes.FRASES)), com_audio=p.voz)
        return {"pedido_id": str(p.pedido_id), "ouvido": ouvido, "opcoes": [], **saudacao}
    r = roteador.atender_texto(db, "bella", origem, texto, rotulo="Bella", via_audio=bool(conteudo) or p.via_audio)
    itens, blocos = [], []
    for m in r.mensagens:
        corpo = m.get("texto") or ""
        novos = render.plano(m.get("opcoes"))
        if novos:
            corpo += "\n\n" + render.lista_whatsapp(novos, inicio=len(itens)).replace("_Responda com o número._", "")
            itens += novos
        blocos.append(corpo)
    roteador.guardar_escolhas(db, "bella", origem, itens)
    try:
        falado = fala.o_que_falar(r.mensagens)
    except Exception:
        log.warning("Bella: não consegui preparar o resumo falado")
        falado = None
    falado = falado or (fala.texto_falavel("\n".join(blocos), None) or "Pronto.")[:fala.MAX_CARACTERES]
    if itens:
        falado += " Para escolher, diga o número."
    saida = {"pedido_id": str(p.pedido_id), "ouvido": ouvido, "texto": _sem_marcacao("\n\n".join(blocos)),
             "falar": falado, "opcoes": [{"numero": i, "rotulo": a["rotulo"], "titulo": a["titulo"]}
                                           for i, a in enumerate(itens, 1)]}
    if p.voz and fala.disponivel():
        try:
            audio = fala.sintetizar(falado, "whatsapp")
            if audio:
                saida.update(audio_base64=audio["base64"], mime=audio["mime"])
        except Exception:
            log.warning("Bella: falha na resposta em áudio; texto preservado")
    return saida
