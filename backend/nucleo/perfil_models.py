"""A identidade pessoal do Arquiteto no Models é a referência central da sua bio."""
import json
import re
from datetime import datetime
from database import SessionLocal,Conta,Configuracao
from nucleo import models

def fonte(conta_id):
    db=SessionLocal()
    try:
        cfg=db.get(Configuracao,f'perfil_models:{int(conta_id)}')
        if not cfg or not cfg.valor:return None
        conta=db.get(Conta,int(conta_id))
        if not conta or not conta.admin:return None
        return Perfil(conta,json.loads(cfg.valor)['modelo_id'])
    finally:db.close()

class Perfil:
    def __init__(self,conta,modelo_id):self.conta,self.modelo_id=conta,modelo_id
    def obter(self):
        return models._requisicao('GET',models._rota(self.conta,self.modelo_id)+'/perfil-pessoa',self.conta,self.modelo_id)
    def listar(self):return self.obter()['bio']
    def salvar(self,linhas):
        p=self.obter()
        dados={k:p[k] for k in ('nome','nascimento','versao')};dados['bio']=linhas
        for linha in linhas:
            if re.match(r'^nome\s*:',linha,re.I):dados['nome']=linha.split(':',1)[1].strip()
            m=re.match(r'^(?:nascimento|data de nascimento)\s*:\s*(\d{1,2}/\d{1,2}/\d{4})',linha,re.I)
            if m:
                try:dados['nascimento']=datetime.strptime(m[1],'%d/%m/%Y').date().isoformat()
                except ValueError:pass
        return models._requisicao('PUT',models._rota(self.conta,self.modelo_id)+'/perfil-pessoa',self.conta,self.modelo_id,dados)
