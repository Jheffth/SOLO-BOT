# -*- coding: utf-8 -*-
"""O painel do administrador: estado dos canais e dos sistemas."""
from datetime import datetime, timedelta

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
from canais import evolution, telegram
from database import Atividade, CanalVinculo, Conta, VinculoSistema, get_db
from nucleo import modulos
from routers.webhooks import ULTIMO_QR
from seguranca import conta_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/status")
def status(_: Conta = Depends(conta_admin), db: Session = Depends(get_db)):
    tg = telegram.info_webhook() if telegram.disponivel() else {}
    por_app = dict(db.query(VinculoSistema.app, func.count()).group_by(VinculoSistema.app).all())
    por_canal = dict(db.query(CanalVinculo.canal, func.count()).group_by(CanalVinculo.canal).all())
    return {
        "contas": db.query(func.count(Conta.id)).scalar(),
        "mensagens_24h": db.query(func.count(Atividade.id)).filter(
            Atividade.tipo == "comando",
            Atividade.criado_em >= datetime.utcnow() - timedelta(days=1)).scalar(),
        "telegram": {"configurado": telegram.disponivel() and bool(config.TELEGRAM_SECRET),
                     "usuario": config.TELEGRAM_BOT_USERNAME,
                     "webhook": (tg.get("result") or {}).get("url"),
                     "pendentes": (tg.get("result") or {}).get("pending_update_count"),
                     "ultimo_erro": (tg.get("result") or {}).get("last_error_message"),
                     "contas": por_canal.get("telegram", 0)},
        "whatsapp": {"configurado": evolution.disponivel() and bool(config.EVOLUTION_WEBHOOK_SECRET),
                     "numero": evolution.numero() if evolution.disponivel() else config.WHATSAPP_NUMERO,
                     "estado": evolution.estado_simples() if evolution.disponivel() else ULTIMO_QR["estado"],
                     "qr": ULTIMO_QR["base64"],
                     "contas": por_canal.get("whatsapp", 0)},
        "voz": {"transcricao": _voz_disponivel(), "fala": _fala_disponivel(),
                 "fala_erro": _fala_erro(),
                 "sistemas_com_audio": [m.chave for m in modulos.todos() if _recebe_audio(db, m.chave)]},
        "sistemas": [{**m.publico(), "url": m.url, "contas": por_app.get(m.chave, 0),
                      "manifesto": _resumo_manifesto(db, m.chave)}
                     for m in modulos.todos()],
    }


def _fala_disponivel() -> bool:
    from nucleo import fala
    return fala.disponivel()


def _fala_erro():
    from nucleo import fala
    return fala.ultimo_erro()


def _voz_disponivel() -> bool:
    from nucleo import voz
    return voz.disponivel()


def _recebe_audio(db: Session, app: str) -> bool:
    from nucleo import manifestos
    return manifestos.recebe_audio(db, app)


def _resumo_manifesto(db: Session, app: str):
    from nucleo import manifestos
    d = manifestos.de(db, app)
    if not d:
        return None
    return {"versao": d["versao"], "comandos": len(d.get("comandos", [])),
            "recebido_em": d["recebido_em"], "origem": d["origem"]}


@router.post("/manifestos/sincronizar")
def sincronizar_manifestos(_: Conta = Depends(conta_admin), db: Session = Depends(get_db)):
    from nucleo import manifestos
    return manifestos.buscar_todos(db)


@router.post("/telegram/webhook")
def ligar_telegram(_: Conta = Depends(conta_admin)):
    if not (telegram.disponivel() and config.TELEGRAM_SECRET):
        raise HTTPException(400, "Defina TELEGRAM_BOT_TOKEN e TELEGRAM_SECRET no .env.")
    r = telegram.configurar_webhook(f"{config.URL_PUBLICA}/api/telegram/webhook")
    telegram.configurar_comandos()
    return r


