"""Fallback real de HTTP sem tocar nos provedores ou na rede."""
import base64
import httpx
import pytest
import config
from nucleo import fala, voicestudio


@pytest.fixture()
def reserva(monkeypatch, tmp_path):
    fala._QUEDA.clear()
    import database
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    database.Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    values = {"ELEVENLABS_API_KEY": "k1", "ELEVENLABS_API_KEY_SECONDARY": "k2",
              "ELEVENLABS_CONTAS_EXTRAS": {}, "ELEVENLABS_VOICE_ID": "eleven-voice",
              "ELEVENLABS_MODEL": "eleven_flash_v2_5", "BELLA_AUDIO_DIR": str(tmp_path),
              "VOICESTUDIO_URL": "https://voice.internal", "VOICESTUDIO_API_KEY": "private-key",
              "VOICESTUDIO_VOICE_ID": "bella-clone-id", "VOICESTUDIO_MODEL": "omnivoice",
              "VOICESTUDIO_TIMEOUT": 120, "VOICESTUDIO_STEPS": 16}
    for key, value in values.items():
        monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(fala, "_estado", {"voz": None, "ultimo_erro": None})
    requests = []
    status = {"k1": 429, "k2": 402, "vs": 200, "type": None, "error": False}

    class Client:
        def __init__(self, **kwargs):
            self.options = kwargs
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json, headers):
            requests.append((url, dict(json), dict(headers), self.options))
            if "xi-api-key" in headers:
                code = status[headers["xi-api-key"]]
                return httpx.Response(code, content=b"ELEVEN" if code == 200 else b"")
            if status["error"]:
                raise httpx.ConnectError("private-key: private-text")
            kind = status["type"] or ("audio/ogg" if json["response_format"] == "opus" else "audio/mpeg")
            return httpx.Response(status["vs"], content=b"VOICE", headers={"Content-Type": kind})

    monkeypatch.setattr(fala.httpx, "Client", Client)
    return requests, status


def test_elevenlabs_tem_prioridade_e_resposta_identica(reserva):
    requests, status = reserva
    status["k1"] = 200
    assert fala.sintetizar("Oi", "whatsapp") == {"base64": "RUxFVkVO", "mime": "audio/mpeg"}
    assert len(requests) == 1 and "elevenlabs" in requests[0][0]


def test_tenta_todas_as_contas_antes_do_motor_secundario(reserva):
    requests, _ = reserva
    result = fala.sintetizar("[animado] Oi", "whatsapp")
    assert [r[2].get("xi-api-key", "vs") for r in requests] == ["k1", "k2", "vs"]
    assert result == {"base64": base64.b64encode(b"VOICE").decode(), "mime": "audio/mpeg"}
    url, body, headers, options = requests[-1]
    assert url == "https://voice.internal/v1/audio/speech"
    assert body == {"model": "omnivoice", "voice": "bella-clone-id", "input": "Oi",
                    "language": "pt", "response_format": "mp3", "speed": 1.0, "num_step": 16}
    assert headers["Authorization"] == "Bearer private-key"
    assert options["follow_redirects"] is False
    assert options["timeout"].connect == 5
    assert fala.ultimo_erro() is None


def test_reserva_elevenlabs_ainda_precede_voicestudio(reserva):
    requests, status = reserva
    status["k2"] = 200
    assert fala.sintetizar("Oi", "whatsapp")["base64"] == "RUxFVkVO"
    assert len(requests) == 2


def test_telegram_recebe_ogg_opus(reserva):
    requests, _ = reserva
    assert fala.sintetizar("Oi", "telegram")["mime"] == "audio/ogg"
    assert requests[-1][1]["response_format"] == "opus"


def test_sem_chaves_elevenlabs_usa_reserva_configurada(reserva, monkeypatch):
    requests, _ = reserva
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY_SECONDARY", "")
    assert fala.disponivel()
    assert fala.sintetizar("Oi", "whatsapp")
    assert len(requests) == 1 and "xi-api-key" not in requests[0][2]


