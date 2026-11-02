"""Separação de prints esportivos e prompts nos três canais, sem rede real."""
import base64
from datetime import datetime, timezone
from types import SimpleNamespace as S
import pytest
from database import SessionLocal, Conta, CanalVinculo, VinculoSistema
from nucleo import imagens_entrada as I, roteador as R, modulos, prompts_bella as P
from routers import bella


def preparar(logado, vinculado=True):
    db=SessionLocal(); conta=db.query(Conta).first()
    db.add_all([CanalVinculo(conta_id=conta.id,canal='telegram',origem='777'),
                CanalVinculo(conta_id=conta.id,canal='whatsapp',origem='555@s.whatsapp.net')])
    if vinculado:
        db.add(VinculoSistema(conta_id=conta.id,app='rot',usuario_id='44'))
    db.commit(); return db,conta


def tratado(**kwargs):
    return dict(tratado=True,estado='registrado',mensagens=[{'texto':'Corrida registrada: 1,91 km em 17:50'}],**kwargs)


@pytest.mark.parametrize('canal,origem',[('telegram','777'),('whatsapp','555@s.whatsapp.net')])
def test_print_vai_so_ao_rotinas(logado,monkeypatch,canal,origem):
    db,conta=preparar(logado)
    monkeypatch.setattr(P,'guardar_referencia',lambda *a:pytest.fail('treino virou referência'))
    monkeypatch.setattr(P,'criar',lambda *a,**k:pytest.fail('treino virou prompt'))
    vistos=[]
    def chamar(mod,rota,corpo):
        vistos.append((mod.chave,rota,corpo));return tratado()
    monkeypatch.setattr(modulos,'chamar',chamar)
    resposta=R.atender_imagem(db,canal,origem,b'print-strava','image/jpeg',enviado_em=1793659200)
    assert 'Corrida registrada' in resposta.mensagens[0]['texto']
    app,rota,corpo=vistos[0]
    assert app=='rot' and rota=='imagem' and corpo['usuario_id']=='44'
    assert corpo['origem']==f'solo:{conta.id}:{canal}'
    assert corpo['imagem_base64']==base64.b64encode(b'print-strava').decode()
    assert corpo['enviado_em']==I.instante_envio(1793659200).isoformat()
    db.close()


@pytest.mark.parametrize('legenda',['/prompt roupa azul','prompt dessa roupa, banheiro','quero um prompt usando esta foto'])
def test_prompt_explicito_nao_chama_rotinas(logado,monkeypatch,legenda):
    db,_=preparar(logado)
    monkeypatch.setattr(modulos,'chamar',lambda *a:pytest.fail('prompt foi para Rotinas'))
    monkeypatch.setattr(P,'guardar_referencia',lambda *a:None)
    monkeypatch.setattr(R,'_prompt_responder',lambda *a:R.Resposta().diz('prompt solicitado'))
    r=R.atender_imagem(db,'telegram','777',b'referencia','image/jpeg',legenda)
    assert r.mensagens[0]['texto']=='prompt solicitado'
    db.close()


def test_imagem_normal_preserva_prompt(logado,monkeypatch):
    db,_=preparar(logado)
    monkeypatch.setattr(modulos,'chamar',lambda *a:dict(tratado=False,estado='nao_treino',mensagens=[]))
    guardadas=[];monkeypatch.setattr(P,'guardar_referencia',lambda *a:guardadas.append(a))
    r=R.atender_imagem(db,'telegram','777',b'referencia','image/jpeg')
    assert len(guardadas)==1 and 'Recebi a referência' in r.mensagens[0]['texto']
    db.close()


@pytest.mark.parametrize('resultado',[dict(tratado=True,estado='incompleto',mensagens=[{'texto':'Falta a data'}]),{},None])
def test_falha_ou_print_incompleto_nao_viram_prompt(logado,monkeypatch,resultado):
    db,_=preparar(logado)
    def chamar(*a):
        if resultado is None: raise modulos.ErroModulo('Serviço indisponível')
        return resultado
    monkeypatch.setattr(modulos,'chamar',chamar)
    monkeypatch.setattr(P,'guardar_referencia',lambda *a:pytest.fail('guardou imagem indevida'))
    assert R.atender_imagem(db,'telegram','777',b'print','image/jpeg').mensagens
    db.close()


def test_sem_vinculo_so_classifica(logado,monkeypatch):
    db,_=preparar(logado,vinculado=False)
    vistos=[]
    monkeypatch.setattr(modulos,'chamar',lambda m,r,c: vistos.append(c) or dict(tratado=True,estado='sem_vinculo',mensagens=[{'texto':'Conecte o Rotinas'}]))
    r=R.atender_imagem(db,'telegram','777',b'print','image/jpeg')
    assert vistos[0]['usuario_id'] is None and 'Conecte' in r.mensagens[0]['texto']
    db.close()