@router.post("/whatsapp/conectar")
def conectar_whatsapp(_: Conta = Depends(conta_admin)):
    if not (evolution.disponivel() and config.EVOLUTION_WEBHOOK_SECRET):
        raise HTTPException(400, "Defina EVOLUTION_API_KEY e EVOLUTION_WEBHOOK_SECRET no .env.")
    url = f"http://solo_bot:8000/api/whatsapp/webhook/{config.EVOLUTION_WEBHOOK_SECRET}"
    r = evolution.parear(url)
    if r.get("qr"):
        ULTIMO_QR["base64"] = r["qr"]
    ULTIMO_QR["estado"] = r.get("estado")
    if r.get("estado") == "open":
        ULTIMO_QR["base64"] = None
    return {**r, "qr": r.get("qr") or (ULTIMO_QR["base64"] if r.get("estado") != "open" else None)}


# ══════════════════════════════════════════════════════════════════════
# VOZ — saldo de créditos, vozes e modelo (ElevenLabs)
# ══════════════════════════════════════════════════════════════════════
@router.get("/voz")
def painel_voz(_: Conta = Depends(conta_admin)):
    from database import ler_config
    from nucleo import fala
    motores = fala.motores()
    if motores["atual"] == "voicestudio":
        from nucleo import voicestudio
        vozes = voicestudio.listar_vozes()
        atual = voicestudio.voz_id()
        return {"disponivel": fala.disponivel(), "motor": motores,
                "perfil_voicestudio": voicestudio.perfil(), "ultimo_erro": fala.ultimo_erro(),
                "vozes_voicestudio": vozes,
                "voz_voicestudio": {"id": atual, "nome": next((x["nome"] for x in vozes if x["voice_id"] == atual), None)}}
    if not fala.disponivel():
        return {"disponivel": False, "motor": motores}
    vozes = fala.listar_vozes()
    atual = fala.voz()
    nome = next((v["nome"] for v in vozes if v["voice_id"] == atual), None)
    origem = "env" if config.ELEVENLABS_VOICE_ID else "tela" if ler_config(fala.CHAVE_VOZ) else "automatica"
    sis = fala.voz_do_sistema()
    return {
        "disponivel": True,
        "motor": motores,
        "conta": {"atual": fala.conta_escolhida(),
                  "opcoes": [{"id": c["id"], "nome": c["nome"]} for c in fala.contas()]},
        "creditos": fala.creditos(),
        "vozes": vozes,
        "voz": {"id": atual, "nome": nome, "origem": origem},
        "voz_sistema": {"id": sis["id"], "origem": sis["origem"],
                        "nome": next((v["nome"] for v in vozes if v["voice_id"] == sis["id"]), None)},
        "modelo": {"atual": fala.modelo(), "fixo_no_env": bool(config.ELEVENLABS_MODEL), "opcoes": fala.MODELOS},
        "ultimo_erro": fala.ultimo_erro(),
    }


@router.get("/grok")
def painel_grok(_: Conta = Depends(conta_admin), atualizar: bool = False):
    """Saldo pré-pago da xAI (Grok), pela API de gerenciamento."""
    from nucleo import grok
    if not grok.saldo_disponivel():
        return {"disponivel": False}
    return {"disponivel": True, **grok.saldo(forcar=atualizar)}


class AjusteVoz(BaseModel):
    motor: Optional[str] = None
    conta: Optional[str] = None
    voice_id: Optional[str] = None
    modelo: Optional[str] = None
    voice_id_sistema: Optional[str] = None        # a voz dos sussurros; "" volta a usar a voz do bot
    voice_id_voicestudio: Optional[str] = None    # a voz (clone) usada no VoiceStudio


