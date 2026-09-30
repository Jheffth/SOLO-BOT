# -*- coding: utf-8 -*-
"""O painel: canais, sistemas, atividade e perfil."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import config
from canais import evolution, telegram
from database import Atividade, CanalVinculo, Conta, VinculoSistema, get_db
from nucleo import manifestos, modulos, roteador
from routers.auth import conta_publica
from seguranca import conferir_senha, conta_atual, hash_senha

log = logging.getLogger("solobot.conta")
router = APIRouter(prefix="/api/conta", tags=["conta"])


def _canal_publico(c: Optional[CanalVinculo], canal: str) -> dict:
    disponivel = telegram.disponivel() if canal == "telegram" else evolution.disponivel()
    return {"canal": canal, "disponivel": disponivel, "conectado": bool(c),
            "rotulo": c.rotulo if c else None, "avisos": c.avisos if c else True,
            "desde": c.vinculado_em.isoformat() if c and c.vinculado_em else None}


@router.get("")
def painel(conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    canais = {c.canal: c for c in conta.canais}
    ligados = {v.app: v for v in conta.sistemas}
    sistemas = []
    for m in modulos.todos():
        v = ligados.get(m.chave)
        man = manifestos.de(db, m.chave) or {}
        sistemas.append({**m.publico(), "conectado": bool(v),
                         "comandos": [c for c in man.get("comandos", []) if not c.get("oculto")],
                         "exemplos": man.get("exemplos", []),
                         "nome_remoto": v.nome_remoto if v else None,
                         "desde": v.vinculado_em.isoformat() if v and v.vinculado_em else None})
    atividade = (db.query(Atividade).filter(Atividade.conta_id == conta.id)
                 .order_by(Atividade.criado_em.desc()).limit(12).all())
    return {
        "conta": conta_publica(conta),
        "canais": [_canal_publico(canais.get(c), c) for c in ("telegram", "whatsapp")],
        "sistemas": sistemas,
        "atividade": [{"tipo": a.tipo, "resumo": a.resumo, "app": a.app, "canal": a.canal,
                       "em": a.criado_em.isoformat()} for a in atividade],
    }


@router.post("/canais/{canal}/codigo")
def codigo_canal(canal: str, conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    if canal not in roteador.CANAIS:
        raise HTTPException(404, "Canal desconhecido.")
    if canal == "telegram" and not (telegram.disponivel() and config.TELEGRAM_BOT_USERNAME):
        raise HTTPException(503, "O Telegram ainda não foi configurado no servidor.")
    if canal == "whatsapp":
        if not evolution.disponivel():
            raise HTTPException(503, "O WhatsApp ainda não foi configurado no servidor (falta EVOLUTION_API_KEY).")
        if not evolution.numero():
            raise HTTPException(503, "O número do bot ainda não está pareado: o administrador precisa ler o QR "
                                     "em Administração → WhatsApp (ou definir WHATSAPP_NUMERO no .env).")
    c = roteador.gerar_codigo(db, conta, canal)
    if canal == "telegram":
        link, texto = telegram.link_start(c.codigo), None
    else:
        texto = f"SOLO {c.codigo}"
        link = evolution.link_wa(texto)
    return {"canal": canal, "codigo": c.codigo, "mensagem": texto, "link": link,
            "expira_em": c.expira_em.isoformat() + "Z"}


class AjusteCanal(BaseModel):
    avisos: bool


@router.patch("/canais/{canal}")
def ajustar_canal(canal: str, dados: AjusteCanal, conta: Conta = Depends(conta_atual),
                  db: Session = Depends(get_db)):
    c = db.query(CanalVinculo).filter(CanalVinculo.conta_id == conta.id, CanalVinculo.canal == canal).first()
    if not c:
        raise HTTPException(404, "Canal não conectado.")
    c.avisos = dados.avisos
    db.commit()
    return _canal_publico(c, canal)


@router.delete("/canais/{canal}")
def desconectar_canal(canal: str, conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    n = db.query(CanalVinculo).filter(CanalVinculo.conta_id == conta.id, CanalVinculo.canal == canal).delete()
    if n:
        db.add(Atividade(conta_id=conta.id, canal=canal, tipo="canal", resumo=f"{canal.capitalize()} desconectado"))
    db.commit()
    return {"ok": True}


@router.delete("/sistemas/{app}")
def desconectar_sistema(app: str, conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    v = db.query(VinculoSistema).filter(VinculoSistema.conta_id == conta.id, VinculoSistema.app == app).first()
    if not v:
        raise HTTPException(404, "Sistema não conectado.")
    mod = modulos.por_chave(app)
    usuario_id = v.usuario_id
    db.delete(v)
    db.add(Atividade(conta_id=conta.id, app=app, tipo="vinculo",
                     resumo=f"{mod.nome if mod else app} desconectado"))
    db.commit()
    if mod:
        try:  # avisar é cortesia: o vínculo já caiu aqui, que é o que importa
            modulos.chamar(mod, "desvinculado", {"usuario_id": usuario_id})
        except modulos.ErroModulo:
            log.warning("Não consegui avisar %s do desvínculo", app)
    return {"ok": True}


class Perfil(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=2, max_length=100)
    voz: Optional[str] = None           # audio | sempre | nunca


@router.patch("")
def perfil(dados: Perfil, conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    if dados.nome is not None:
        conta.nome = dados.nome.strip()
    if dados.voz is not None:
        if dados.voz not in ("audio", "sempre", "nunca"):
            raise HTTPException(422, "Voz: audio, sempre ou nunca.")
        conta.voz = dados.voz
    db.commit()
    return conta_publica(conta)


class TrocaSenha(BaseModel):
    atual: str
    nova: str = Field(min_length=8, max_length=128)


@router.post("/senha")
def trocar_senha(dados: TrocaSenha, conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    if not conferir_senha(dados.atual, conta.senha_hash):
        raise HTTPException(400, "A senha atual não confere.")
    conta.senha_hash = hash_senha(dados.nova)
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════
# AVISOS — canais, horário de silêncio e voz (ver nucleo/avisos.py)
# ══════════════════════════════════════════════════════════════════════
def _avisos_publico(db: Session, conta: Conta) -> dict:
    from database import AvisoPendente
    from nucleo import avisos
    canais = {c.canal: c for c in conta.canais}
    fim = avisos.fim_do_silencio(conta)
    return {
        "canais": [{"canal": c, "conectado": c in canais, "avisos": canais[c].avisos if c in canais else False}
                   for c in ("telegram", "whatsapp")],
        "silencio": {"ativo": bool(avisos.silencio(conta)), "de": conta.avisos_silencio_de or "22:00",
                     "ate": conta.avisos_silencio_ate or "07:00", "agora": bool(fim),
                     "termina_as": fim.strftime("%H:%M") if fim else None},
        "voz": conta.avisos_voz if conta.avisos_voz in avisos.VOZ_AVISOS else "sistema",
        "na_fila": db.query(AvisoPendente).filter(AvisoPendente.conta_id == conta.id).count(),
    }


@router.get("/avisos")
def ver_avisos(conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    return _avisos_publico(db, conta)


class AjusteAvisos(BaseModel):
    silencio: Optional[bool] = None
    de: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    ate: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    voz: Optional[str] = None


@router.patch("/avisos")
def ajustar_avisos(dados: AjusteAvisos, conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    from nucleo import avisos
    de = dados.de or conta.avisos_silencio_de or "22:00"
    ate = dados.ate or conta.avisos_silencio_ate or "07:00"
    ligar = dados.silencio if dados.silencio is not None else bool(avisos.silencio(conta))
    if ligar and de == ate:
        raise HTTPException(422, "O início e o fim do silêncio não podem ser iguais.")
    conta.avisos_silencio_de, conta.avisos_silencio_ate = (de, ate) if ligar else (None, None)
    if dados.voz is not None:
        if dados.voz not in avisos.VOZ_AVISOS:
            raise HTTPException(422, "Voz dos avisos: sistema, sempre ou nunca.")
        conta.avisos_voz = dados.voz
    db.commit()
    return _avisos_publico(db, conta)