def test_outro_modo_nao_desvia_print(logado,monkeypatch):
    db,conta=preparar(logado)
    R._entrar_modo(db,R.sessao_de(db,'telegram','777'),'fin')
    vistos=[];monkeypatch.setattr(modulos,'chamar',lambda mod,*a:vistos.append(mod.chave) or tratado())
    R.atender_imagem(db,'telegram','777',b'print','image/jpeg')
    assert vistos==['rot']
    db.close()


@pytest.mark.parametrize('texto',['analise esta imagem','crie um prompt com essa referência','/rot treino 01/11/2026 caminhada'])
def test_bella_anexo_de_treino_nao_cria_prompt(logado,monkeypatch,texto):
    db,conta=preparar(logado)
    monkeypatch.setattr(bella,'_autenticar',lambda *a:conta)
    monkeypatch.setattr(bella,'_limitar',lambda *a:None)
    monkeypatch.setattr(bella,'_guardar_fala',lambda *a:'voz-treino')
    monkeypatch.setattr(P,'criar',lambda *a,**k:pytest.fail('Bella criou prompt para treino'))
    monkeypatch.setattr(P,'guardar_referencia',lambda *a:pytest.fail('Bella guardou print'))
    monkeypatch.setattr(modulos,'chamar',lambda mod,rota,corpo:tratado())
    r=bella.conversa(bella.PedidoConversa(texto=texto,modo='safada',imagem_mime='image/jpeg',imagem_base64=base64.b64encode(b'print').decode()),'teste',db)
    assert 'Corrida registrada' in r['texto'] and '[[prompt]]' not in r['texto']
    assert r['voz_id']=='voz-treino'
    db.close()


def test_timeout_imagem_e_resposta_sem_conteudo_nos_logs(monkeypatch,caplog):
    vistos=[]
    class Resp:
        status_code=422
        text='CONTEUDO_PRIVADO_DO_PRINT'
    monkeypatch.setattr(modulos,'_post',lambda *a:vistos.append(a) or Resp())
    with pytest.raises(modulos.ErroModulo):
        modulos.chamar(modulos.por_chave('rot'),'imagem',dict(imagem_base64='privado'))
    assert vistos[0][3] is modulos.TIMEOUT_IMAGEM
    assert 'CONTEUDO_PRIVADO' not in caplog.text


@pytest.mark.parametrize('canal',['telegram','whatsapp'])
def test_webhook_envia_data_e_imagem_ao_rotinas(logado,caixa,monkeypatch,canal):
    from canais import telegram
    from routers import webhooks
    db,_=preparar(logado);db.close()
    vistos=[]
    monkeypatch.setattr(modulos,'chamar',lambda mod,rota,corpo:vistos.append(corpo) or tratado())
    monkeypatch.setattr(P,'guardar_referencia',lambda *a:pytest.fail('webhook guardou treino'))
    if canal=='telegram':
        monkeypatch.setattr(telegram,'baixar',lambda *a:b'print')
        r=logado.post('/api/telegram/webhook',headers={'x-telegram-bot-api-secret-token':'tg-secreto'},json={
            'update_id':900001,'message':{'message_id':900001,'date':1793659200,'chat':{'id':777,'type':'private'},'photo':[{'file_id':'foto'}]}})
    else:
        monkeypatch.setattr(webhooks,'_bytes_do_audio',lambda *a:(b'print','image/jpeg'))
        r=logado.post('/api/whatsapp/webhook/wa-secreto',json={'event':'messages.upsert','data':{
            'key':{'remoteJid':'555@s.whatsapp.net','id':'print-treino-1','fromMe':False},'messageTimestamp':1793659200,
            'message':{'imageMessage':{'caption':'/rot treino','mimetype':'image/jpeg'}}}})
    assert r.status_code==200 and len(vistos)==1
    assert vistos[0]['usuario_id']=='44' and vistos[0]['enviado_em']==I.instante_envio(1793659200).isoformat()


@pytest.mark.parametrize('legenda',['/rot treino, não crie prompt','não é prompt, registre a corrida'])
def test_legenda_de_treino_nao_e_pedido_de_prompt(logado,monkeypatch,legenda):
    db,_=preparar(logado)
    monkeypatch.setattr(modulos,'chamar',lambda *a:tratado())
    monkeypatch.setattr(P,'guardar_referencia',lambda *a:pytest.fail('treino virou referência'))
    assert 'Corrida registrada' in R.atender_imagem(db,'telegram','777',b'print','image/jpeg',legenda).mensagens[0]['texto']
    db.close()


def test_anexo_invalido_nao_chega_ao_servico(logado,monkeypatch):
    db,_=preparar(logado)
    monkeypatch.setattr(modulos,'chamar',lambda *a:pytest.fail('anexo inválido foi ao Rotinas'))
    assert R.atender_imagem(db,'telegram','777',b'print','image/gif').mensagens
    db.close()
