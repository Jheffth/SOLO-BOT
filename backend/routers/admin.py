# -*- coding: utf-8 -*-
"""O painel do administrador: estado dos canais e dos sistemas."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
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
    ev = evolution.estado() if evolution.disponivel() else {}
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
                     "numero": config.WHATSAPP_NUMERO,
                     "estado": ((ev.get("instance") or {}).get("state")) or ULTIMO_QR["estado"],
                     "qr": ULTIMO_QR["base64"],
                     "contas": por_canal.get("whatsapp", 0)},
        "sistemas": [{**m.publico(), "url": m.url, "contas": por_app.get(m.chave, 0)}
                     for m in modulos.todos()],
    }


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
    evolution.configurar_webhook(url)
    r = evolution.conectar()
    if r.get("base64"):
        ULTIMO_QR["base64"] = r["base64"]
    return {"qr": ULTIMO_QR["base64"], "estado": (r.get("instance") or {}).get("state")}
