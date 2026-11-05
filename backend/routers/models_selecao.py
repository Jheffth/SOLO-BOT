"""O Models seleciona; o Bot aplica à própria conta nos canais e no aplicativo."""
from collections import defaultdict
from threading import RLock
import hashlib
import json
import re
from fastapi import APIRouter,Depends,HTTPException,Request
from jose import jwt,JWTError
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy.orm import Session
import config
from database import Conta,get_db
from nucleo import models,models_cena,modulos
from seguranca import iguais
from routers.conta import _modo_bella

router=APIRouter(tags=['seleção pelo Models'])
_travas=defaultdict(RLock)


class Alternar(BaseModel):
    model_config=ConfigDict(extra='forbid')
    modelo_id:str=Field(min_length=1,max_length=36,pattern=r'^[A-Za-z0-9-]+$')
    ligada:bool
    revisao:str=Field(pattern=r'^[a-f0-9]{64}$')


def conta_portal(request:Request,db:Session=Depends(get_db)):
    mod=modulos.por_chave('models')
    if not mod or not mod.token or not iguais(request.headers.get('x-solo-token',''),mod.token) or not config.MODELS_CONTEXTO_KEY:
        raise HTTPException(403,'Serviço não autorizado.')
    try:
        d=jwt.decode(request.headers.get('x-solo-contexto',''),config.MODELS_CONTEXTO_KEY,algorithms=['HS256'],
            issuer='solo-models',audience='solo-bot-selecao',options={'require_exp':True,'require_iat':True})
        dono=d.get('dono_id','')
        if not isinstance(dono,str) or not re.fullmatch(r'solo-bot:conta:[1-9][0-9]*',dono):raise ValueError()
        if d.get('metodo')!=request.method or d.get('rota')!=request.url.path:raise ValueError()
        if d['exp']-d['iat']>90:raise ValueError()
        conta=db.get(Conta,int(dono.rsplit(':',1)[1]))
        if not conta or not conta.ativo:raise ValueError()
        return conta
    except (JWTError,ValueError,TypeError,KeyError):raise HTTPException(403,'Acesso à seleção não autorizado.') from None


def estado(conta):
    ident=models.selecionado(conta.id);presentes=[ident] if ident else []
    if ident and conta.admin:
        # Uma falha ao ler a cena não pode aparecer como uma seleção vazia.
        cena=models._requisicao('GET',models._rota(conta,ident)+'/cena',conta,ident)
        if not isinstance(cena,dict) or not isinstance(cena.get('ativa'),bool):
            raise models.ErroModels('Não foi possível consultar a conversa atual. Sua escolha foi preservada.')
        if cena['ativa']:
            linhas=cena.get('presentes')
            if not isinstance(linhas,list) or any(not isinstance(p,dict) or not isinstance(p.get('modelo_id'),str) for p in linhas):
                raise models.ErroModels('Não foi possível consultar as participantes da conversa.')
            presentes=[p['modelo_id'] for p in linhas]
            if ident not in presentes or not 1<=len(presentes)<=3 or len(set(presentes))!=len(presentes):
                raise models.ErroModels('A conversa atual precisa ser atualizada. Tente novamente.')
    revisao=hashlib.sha256(json.dumps([ident,presentes],separators=(',',':')).encode()).hexdigest()
    return {'modelo_id':ident,'presentes':presentes,'maximo':3 if conta.admin else 1,
            'origem':'models' if ident else 'legado','revisao':revisao}


@router.get('/interno/models/portal/selecao')
def ler(conta:Conta=Depends(conta_portal)):
    try:return estado(conta)
    except models.ErroModels as e:raise HTTPException(503,str(e)) from None


@router.put('/interno/models/portal/selecao')
def alternar(p:Alternar,conta:Conta=Depends(conta_portal),db:Session=Depends(get_db)):
    with _travas[conta.id]:
        try:
            atual=estado(conta)
            if atual['revisao']!=p.revisao:raise HTTPException(409,'Sua seleção mudou em outra tela. Confira as chaves atualizadas e tente novamente.')
            ids=list(atual['presentes'])
            if p.ligada and p.modelo_id not in ids:
                if not conta.admin:ids=[]
                ids.append(p.modelo_id)
            elif not p.ligada:ids=[i for i in ids if i!=p.modelo_id]
            if len(ids)>atual['maximo']:raise HTTPException(422,'Você pode manter até 3 modelos ligadas. Desligue uma antes de adicionar outra.')
            if ids==atual['presentes']:return atual
            if ids:models_cena.definir_presentes(db,conta,ids)
            else:
                if conta.admin and atual['modelo_id']:
                    models._requisicao('POST',models._rota(conta,atual['modelo_id'])+'/cena/encerrar',conta,atual['modelo_id'],{})
                models.escolher(db,conta,None)
            _modo_bella(db,conta)
            return estado(conta)
        except models.ErroModels as e:raise HTTPException(503,str(e)) from None
