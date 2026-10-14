"""Bella: autenticação própria, isolamento de canais e voz no computador."""
import base64
import io
import wave
from uuid import uuid4

import pytest

import database
from nucleo import fala, intencao, roteador, voz
from routers import bella
from test_fluxos import _ligar_telegram, _tg
from test_audio import gemini_audio


@pytest.fixture()
def acesso(logado, sistemas, caixa, monkeypatch):
    bella._JANELAS.clear()
    bella._JANELAS_TRANSCRICAO.clear()
    bella._JANELAS_VOZ_LOCAL.clear()
    bella._JANELAS_COMANDOS.clear()
    monkeypatch.setattr(fala, "disponivel", lambda: False)
    logado.post("/api/conectar", json={"app": "fin", "codigo": "CODFIN1"})
    logado.post("/api/conectar", json={"app": "rot", "codigo": "CODROT1"})
    logado.post("/interno/manifesto", headers={"X-Solo-Token": "tok-fin"}, json={
        "versao": "bella", "comandos": [{"comando": "/saldo", "descricao": "Saldo"}],
        "exemplos": ["recebi 92,60 uber"]})
    chave = logado.post("/api/conta/bella").json()["chave"]
    return logado, {"X-Bella-Chave": chave}


def enviar(acesso, texto=None, **dados):
    c, headers = acesso
    return c.post("/api/bella/mensagem", headers=headers, json={
        "pedido_id": str(uuid4()), "texto": texto, **dados})


