# -*- coding: utf-8 -*-
"""
O vínculo de DENTRO para fora (authorization code).

O sistema gera um código de uso único amarrado ao usuário logado nele e
manda o navegador para /conectar?app=…&codigo=…. Aqui, com a Conta Solo
aberta, a pessoa confirma e o código é trocado SERVIDOR A SERVIDOR.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import Atividade, Conta, VinculoSistema, get_db
from nucleo import modulos
from seguranca import conta_atual

router = APIRouter(prefix="/api/conectar", tags=["conectar"])


@router.get("/{app}")
def info(app: str):
    """O que a tela de consentimento mostra. Não toca no código."""
    mod = modulos.por_chave(app)
    if not mod:
        raise HTTPException(404, "Sistema desconhecido.")
    return mod.publico()


class Pedido(BaseModel):
    app: str
    codigo: str = Field(min_length=6, max_length=128)


@router.post("")
def conectar(p: Pedido, conta: Conta = Depends(conta_atual), db: Session = Depends(get_db)):
    mod = modulos.por_chave(p.app)
    if not mod:
        raise HTTPException(404, "Sistema desconhecido.")
    try:
        dados = modulos.chamar(mod, "resgatar", {"codigo": p.codigo.strip()})
    except modulos.ErroModulo as e:
        raise HTTPException(400, str(e))

    usuario_id = str(dados.get("usuario_id") or "").strip()
    if not usuario_id:
        raise HTTPException(502, f"{mod.nome} não disse quem é o usuário.")
    nome_remoto = (dados.get("nome") or "")[:120]

    # Um usuário do sistema pertence a UMA Conta Solo; uma conta tem UM vínculo por sistema.
    anterior = db.query(VinculoSistema).filter(VinculoSistema.app == mod.chave,
                                               VinculoSistema.usuario_id == usuario_id).first()
    trocou_de_conta = bool(anterior and anterior.conta_id != conta.id)
    if anterior:
        db.delete(anterior)
    db.query(VinculoSistema).filter(VinculoSistema.conta_id == conta.id,
                                    VinculoSistema.app == mod.chave).delete()
    db.flush()
    db.add(VinculoSistema(conta_id=conta.id, app=mod.chave, usuario_id=usuario_id, nome_remoto=nome_remoto))
    db.add(Atividade(conta_id=conta.id, app=mod.chave, tipo="vinculo", resumo=f"{mod.nome} conectado"))
    db.commit()
    # O retorno é SEMPRE o painel configurado do sistema — nunca uma URL vinda do pedido.
    return {"ok": True, "app": mod.publico(), "nome_remoto": nome_remoto,
            "retorno": mod.painel or None, "trocou_de_conta": trocou_de_conta}