@pytest.mark.parametrize("field", ["VOICESTUDIO_URL", "VOICESTUDIO_VOICE_ID"])
def test_reserva_sem_configuracao_nao_chama_http(reserva, monkeypatch, field):
    requests, _ = reserva
    monkeypatch.setattr(config, field, "")
    assert fala.sintetizar("Oi", "whatsapp") is None
    assert len(requests) == 2


@pytest.mark.parametrize("status_code, content_type", [(503, "audio/mpeg"), (401, "application/json"), (200, "application/json")])
def test_resposta_invalida_nao_vira_audio(reserva, status_code, content_type):
    _, status = reserva
    status.update(vs=status_code, type=content_type)
    assert fala.sintetizar("Oi", "whatsapp") is None


def test_falha_de_rede_nao_vaza_segredos(reserva, caplog):
    _, status = reserva
    status["error"] = True
    assert fala.sintetizar("private-text", "whatsapp") is None
    assert "private-key" not in caplog.text and "private-text" not in caplog.text


def test_cache_da_reserva_isolado_e_primario_recupera_prioridade(reserva):
    requests, status = reserva
    a = fala.sintetizar("Oi", "whatsapp", guardar=True)
    b = fala.sintetizar("Oi", "whatsapp", guardar=True)
    assert a == b and a["perfil_voz"]["conta"] == "voicestudio"
    assert sum("xi-api-key" not in r[2] for r in requests) == 1
    assert fala.perfil_ativo()["conta"] == "principal"
    status["k1"] = 200
    c = fala.sintetizar("Oi", "whatsapp", guardar=True)
    assert c["base64"] == "RUxFVkVO" and c["cache_id"] != a["cache_id"]
    assert c["perfil_voz"]["conta"] == "principal"


def test_tom_explicito_nao_altera_fala_normal(reserva):
    requests, _ = reserva
    fala.sintetizar("Oi", "whatsapp", tom="sussurro")
    assert requests[-1][1]["instruct"] == "whisper"
    fala.sintetizar("Oi", "whatsapp")
    assert "instruct" not in requests[-1][1]


def test_url_com_v1_e_sem_chave_local(reserva, monkeypatch):
    requests, _ = reserva
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "http://127.0.0.1:3900/v1/")
    monkeypatch.setattr(config, "VOICESTUDIO_API_KEY", "")
    assert fala.sintetizar("Oi", "whatsapp")
    assert requests[-1][0] == "http://127.0.0.1:3900/v1/audio/speech"
    assert "Authorization" not in requests[-1][2]


def test_sem_texto_nao_chama_nenhum_motor(reserva):
    assert fala.sintetizar("", "whatsapp") is None
    assert reserva[0] == []


def test_host_ou_voz_diferentes_nao_reutilizam_cache(reserva, monkeypatch):
    a = fala.sintetizar("Oi", "whatsapp", guardar=True)
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "https://other.internal")
    b = fala.sintetizar("Oi", "whatsapp", guardar=True)
    monkeypatch.setattr(config, "VOICESTUDIO_VOICE_ID", "other-voice")
    c = fala.sintetizar("Oi", "whatsapp", guardar=True)
    assert len({a["cache_id"], b["cache_id"], c["cache_id"]}) == 3


@pytest.mark.parametrize("url", ["http://[", "https://name:password@host", "https://host/other"])
def test_url_invalida_nao_faz_pedido_a_reserva(reserva, monkeypatch, url):
    requests, _ = reserva
    monkeypatch.setattr(config, "VOICESTUDIO_URL", url)
    assert fala.sintetizar("Oi", "whatsapp") is None
    assert len(requests) == 2


@pytest.mark.parametrize("motor", ["elevenlabs", "voicestudio"])
def test_escolha_manual_nao_chama_outro_provedor(reserva, motor):
    import database
    with database.SessionLocal() as db:
        database.gravar_config(db, fala.CHAVE_MOTOR, motor)
    requests, status = reserva
    status["k1"] = 200
    result = fala.sintetizar("Oi", "whatsapp", guardar=True)
    assert result
    assert len(requests) == 1
    assert ("xi-api-key" in requests[0][2]) == (motor == "elevenlabs")
    assert result["perfil_voz"]["conta"] == ("principal" if motor == "elevenlabs" else "voicestudio")
    assert fala.perfil_ativo() == result["perfil_voz"]


