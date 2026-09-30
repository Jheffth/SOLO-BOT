# -*- coding: utf-8 -*-
"""
Sistema → Solo Bot. Por aqui chegam os avisos (manhã do Rotinas, fatura do Finances).

Só na rede interna, e só com o token do próprio sistema. O token diz QUEM
está mandando: um sistema não consegue avisar em nome de outro.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from canais import entrega
from database import get_db
from nucleo import modulos, roteador

router = APIRouter(prefix="/interno", tags=["interno"])


def _modulo(x_solo_token: str = Header("")) -> modulos.Modulo:
    mod = modulos.por_token(x_solo_token)
    if not mod:
        raise HTTPException(403, "token de serviço inválido")
    return mod


class Aviso(BaseModel):
    usuario_id: str
    texto: str = Field(min_length=1, max_length=3800)
    opcoes: Optional[List[dict]] = None


@router.post("/enviar")
def enviar(a: Aviso, mod: modulos.Modulo = Depends(_modulo), db: Session = Depends(get_db)):
    destinos = roteador.aviso(db, mod, a.usuario_id, a.texto, a.opcoes)
    for canal, origem, resposta in destinos:
        entrega.entregar(db, canal, origem, resposta)
    return {"entregues": len(destinos), "vinculado": bool(destinos) or None}


@router.post("/manifesto")
def receber_manifesto(corpo: dict, mod: modulos.Modulo = Depends(_modulo), db: Session = Depends(get_db)):
    """O sistema avisa, ao subir, quais comandos tem. Ver nucleo/manifestos.py."""
    from nucleo import manifestos
    try:
        r = manifestos.guardar(db, mod, corpo, "empurrado")
    except manifestos.ManifestoInvalido as e:
        raise HTTPException(422, f"manifesto inválido: {e}")
    return {"ok": True, **r}


@router.get("/vinculo/{usuario_id}")
def vinculo(usuario_id: str, mod: modulos.Modulo = Depends(_modulo), db: Session = Depends(get_db)):
    """Para a aba Bots do sistema mostrar 'conectado ao Solo Bot como fulano'."""
    from database import VinculoSistema
    v = db.query(VinculoSistema).filter(VinculoSistema.app == mod.chave,
                                        VinculoSistema.usuario_id == str(usuario_id)).first()
    if not v:
        return {"conectado": False}
    return {"conectado": True, "conta": v.conta.nome, "email": v.conta.email or v.conta.usuario,
            "canais": [c.canal for c in v.conta.canais]}