@router.put("/voz")
def ajustar_voz(dados: AjusteVoz, _: Conta = Depends(conta_admin), db: Session = Depends(get_db)):
    from database import gravar_config
    from nucleo import fala
    if dados.voice_id_voicestudio is not None:
        from nucleo import voicestudio
        if not voicestudio.disponivel_servidor():
            raise HTTPException(409, "Configure o VoiceStudio no servidor antes de escolher a voz.")
        if dados.voice_id_voicestudio not in {v["voice_id"] for v in voicestudio.listar_vozes(forcar=True)}:
            raise HTTPException(404, "Essa voz não está no VoiceStudio. Confira se ele está aberto e conectado.")
        gravar_config(db, voicestudio.CHAVE_VOZ, dados.voice_id_voicestudio)
        fala._estado["ultimo_erro"] = None
        return {"ok": True, "voz_voicestudio": voicestudio.voz_id()}
    if dados.motor is not None:
        if dados.motor not in fala.MOTORES:
            raise HTTPException(422, "Motor de voz desconhecido.")
        if any(x is not None for x in (dados.conta, dados.voice_id, dados.modelo, dados.voice_id_sistema)):
            raise HTTPException(422, "Troque o motor separadamente dos ajustes da ElevenLabs.")
        opcao = next(m for m in fala.motores()["opcoes"] if m["id"] == dados.motor)
        if not opcao["configurado"]:
            raise HTTPException(409, "Configure esse motor no servidor antes de selecioná-lo.")
        gravar_config(db, fala.CHAVE_MOTOR, dados.motor)
        fala._estado["ultimo_erro"] = None
        return {"ok": True, "motor": fala.motor_escolhido()}
    if dados.conta is not None:
        if dados.conta not in {"automatica"} | {c["id"] for c in fala.contas()}:
            raise HTTPException(422, "Conta de voz não configurada.")
        if any(x is not None for x in (dados.voice_id, dados.modelo, dados.voice_id_sistema)):
            raise HTTPException(422, "Troque a conta antes de escolher a voz ou o modelo.")
        if dados.conta != fala.conta_escolhida():
            # As vozes clonadas podem não existir na outra conta.
            from database import Configuracao
            for chave, valor in ((fala.CHAVE_CONTA, dados.conta), (fala.CHAVE_VOZ, None),
                                 (fala.CHAVE_VOZ_SISTEMA, None)):
                registro = db.get(Configuracao, chave) or Configuracao(chave=chave)
                registro.valor = valor
                db.add(registro)
            db.commit()
            fala._estado["voz"] = None
            fala._estado["ultimo_erro"] = None
        return {"ok": True, "conta": fala.conta_escolhida()}
    if dados.voice_id is not None:
        if config.ELEVENLABS_VOICE_ID:
            raise HTTPException(409, "A voz está fixada no .env (ELEVENLABS_VOICE_ID). Tire de lá para escolher aqui.")
        if dados.voice_id not in {v["voice_id"] for v in fala.listar_vozes()}:
            raise HTTPException(404, "Essa voz não está na conta da ElevenLabs.")
        gravar_config(db, fala.CHAVE_VOZ, dados.voice_id)
        fala._estado["voz"] = None
    if dados.modelo is not None:
        if config.ELEVENLABS_MODEL:
            raise HTTPException(409, "O modelo está fixado no .env (ELEVENLABS_MODEL). Tire de lá para escolher aqui.")
        if dados.modelo not in {m["id"] for m in fala.MODELOS}:
            raise HTTPException(422, "Modelo desconhecido.")
        gravar_config(db, fala.CHAVE_MODELO, dados.modelo)
    if dados.voice_id_sistema is not None:
        if dados.voice_id_sistema and dados.voice_id_sistema not in {v["voice_id"] for v in fala.listar_vozes()}:
            raise HTTPException(404, "Essa voz não está na conta da ElevenLabs.")
        gravar_config(db, fala.CHAVE_VOZ_SISTEMA, dados.voice_id_sistema or None)
    return {"ok": True, "voz": fala.voz(), "modelo": fala.modelo(), "voz_sistema": fala.voz_do_sistema()["id"]}


class Amostra(BaseModel):
    texto: str = Field(default="Oi! Eu sou o Solo Bot. É assim que eu vou falar com você.", max_length=200)
    voice_id: Optional[str] = None
    tom: Optional[str] = None


@router.post("/voz/amostra")
def amostra_voz(dados: Amostra, _: Conta = Depends(conta_admin)):
    """Gasta créditos: é a frase falada de verdade, no modelo atual."""
    import base64
    from fastapi.responses import Response
    from nucleo import fala
    r = (fala.sintetizar(dados.texto, "whatsapp", dados.voice_id, tom=dados.tom) if fala.tom_valido(dados.tom)
         else fala.sintetizar(dados.texto, "whatsapp", dados.voice_id))
    if not r:
        raise HTTPException(502, fala.ultimo_erro() or "O motor de voz não gerou a amostra.")
    return Response(base64.b64decode(r["base64"]), media_type="audio/mpeg")
