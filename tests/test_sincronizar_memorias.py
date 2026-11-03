"""Sincronização explícita pelo ID; dados sintéticos, sem chamadas a provedores."""
from copy import deepcopy
from uuid import uuid4
import pytest
from database import SessionLocal, Conta, Configuracao, BellaMemoria, BellaLore, BellaArquivo, BellaTurno
from nucleo import models, models_memorias as M, roteador

IDENT = '3a97420f-ccce-4680-9d2b-dfc52b97e0d2'


def preparar():
    db = SessionLocal()
    c = db.get(Conta, 1); c.admin = True; db.commit(); db.close()
    return {'formato': 1, 'modelo_id': IDENT, 'dono_id': 'solo-bot:conta:1', 'registros': [
        {'id': str(uuid4()), 'tipo': tipo, 'criado_em': '2026-11-02T01:30:00+00:00',
         'dados': {'texto': 'Conteúdo '+tipo, 'titulo': 'Título completo '+('longo '*12), 'usuario': 'Pergunta'}}
        for tipo in ('lembranca', 'permanente', 'narrador', 'turno')]}


def test_importacao_idempotente_dono_datas_e_preservacao(logado):
    p = preparar()
    db = SessionLocal(); db.add(BellaMemoria(conta_id=1, texto='Somente no legado')); db.commit(); db.close()
    assert M.importar(1, IDENT, p)['novos'] == 4
    assert M.importar(1, IDENT, p)['novos'] == 0
    db = SessionLocal()
    assert db.query(BellaMemoria).count() == 2
    assert db.query(BellaLore).count() == 2
    assert all(len(r.nome) <= 40 for r in db.query(BellaLore).all())
    assert db.query(BellaArquivo).one().dia == '2026-11-01'
    assert db.query(BellaTurno).count() == 5
    assert len(M.vinculos(db, 1, IDENT)) == 4
    assert M.vinculos(db, 2, IDENT) == {}
    db.close()
    p['registros'][0]['dados']['texto'] = 'Fato atualizado no Models'
    assert M.importar(1, IDENT, p)['atualizados'] == 1
    invalido = deepcopy(p); invalido['registros'][-1]['tipo'] = 'outro'
    with pytest.raises(models.ErroModels): M.importar(1, IDENT, invalido)
    with pytest.raises(models.ErroModels): M.importar(2, IDENT, p)
    db = SessionLocal(); assert db.query(BellaMemoria).count() == 2; db.close()


def test_comando_direcao_id_e_selecao_preservada(logado, monkeypatch):
    p = preparar(); chamadas = []
    def pedir(metodo, rota, conta=None, modelo_id=None, corpo=None):
        chamadas.append((metodo, rota))
        if rota.endswith('/bella-legado'): return {'modelo_id': IDENT}
        if rota.endswith('/sincronizar-memorias'): return {'total': 12}
        if rota.endswith('/memorias-legado'): return p
        raise AssertionError(rota)
    monkeypatch.setattr(models, '_requisicao', pedir)
    db = SessionLocal(); conta = db.get(Conta, 1)
    assert 'Legado → Bella Models' in M.sincronizar(conta)
    db.add(Configuracao(chave='models_selecao:1', valor=IDENT)); db.commit()
    assert 'Models → Bella Legado' in M.sincronizar(conta)
    assert models.selecionado(1) == IDENT
    cfg=db.get(Configuracao,'models_selecao:1'); cfg.valor='outra-modelo'; db.commit()
    antes=len(chamadas)
    assert 'memórias próprias' in M.sincronizar(conta)
    assert len(chamadas)==antes+1 and models.selecionado(1)=='outra-modelo'
    db.close()


@pytest.mark.parametrize('comando',['/sincronizarmemorias','/sincronizar_memorias','/sincronizar memórias'])
def test_roteador_intercepta_sem_responder_com_ia(logado,monkeypatch,comando):
    from database import CanalVinculo
    db=SessionLocal(); db.add(CanalVinculo(conta_id=1,canal='whatsapp',origem='sync-teste')); db.commit()
    monkeypatch.setattr(M,'sincronizar',lambda c:'Sincronização executada')
    r=roteador.atender_texto(db,'whatsapp','sync-teste',comando)
    assert r.mensagens[0]['texto']=='Sincronização executada'
    db.close()