def wav_base64(segundos=1):
    f = io.BytesIO()
    with wave.open(f, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00" * int(segundos * 32000))
    return base64.b64encode(f.getvalue()).decode()


def test_chave_aparece_uma_vez_e_e_independente_da_siri(acesso):
    c, h = acesso
    estado = c.get("/api/conta/bella").json()
    assert estado["ativo"] and "chave" not in estado
    with database.SessionLocal() as db:
        conta = db.query(database.Conta).first()
        assert conta.bella_hash and h["X-Bella-Chave"] != conta.bella_hash
    siri = c.post("/api/conta/atalho").json()["chave"]
    assert c.post("/api/bella/mensagem", headers={"X-Bella-Chave": siri}, json={
        "pedido_id": str(uuid4()), "texto": "/fin saldo"}).status_code == 401
    assert c.post("/api/atalho", headers={"X-Solo-Chave": h["X-Bella-Chave"]}, json={"texto": "/saldo"}).status_code == 401
    c.delete("/api/conta/bella")
    assert enviar(acesso, "/fin saldo").status_code == 401
    assert c.post("/api/atalho", headers={"X-Solo-Chave": siri}, json={"texto": "/fin saldo"}).status_code == 200


def test_bella_entende_comando_e_modo_nao_muda_telegram(acesso, sistemas):
    c, h = acesso
    _ligar_telegram(c)
    _tg(c, "/rot hoje")
    resposta = enviar(acesso, "Bella, /fin saldo").json()
    assert "eco:/saldo" in resposta["texto"]
    assert sistemas.recebidos[-1][2]["canal"] == "bella"
    enviar(acesso, "/saldo")
    assert sistemas.recebidos[-1][0] == "fin"
    _tg(c, "/hoje")
    assert sistemas.recebidos[-1][0] == "rot"


def test_audio_transcrito_preserva_valor_e_marca_via_audio(acesso, sistemas, monkeypatch):
    ouvido = "Bella, recebi R$ 92,60 na conta Uber referente à diária de motorista."
    monkeypatch.setattr(voz, "transcrever", lambda b, m: ouvido)
    r = enviar(acesso, audio_base64=wav_base64())
    assert r.status_code == 200 and r.json()["ouvido"] == ouvido
    corpo = sistemas.recebidos[-1][2]
    assert corpo["texto"] == ouvido.removeprefix("Bella, ") and corpo["via_audio"] is True
    assert sistemas.recebidos[-1][0] == "fin"


def test_transcricao_para_acao_local_nao_encaminha_nem_altera_modo(acesso, sistemas, monkeypatch):
    c, h = acesso
    enviar(acesso, "/rot hoje")
    antes = len(sistemas.recebidos)
    monkeypatch.setattr(voz, "transcrever", lambda b, m: "Bella, excluir arquivo rascunho.txt")
    pedido = {"pedido_id": str(uuid4()), "audio_base64": wav_base64()}
    r = c.post("/api/bella/transcrever", headers=h, json=pedido)
    assert r.status_code == 200 and r.json()["ouvido"] == "Bella, excluir arquivo rascunho.txt"
    assert len(sistemas.recebidos) == antes
    with database.SessionLocal() as db:
        registros = db.query(database.MensagemProcessada).filter_by(canal=bella.CANAL_TRANSCRICAO).all()
        assert len(registros) == 1
        assert len(registros[0].canal) <= database.MensagemProcessada.canal.type.length
    assert c.post("/api/bella/transcrever", headers=h, json=pedido).status_code == 409
    # A lista anterior do Rotinas continua disponível, pois só houve transcrição.
    assert enviar(acesso, "um").status_code == 200 and sistemas.recebidos[-1][1] == "acao"


def test_texto_transcrito_no_cliente_preserva_origem_por_voz(acesso, sistemas):
    texto = "Recebi R$ 92,60 na conta Uber."
    r = enviar(acesso, texto, via_audio=True)
    assert r.status_code == 200
    assert sistemas.recebidos[-1][2]["texto"] == texto and sistemas.recebidos[-1][2]["via_audio"]


@pytest.mark.parametrize("endpoint,dados", [
    ("transcrever", {"pedido_id": str(uuid4()), "audio_base64": wav_base64()}),
    ("voz-local", {"codigo": "criada"}),
    ("interpretar-comando", {"texto": "Abra projetos", "comandos": [{"id": "a" * 32, "frase": "Abrir minha pasta de projetos"}]}),
])
def test_rotas_locais_exigem_chave_da_bella(acesso, endpoint, dados):
    c, h = acesso
    assert c.post("/api/bella/" + endpoint, json=dados).status_code == 401
    c.delete("/api/conta/bella")
    assert c.post("/api/bella/" + endpoint, headers=h, json=dados).status_code == 401


def test_voz_local_so_sintetiza_frase_fixa_e_reutilizavel(acesso, sistemas, monkeypatch):
    c, h = acesso
    sintetizados = []
    monkeypatch.setattr(fala, "disponivel", lambda: True)
    def sintetizar(texto, canal, **kwargs):
        sintetizados.append((texto, canal, kwargs))
        return {"base64": "SUQz", "mime": "audio/mpeg"}
    monkeypatch.setattr(fala, "sintetizar", sintetizar)
    antes = len(sistemas.recebidos)
    r = c.post("/api/bella/voz-local", headers=h, json={"codigo": "criada"})
    assert r.status_code == 200 and r.json()["falar"] == "Criei a pasta."
    assert sintetizados == [("Criei a pasta.", "whatsapp", {"guardar": True})]
    assert len(sistemas.recebidos) == antes
    r = c.post("/api/bella/voz-local", headers=h, json={"codigo": "C:/pasta/arquivo-privado.txt"})
    assert r.status_code == 422 and len(sintetizados) == 1
    assert c.post("/api/bella/voz-local", headers=h, json={"codigo": "criada", "caminho": "arquivo-privado"}).status_code == 422


def test_transcricao_local_valida_audio_falhas_e_limite(acesso, sistemas, monkeypatch):
    c, h = acesso
    def pedir(audio):
        return c.post("/api/bella/transcrever", headers=h, json={"pedido_id": str(uuid4()), "audio_base64": audio})
    assert pedir("invalido").status_code == 422
    assert pedir(wav_base64(31)).status_code == 422
    monkeypatch.setattr(voz, "transcrever", lambda b, m: "")
    assert pedir(wav_base64()).status_code == 422
    monkeypatch.setattr(voz, "transcrever", lambda b, m: "listar downloads")
    bella._JANELAS_TRANSCRICAO.clear()
    for _ in range(30):
        assert pedir(wav_base64()).status_code == 200
    assert pedir(wav_base64()).status_code == 429
    # Transcrever não consome o limite dos pedidos aos sistemas.
    assert enviar(acesso, "/fin saldo").status_code == 200


def test_falha_de_voz_local_preserva_texto(acesso, monkeypatch):
    c, h = acesso
    monkeypatch.setattr(fala, "disponivel", lambda: True)
    def falhar(*args, **kwargs): raise RuntimeError("segredo")
    monkeypatch.setattr(fala, "sintetizar", falhar)
    r = c.post("/api/bella/voz-local", headers=h, json={"codigo": "aberto"})
    assert r.status_code == 200 and r.json() == {"falar": "Abri o item."}


def test_interpretar_comando_local_sem_execucao_ou_mudanca_de_sessao(acesso, sistemas, monkeypatch):
    from nucleo import gemini
    c, h = acesso
    enviar(acesso, "/rot hoje")
    antes = len(sistemas.recebidos)
    pedidos = []
    def gerar(prompt, texto, **kwargs):
        pedidos.append((prompt, texto, kwargs))
        return '{"comando_id":"' + "a" * 32 + '","confianca":0.95,"candidatos":[]}'
    monkeypatch.setattr(gemini, "gerar", gerar)
    corpo = {"texto": "Leve-me à pasta onde desenvolvo meus projetos", "comandos": [
        {"id": "a" * 32, "frase": "Abrir minha pasta de Projetos"}]}
    r = c.post("/api/bella/interpretar-comando", headers=h, json=corpo)
    assert r.status_code == 200 and r.json() == {"comando_id": "a" * 32, "candidatos": []}
    assert len(sistemas.recebidos) == antes and len(pedidos) == 1
    assert '"frase": "Abrir minha pasta de Projetos"' in pedidos[0][1]
    assert "caminho" not in pedidos[0][1] and "C:\\" not in pedidos[0][1]
    assert enviar(acesso, "um").status_code == 200 and sistemas.recebidos[-1][1] == "acao"
    corpo["comandos"][0]["caminho"] = "C:/nao-enviar"
    assert c.post("/api/bella/interpretar-comando", headers=h, json=corpo).status_code == 422
    assert len(pedidos) == 1


@pytest.mark.parametrize("saida,esperado", [
    (None, {"comando_id": None, "candidatos": []}),
    ('[]', {"comando_id": None, "candidatos": []}),
    ('{invalido}', {"comando_id": None, "candidatos": []}),
    ('{"comando_id":"inventado","confianca":1}', {"comando_id": None, "candidatos": []}),
    ('{"comando_id":"' + "a" * 32 + '","confianca":0.4}', {"comando_id": None, "candidatos": []}),
    ('{"comando_id":"' + "a" * 32 + '","confianca":true}', {"comando_id": None, "candidatos": []}),
    ('{"comando_id":"' + "a" * 32 + '","confianca":1,"candidatos":["' + "a" * 32 + '","' + "b" * 32 + '"]}',
     {"comando_id": None, "candidatos": ["a" * 32, "b" * 32]}),
    ('{"candidatos":["inventado"]}', {"comando_id": None, "candidatos": []}),
])
def test_interpretacao_local_valida_saida_da_ia(monkeypatch, saida, esperado):
    from nucleo import comandos_locais, gemini
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: saida)
    assert comandos_locais.interpretar("Abra a pasta de trabalho", [
        {"id": "a" * 32, "frase": "Abrir projetos"}, {"id": "b" * 32, "frase": "Abrir trabalho"}]) == esperado