@pytest.mark.parametrize("motor", ["elevenlabs", "voicestudio"])
def test_falha_manual_nao_troca_de_motor(reserva, motor):
    import database
    with database.SessionLocal() as db:
        database.gravar_config(db, fala.CHAVE_MOTOR, motor)
    requests, status = reserva
    status["vs"] = 503
    assert fala.sintetizar("Oi", "whatsapp") is None
    assert all(("xi-api-key" in r[2]) == (motor == "elevenlabs") for r in requests)
    assert fala.ultimo_erro()


def test_selecao_admin_persiste_e_volta_ao_automatico(reserva):
    import database
    from routers.admin import ajustar_voz, AjusteVoz, painel_voz
    requests, status = reserva
    with database.SessionLocal() as db:
        assert ajustar_voz(AjusteVoz(motor="voicestudio"), db=db)["motor"] == "voicestudio"
        v = painel_voz()
        assert v["motor"]["atual"] == "voicestudio"
        assert v["perfil_voicestudio"]["voz"] == "bella-clone-id"
        assert requests == []  # o painel local não consulta a ElevenLabs
        assert ajustar_voz(AjusteVoz(motor="automatico"), db=db)["motor"] == "automatico"
    assert fala.sintetizar("Oi", "whatsapp")
    assert [r[2].get("xi-api-key", "vs") for r in requests] == ["k1", "k2", "vs"]


@pytest.mark.parametrize("dados, codigo", [({"motor": "invalido"}, 422),
                                           ({"motor": "elevenlabs", "conta": "principal"}, 422)])
def test_admin_rejeita_selecao_invalida_sem_gravar(reserva, dados, codigo):
    import database
    from fastapi import HTTPException
    from routers.admin import ajustar_voz, AjusteVoz
    with database.SessionLocal() as db, pytest.raises(HTTPException) as erro:
        ajustar_voz(AjusteVoz(**dados), db=db)
    assert erro.value.status_code == codigo
    assert fala.motor_escolhido() == "automatico"


def test_motor_sem_configuracao_nao_pode_ser_selecionado(reserva, monkeypatch):
    import database
    from fastapi import HTTPException
    from routers.admin import ajustar_voz, AjusteVoz
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "")
    with database.SessionLocal() as db, pytest.raises(HTTPException) as erro:
        ajustar_voz(AjusteVoz(motor="voicestudio"), db=db)
    assert erro.value.status_code == 409
    assert fala.motor_escolhido() == "automatico"


def test_troca_manual_altera_catalogo_saudacao_e_reutiliza_cache(reserva):
    import database
    from types import SimpleNamespace
    from nucleo import saudacoes
    conta = SimpleNamespace(id=1, usuario="jeff", nome="Jefferson")
    original = saudacoes.catalogo(conta)
    with database.SessionLocal() as db:
        database.gravar_config(db, fala.CHAVE_MOTOR, "voicestudio")
    clone = saudacoes.preparar(conta, 0)
    assert clone["perfil"] != original["perfil"]
    assert clone["voz"]["conta"] == "voicestudio"
    assert clone["perfil"] == saudacoes.catalogo(conta)["perfil"]
    assert saudacoes.preparar(conta, 0)["cache_id"] == clone["cache_id"]
    assert len(reserva[0]) == 1
    with database.SessionLocal() as db:
        database.gravar_config(db, fala.CHAVE_MOTOR, "elevenlabs")
    assert saudacoes.catalogo(conta)["perfil"] == original["perfil"]


def test_disponibilidade_respeita_escolha_manual(reserva, monkeypatch):
    import database
    with database.SessionLocal() as db:
        database.gravar_config(db, fala.CHAVE_MOTOR, "voicestudio")
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "")
    assert not fala.disponivel()
    with database.SessionLocal() as db:
        database.gravar_config(db, fala.CHAVE_MOTOR, "elevenlabs")
    assert fala.disponivel()


