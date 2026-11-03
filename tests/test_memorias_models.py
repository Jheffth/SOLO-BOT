"""Exportação privada de memória: proprietário, serviço e assinatura são obrigatórios."""
import time
from jose import jwt
import config
import database
from nucleo import modulos


def test_exportacao_so_do_proprio_arquiteto(cliente, monkeypatch):
    antigos = list(config.MODULOS)
    modulos.recarregar(antigos + [{'chave':'models','nome':'Models','url':'http://models','token':'models-teste'}])
    monkeypatch.setattr(config, 'MODELS_CONTEXTO_KEY', 'contexto-exclusivo-teste-' * 3)
    try:
        db = database.SessionLocal()
        db.add_all([database.Conta(id=40,nome='Autor',usuario='autor',senha_hash='teste',admin=True),
                    database.Conta(id=41,nome='Outro',usuario='outro',senha_hash='teste',admin=False)])
        db.commit()
        db.add_all([database.BellaLore(conta_id=40,nome='Título',texto='[Permanente] TEXTO DO DONO'),
                    database.BellaMemoria(conta_id=41,texto='SEGREDO DE OUTRO')]);db.commit();db.close()
        agora=int(time.time())
        claims={'sub':'solo-bot:conta:40','modelo_id':'bella-id','iat':agora,'exp':agora+90,
                'iss':'solo-models','aud':'solo-bot-memorias'}
        def chamar(dados, chave=None):
            return cliente.get('/interno/bella/memorias', headers={'X-Solo-Token':'models-teste',
                'X-Solo-Contexto':jwt.encode(dados,chave or config.MODELS_CONTEXTO_KEY,algorithm='HS256')})
        assert cliente.get('/interno/bella/memorias',headers={'X-Solo-Token':'models-teste'}).status_code==403
        r=chamar(claims);assert r.status_code==200
        assert 'TEXTO DO DONO' in r.text and 'SEGREDO DE OUTRO' not in r.text
        assert chamar({**claims,'sub':'solo-bot:conta:41'}).status_code==403
        assert chamar({**claims,'exp':agora+121}).status_code==403
        assert chamar(claims,'outra-chave').status_code==403
    finally:
        modulos.recarregar(antigos)