def test_interpretacao_local_valida_catalogo_e_limita_pedidos(acesso, monkeypatch):
    from nucleo import gemini
    c, h = acesso
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: None)
    corpo = {"texto": "Abra projetos", "comandos": [{"id": "a" * 32, "frase": "Abrir projetos"}]}
    for invalido in ({**corpo, "comandos": []}, {**corpo, "comandos": corpo["comandos"] * 2},
                     {**corpo, "comandos": [{"id": "caminho", "frase": "Abrir projetos"}]},
                     {**corpo, "comandos": [{"id": "a" * 32, "frase": "Executar", "tipo": "powershell"}]},
                     {**corpo, "caminho": "C:/projetos"}):
        assert c.post("/api/bella/interpretar-comando", headers=h, json=invalido).status_code == 422
    bella._JANELAS_COMANDOS.clear()
    for _ in range(30):
        assert c.post("/api/bella/interpretar-comando", headers=h, json=corpo).status_code == 200
    assert c.post("/api/bella/interpretar-comando", headers=h, json=corpo).status_code == 429


@pytest.mark.parametrize("tipo", ["google", "youtube", "maps"])
def test_interpretacao_de_pesquisa_so_retorna_id_e_assunto(monkeypatch, tipo):
    from nucleo import comandos_locais, gemini
    import json
    comandos = [{"id": "a" * 32, "frase": "Pesquisar sobre {assunto}", "tipo": tipo}]
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: json.dumps({
        "comando_id": "a" * 32, "confianca": .95, "assunto": "Escrita criativa",
        "url": "javascript:ignorar", "tipo": "powershell"}))
    assert comandos_locais.interpretar("Encontre dicas de escrita criativa", comandos) == {
        "comando_id": "a" * 32, "candidatos": [], "assunto": "Escrita criativa"}


