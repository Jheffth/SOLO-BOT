"""Entrada no perfil Models pela Conta Solo, com código de uso único e PKCE."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, delete
from sqlalchemy.orm import Session

import config
from database import Base, Conta, get_db
from nucleo import modulos
from seguranca import conta_opcional, iguais

router=APIRouter(tags=['perfil Models'])


class AcessoPortalModels(Base):
    __tablename__='models_portal_codigos'
    hash=Column(String(64),primary_key=True)
    conta_id=Column(Integer,ForeignKey('contas.id',ondelete='CASCADE'),nullable=False)
    desafio=Column(String(64),nullable=False)
    expira_em=Column(DateTime,nullable=False)


class Resgate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    codigo:str=Field(min_length=32,max_length=100)
    verificador:str=Field(min_length=32,max_length=100)


@router.get('/models/perfil')
def entrar(request:Request,estado:str='',desafio:str='',conta:Conta=Depends(conta_opcional),db:Session=Depends(get_db)):
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,100}',estado) or not re.fullmatch(r'[a-f0-9]{64}',desafio):
        raise HTTPException(422,'Abra seu perfil pelo Solo Models.')
    if not conta:
        return RedirectResponse('/entrar?'+urlencode({'proximo':str(request.url.path)+'?'+urlencode({'estado':estado,'desafio':desafio})}),303)
    mod=modulos.por_chave('models')
    if not mod or not mod.token:raise HTTPException(503,'O acesso ao Models ainda não está configurado.')
    destino=urlsplit(config.MODELS_PORTAL_URL)
    if destino.scheme not in ('https','http') or not destino.netloc or destino.username or destino.password:
        raise HTTPException(503,'Endereço do Models não configurado.')
    codigo=secrets.token_urlsafe(32)
    db.execute(delete(AcessoPortalModels).where(AcessoPortalModels.expira_em<datetime.utcnow()))
    db.add(AcessoPortalModels(hash=hashlib.sha256(codigo.encode()).hexdigest(),conta_id=conta.id,
        desafio=desafio,expira_em=datetime.utcnow()+timedelta(seconds=120)))
    db.commit()
    callback=f'{destino.scheme}://{destino.netloc}/conta-solo/retorno'
    return RedirectResponse(callback+'?'+urlencode({'codigo':codigo,'estado':estado}),303,
        headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


@router.post('/interno/models/portal/resgatar')
def resgatar(p:Resgate,request:Request,db:Session=Depends(get_db)):
    mod=modulos.por_chave('models')
    if not mod or not iguais(request.headers.get('x-solo-token',''),mod.token):
        raise HTTPException(403,'Serviço não autorizado.')
    chave=hashlib.sha256(p.codigo.encode()).hexdigest()
    row=db.query(AcessoPortalModels).filter_by(hash=chave).with_for_update().first()
    if not row or row.expira_em<datetime.utcnow() or not iguais(row.desafio,hashlib.sha256(p.verificador.encode()).hexdigest()):
        raise HTTPException(403,'Código inválido ou expirado.')
    conta=db.get(Conta,row.conta_id)
    if not conta or not conta.ativo:raise HTTPException(403,'Conta indisponível.')
    removidos=db.query(AcessoPortalModels).filter_by(hash=chave).delete()
    if removidos!=1:raise HTTPException(403,'Código já utilizado.')
    resultado={'dono_id':'solo-bot:conta:'+str(conta.id),'nome':conta.nome,'arquiteto':bool(conta.admin)}
    db.commit()
    return resultado
