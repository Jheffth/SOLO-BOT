# -*- coding: utf-8 -*-
"""
Rotas da ponte da TV (ponte_tv/ponte.py, no notebook de casa).

A ponte só faz conexões de saída: busca o próximo comando (long-poll) e devolve o
resultado. Tudo exige `Authorization: Bearer <PONTE_TV_TOKEN>`.
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

import config
from nucleo import tv_lg
from seguranca import iguais

log = logging.getLogger("solobot.ponte_tv")
router = APIRouter(prefix="/api/ponte-tv", tags=["ponte-tv"])

ESPERA_MAX = 25   # abaixo do timeout comum de proxies (Caddy aguenta bem mais)


def _ponte(authorization: str = Header("")) -> None:
    if not config.PONTE_TV_TOKEN:
        raise HTTPException(404)
    esquema, _, token = authorization.partition(" ")
    if esquema.lower() != "bearer" or not iguais(token.strip(), config.PONTE_TV_TOKEN):
        log.warning("ponte da TV: token recusado")
        raise HTTPException(401, "token inválido")


@router.get("/proximo", dependencies=[Depends(_ponte)])
async def proximo(espera: int = 25, tvs: Optional[str] = None):
    lista = [t.strip().lower() for t in (tvs or "").split(",") if t.strip()][:10] if tvs is not None else None
    cmd = await asyncio.to_thread(tv_lg.FILA.proximo, max(0, min(espera, ESPERA_MAX)), lista)
    if not cmd:
        return Response(status_code=204)
    log.info("ponte da TV: entregue #%s %s tv=%s", cmd["id"], cmd["acao"], cmd["tv"] or "padrão")
    return cmd


class Resultado(BaseModel):
    id: int
    ok: bool
    mensagem: str = Field("", max_length=500)


@router.post("/resultado", dependencies=[Depends(_ponte)])
def resultado(r: Resultado):
    aceito = tv_lg.FILA.resultado(r.id, r.ok, r.mensagem)
    log.info("ponte da TV: resultado #%s ok=%s aceito=%s", r.id, r.ok, aceito)
    return {"aceito": aceito}