@pytest.mark.parametrize("assunto", [["tema"], "x" * 501])
def test_interpretacao_de_pesquisa_recusa_assunto_invalido(monkeypatch, assunto):
    from nucleo import comandos_locais, gemini
    import json
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: json.dumps({
        "comando_id": "a" * 32, "confianca": .95, "assunto": assunto}))
    assert comandos_locais.interpretar("Pesquise escrita", [
        {"id": "a" * 32, "frase": "Pesquisar {assunto}", "tipo": "google"}]) == {
            "comando_id": None, "candidatos": []}


def test_pesquisa_ambigua_preserva_assunto_para_escolha(monkeypatch):
    from nucleo import comandos_locais, gemini
    import json
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: json.dumps({
        "comando_id": "", "candidatos": ["a" * 32, "b" * 32], "assunto": "Escrita criativa"}))
    assert comandos_locais.interpretar("Encontre escrita criativa", [
        {"id": "a" * 32, "frase": "Pesquisar {assunto}", "tipo": "google"},
        {"id": "b" * 32, "frase": "Pesquisar vídeos {assunto}", "tipo": "youtube"}]) == {
            "comando_id": None, "candidatos": ["a" * 32, "b" * 32], "assunto": "Escrita criativa"}


def test_interpretacao_de_site_ignora_destino_inventado(monkeypatch):
    from nucleo import comandos_locais, gemini
    monkeypatch.setattr(gemini, "gerar", lambda *a, **k: '{"comando_id":"' + "a" * 32 +
                        '","confianca":0.95,"assunto":"javascript:ignorar","url":"https://inventado.invalid"}')
    assert comandos_locais.interpretar("Abra meu correio", [
        {"id": "a" * 32, "frase": "Abrir meu Gmail", "tipo": "site"}]) == {
            "comando_id": "a" * 32, "candidatos": []}


@pytest.mark.parametrize("modo", [None, "fin", "rot"])
@pytest.mark.parametrize("audio", [False, True])
@pytest.mark.parametrize("pedido,comando", [("saldo", "/saldo"), ("Saldo!", "/saldo"),
                                           ("saldos", "/saldo"), ("saldo Uber Conta", "/saldo Uber Conta")])
def test_saldo_sem_barra_e_consulta_em_qualquer_modo(acesso, sistemas, monkeypatch, modo, audio, pedido, comando):
    if modo:
        enviar(acesso, f"/{modo} ajuda")
    def nao_chamar_ia(*a):
        raise AssertionError("Comando anunciado não precisa de IA")
    monkeypatch.setattr(intencao, "_ia", nao_chamar_ia)
    monkeypatch.setattr(voz, "transcrever", lambda b, m: "Bella, " + pedido)
    antes = len(sistemas.recebidos)
    r = enviar(acesso, audio_base64=wav_base64()) if audio else enviar(acesso, pedido)
    assert r.status_code == 200 and len(sistemas.recebidos) == antes + 1
    app, _, corpo = sistemas.recebidos[-1]
    assert app == "fin" and corpo["texto"] == comando
    assert corpo.get("via_audio", False) == audio
    assert "Entendi: Finances" in r.json()["texto"]


