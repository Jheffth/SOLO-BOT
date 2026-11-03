# -*- coding: utf-8 -*-
"""
Sistema → Solo Bot. Por aqui chegam os avisos (manhã do Rotinas, fatura do Finances).

Só na rede interna, e só com o token do próprio sistema. O token diz QUEM
está mandando: um sistema não consegue avisar em nome de outro.
"""
from datetime import datetime
from typing import List, Optional, Literal

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
    falado: Optional[str] = Field(default=None, max_length=1200)   # roteiro para ouvido, se o sistema tiver
    voz: Optional[bool] = None                                     # o sistema pede que este aviso seja falado
    valido_ate: Optional[datetime] = None                          # ISO com fuso; depois disso, não entregar
    formato: Optional[Literal["texto", "audio", "ambos"]] = None
    referencia: Optional[str] = Field(default=None,min_length=1,max_length=160)
    tom: Optional[str] = Field(default=None, max_length=20)        # "sussurro"; desconhecido é ignorado


@router.post("/enviar")
def enviar(a: Aviso, mod: modulos.Modulo = Depends(_modulo), db: Session = Depends(get_db)):
    """Entrega agora, ou guarda até o fim do horário de silêncio da pessoa."""
    from nucleo import avisos
    return avisos.receber(db, mod, a.usuario_id, a.texto, a.opcoes, a.falado, a.voz, a.valido_ate, a.tom, a.formato, a.referencia)


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


@router.get("/saude")
def saude_interna(mod: modulos.Modulo = Depends(_modulo)):
    """Verificação autenticada da integração."""
    return {"status": "ok", "app": mod.chave, "nome": mod.nome}


@router.get("/vozes")
def vozes_internas(mod: modulos.Modulo = Depends(_modulo)):
    """Consulta interna autenticada das vozes disponíveis em todos os provedores."""
    from nucleo import fala
    return {"vozes": fala.catalogo_todas_vozes()}


@router.get("/bella/memorias")
def memorias_bella(x_solo_contexto: str = Header(""), mod: modulos.Modulo = Depends(_modulo),
                  db: Session = Depends(get_db)):
    """Cópia das memórias do próprio Arquiteto para seu arquivo privado no Models."""
    import time
    import config
    from jose import jwt, JWTError
    from database import Conta, BellaLore, BellaMemoria, BellaArquivo, BellaDia
    if mod.chave != "models" or not config.MODELS_CONTEXTO_KEY:
        raise HTTPException(403, "Contexto de memória não autorizado.")
    try:
        contexto = jwt.decode(x_solo_contexto, config.MODELS_CONTEXTO_KEY, algorithms=["HS256"],
                              issuer="solo-models", audience="solo-bot-memorias")
        for chave in ("sub", "modelo_id", "iat", "exp"):
            if chave not in contexto:
                raise ValueError()
        if not isinstance(contexto['modelo_id'], str) or not contexto['modelo_id']:
            raise ValueError()
        if not all(type(contexto[k]) in (int, float) for k in ('iat', 'exp')):
            raise ValueError()
        if not 0 < contexto['exp'] - contexto['iat'] <= 120 or contexto['iat'] > time.time() + 5:
            raise ValueError()
        import re
        m = re.fullmatch(r"solo-bot:conta:([1-9][0-9]*)", contexto['sub'])
        conta = db.get(Conta, int(m[1])) if m else None
        if not conta or not conta.admin:
            raise ValueError()
    except (JWTError, ValueError, TypeError, KeyError):
        raise HTTPException(403, "Contexto de memória não autorizado.") from None
    tabelas = {}
    # A cópia inclui somente registros da conta autorizada; não consulta outros donos.
    for tipo, classe in [('bella_lores', BellaLore), ('bella_memorias', BellaMemoria),
                         ('bella_arquivo', BellaArquivo), ('bella_dias', BellaDia)]:
        linhas = db.query(classe).filter(classe.conta_id == conta.id).order_by(classe.id).all()
        tabelas[tipo] = [{col.name: (v.isoformat() if isinstance(v, datetime) else v)
                         for col in classe.__table__.columns for v in [getattr(linha, col.name)]}
                        for linha in linhas]
    from nucleo.models_memorias import vinculos
    return {"formato": 1, "dono_id": contexto['sub'], "modelo_id": contexto['modelo_id'],
            "tabelas": tabelas, "vinculos": vinculos(db, conta.id, contexto['modelo_id'])}