def test_listar_vozes_e_escolher(monkeypatch):
    from nucleo import voicestudio
    monkeypatch.setattr(config, "VOICESTUDIO_URL", "http://100.1.2.3")
    monkeypatch.setattr(config, "VOICESTUDIO_API_KEY", "k")
    voicestudio._VOZES.update(quando=0.0, origem=None, itens=[])
    vistos = []

    class Cliente:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, url, headers=None):
            vistos.append((url, headers))
            return httpx.Response(200, request=httpx.Request("GET", url),
                                  json={"voices": [{"id": "a1", "name": "Bella"}, {"id": "b2", "name": "Jefferson"}, {"id": "a1"}]})
    monkeypatch.setattr(voicestudio.httpx, "Client", Cliente)
    assert voicestudio.listar_vozes() == [{"voice_id": "a1", "nome": "Bella"}, {"voice_id": "b2", "nome": "Jefferson"}]
    assert vistos[0] == ("http://100.1.2.3/v1/audio/voices", {"Authorization": "Bearer k"})
    voicestudio.listar_vozes()
    assert len(vistos) == 1                         # cache


@pytest.mark.parametrize("steps", [8, 32])
def test_passos_configuraveis_preservam_voz_e_velocidade(reserva, monkeypatch, steps):
    requests, _ = reserva
    monkeypatch.setattr(config, "VOICESTUDIO_STEPS", steps)
    assert voicestudio.sintetizar("Oi", "whatsapp")
    body = requests[-1][1]
    assert body["num_step"] == steps
    assert body["speed"] == 1.0 and body["voice"] == "bella-clone-id"


def test_troca_de_passos_isola_cache(reserva, monkeypatch):
    first = voicestudio.sintetizar("Oi", "whatsapp", guardar=True)
    monkeypatch.setattr(config, "VOICESTUDIO_STEPS", 32)
    second = voicestudio.sintetizar("Oi", "whatsapp", guardar=True)
    assert first["cache_id"] != second["cache_id"]
    assert voicestudio.sintetizar("Oi", "whatsapp", guardar=True) == second
    assert len(reserva[0]) == 2


def test_tempos_nao_registram_texto_ou_segredos(reserva, caplog):
    caplog.set_level("INFO")
    assert fala.sintetizar("private-text", "whatsapp")
    assert "Sintese ElevenLabs:" in caplog.text
    assert "Sintese VoiceStudio:" in caplog.text
    assert "passos=16" in caplog.text
    assert "private-text" not in caplog.text and "private-key" not in caplog.text


def test_elevenlabs_limita_conexao_sem_encurtar_geracao(reserva):
    requests, status = reserva
    status["k1"] = 200
    assert fala.sintetizar("Oi", "whatsapp")
    timeout = requests[0][3]["timeout"]
    assert timeout.connect == 5 and timeout.read == 40
    assert len(requests) == 1


def test_motor_que_demora_para_falhar_fica_de_lado_no_automatico(reserva, monkeypatch):
    requests, status = reserva
    relogio = {"t": 1000.0}
    monkeypatch.setattr(fala.time, "monotonic", lambda: relogio["t"])
    chamadas = []
    original = fala._sintetizar_elevenlabs

    def lenta(*a, **k):
        chamadas.append(1)
        relogio["t"] += 40                      # a ElevenLabs esgotou o tempo
        return None
    monkeypatch.setattr(fala, "_sintetizar_elevenlabs", lenta)
    assert fala.sintetizar("Oi", "whatsapp")["base64"] == base64.b64encode(b"VOICE").decode()
    assert len(chamadas) == 1
    assert fala.sintetizar("Oi de novo", "whatsapp")["base64"] == base64.b64encode(b"VOICE").decode()
    assert len(chamadas) == 1                   # na pausa: foi direto ao VoiceStudio
    relogio["t"] += 61                          # a pausa acabou: a ElevenLabs volta a ser tentada
    fala.sintetizar("Oi", "whatsapp")
    assert len(chamadas) == 2
    monkeypatch.setattr(fala, "_sintetizar_elevenlabs", original)


def test_previa_de_voz_ignora_a_pausa(reserva):
    fala._QUEDA["elevenlabs"] = float("inf")
    requests, status = reserva
    status["k1"] = 200
    assert fala.sintetizar("Oi", "whatsapp", id_voz="v-escolhida")["base64"] == "RUxFVkVO"