def test_saltos_pede_correcao_sem_executar_e_saldo_seguinte_funciona(acesso, sistemas, monkeypatch):
    enviar(acesso, "/fin saldo")
    antes = len(sistemas.recebidos)
    monkeypatch.setattr(voz, "transcrever", lambda b, m: "saltos")
    r = enviar(acesso, audio_base64=wav_base64())
    assert r.status_code == 200 and "Você quis dizer “saldo”" in r.json()["texto"]
    assert len(sistemas.recebidos) == antes
    monkeypatch.setattr(voz, "transcrever", lambda b, m: "saldo")
    assert enviar(acesso, audio_base64=wav_base64()).status_code == 200
    assert len(sistemas.recebidos) == antes + 1 and sistemas.recebidos[-1][2]["texto"] == "/saldo"


@pytest.mark.parametrize("audio", [False, True])
def test_lancamento_com_saldo_no_meio_preserva_valor_e_descricao(acesso, sistemas, monkeypatch, audio):
    enviar(acesso, "/fin saldo")
    pedido = "Recebi R$ 92,60 na Uber, saldo da diária de motorista."
    monkeypatch.setattr(voz, "transcrever", lambda b, m: pedido)
    r = enviar(acesso, audio_base64=wav_base64()) if audio else enviar(acesso, pedido)
    assert r.status_code == 200
    assert sistemas.recebidos[-1][2]["texto"] == pedido


def test_escolhas_faladas_tambem_executam_acao(acesso, sistemas):
    r = enviar(acesso, "/rot hoje").json()
    assert r["opcoes"][0]["numero"] == 1
    assert "Para escolher, diga o número" in r["falar"]
    r = enviar(acesso, "Bella, um")
    assert r.status_code == 200 and sistemas.recebidos[-1][1] == "acao"
    assert sistemas.recebidos[-1][2]["dados"] == "ok|r|12"


def test_pedido_reentregue_nao_executa_duas_vezes(acesso, sistemas):
    c, h = acesso
    p = {"pedido_id": str(uuid4()), "texto": "recebi 92,60 uber"}
    assert c.post("/api/bella/mensagem", headers=h, json=p).status_code == 200
    antes = len(sistemas.recebidos)
    assert c.post("/api/bella/mensagem", headers=h, json=p).status_code == 409
    assert len(sistemas.recebidos) == antes


@pytest.mark.parametrize("dados", [{}, {"texto": "oi", "audio_base64": "AAAA"},
                                  {"audio_base64": "não é base64"},
                                  {"audio_base64": base64.b64encode(b"invalido").decode()}])
def test_pedidos_invalidos_nao_chegam_ao_sistema(acesso, sistemas, dados):
    antes = len(sistemas.recebidos)
    assert enviar(acesso, **dados).status_code == 422
    assert len(sistemas.recebidos) == antes


def test_audio_longo_e_recusado(acesso):
    assert enviar(acesso, audio_base64=wav_base64(31)).status_code == 422


def test_falha_na_transcricao_nao_executa_comando(acesso, sistemas, monkeypatch):
    def falhar(b, m): raise voz.FalhaVoz("gemini/principal: limite de uso atingido (HTTP 429)")
    monkeypatch.setattr(voz, "transcrever", falhar)
    antes = len(sistemas.recebidos)
    r = enviar(acesso, audio_base64=wav_base64())
    assert r.status_code == 502 and "429" in r.json()["detail"]
    assert len(sistemas.recebidos) == antes


def test_recuperacao_503_encaminha_comando_uma_vez(acesso, sistemas, gemini_audio):
    resultados, pedidos, pausas = gemini_audio
    resultados.extend([503, 503, "Bella, recebi R$ 92,60 na conta Uber"])
    antes = len(sistemas.recebidos)
    r = enviar(acesso, audio_base64=wav_base64())
    assert r.status_code == 200 and len(pedidos) == 3
    assert len(sistemas.recebidos) == antes + 1
    corpo = sistemas.recebidos[-1][2]
    assert corpo["texto"] == "recebi R$ 92,60 na conta Uber" and corpo["via_audio"]


def test_503_em_todos_modelos_nao_encaminha_nada(acesso, sistemas, gemini_audio):
    resultados, pedidos, pausas = gemini_audio
    resultados.extend([503, 503, 503])
    antes = len(sistemas.recebidos)
    r = enviar(acesso, audio_base64=wav_base64())
    assert r.status_code == 502 and "HTTP 503" in r.json()["detail"]
    assert len(sistemas.recebidos) == antes


def test_resposta_com_voz_ou_texto_se_tts_falhar(acesso, monkeypatch):
    monkeypatch.setattr(fala, "disponivel", lambda: True)
    monkeypatch.setattr(fala, "sintetizar", lambda t, c: {"base64": "SUQz", "mime": "audio/mpeg"})
    assert enviar(acesso, "/fin saldo").json()["audio_base64"] == "SUQz"
    def falhar(t, c): raise RuntimeError()
    monkeypatch.setattr(fala, "sintetizar", falhar)
    r = enviar(acesso, "/fin saldo")
    assert r.status_code == 200 and "eco:/saldo" in r.json()["texto"]
    assert "audio_base64" not in r.json()


def test_gerenciar_exige_login_e_chave_trocada_invalida_antiga(cliente, acesso):
    c, h = acesso
    c.post("/api/conta/bella")
    assert enviar(acesso, "oi").status_code == 401
    c.post("/api/auth/sair"); c.cookies.clear()
    assert c.get("/api/conta/bella").status_code == 401
    assert c.post("/api/conta/bella").status_code == 401


def test_limite_de_pedidos_e_saudacao_sem_sistema(acesso, sistemas):
    r = enviar(acesso, "Bella")
    assert r.status_code == 200 and "jeff" in r.json()["texto"]
    conta_id = None
    with database.SessionLocal() as db:
        conta_id = db.query(database.Conta).first().id
    import time
    bella._JANELAS[conta_id] = [time.monotonic()] * 30
    antes = len(sistemas.recebidos)
    assert enviar(acesso, "/fin saldo").status_code == 429
    assert len(sistemas.recebidos) == antes


def test_conta_inativa_nao_pode_usar_bella(acesso):
    with database.SessionLocal() as db:
        conta = db.query(database.Conta).first()
        conta.ativo = False
        db.commit()
    assert enviar(acesso, "/fin saldo").status_code == 401


def test_migracao_acrescenta_campos_bella_em_banco_antigo(monkeypatch):
    from sqlalchemy import create_engine, inspect, text
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE contas (id INTEGER PRIMARY KEY, usuario VARCHAR(50), email VARCHAR(200))"))
    monkeypatch.setattr(database, "engine", engine)
    database._migrar(); database._migrar()
    colunas = {c["name"] for c in inspect(engine).get_columns("contas")}
    assert {"bella_hash", "bella_criado_em", "bella_usado_em"} <= colunas
    engine.dispose()


def test_bella_fala_roteiro_natural_e_mantem_tabela_na_tela(acesso, monkeypatch):
    from conftest import Resp
    from nucleo import gemini, modulos
    dito = 'O cartão Santander CC está sem limite disponível.'
    sintetizados = []
    monkeypatch.setattr(modulos, '_post', lambda *a, **k: Resp(200, {'mensagens':[
        {'texto':'💳 Cartões\nSantander CC   Disp: R$ 0,00', 'falado':dito, 'opcoes':[]}]}))
    monkeypatch.setattr(gemini, 'gerar', lambda *a, **k: pytest.fail('Roteiro pronto não pede IA'))
    monkeypatch.setattr(fala, 'disponivel', lambda: True)
    monkeypatch.setattr(fala, 'sintetizar', lambda t, c: sintetizados.append((t,c)) or {'base64':'SUQz','mime':'audio/mpeg'})
    r = enviar(acesso, '/fin saldo Santander CC').json()
    assert 'Disp:' in r['texto'] and r['falar'] == dito
    assert sintetizados == [(dito, 'whatsapp')] and r['audio_base64'] == 'SUQz'
