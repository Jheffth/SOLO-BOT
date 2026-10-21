"""Ecos repetidos reutilizam a gravação sem nova síntese na ElevenLabs."""
from concurrent.futures import ThreadPoolExecutor

import config
from database import SessionLocal, gravar_config
from nucleo import fala
from test_avisos import ROT, _hora, pronto  # noqa: F401
from test_saudacoes import banco  # noqa: F401


FRASE = "O Sistema anotou."


def configurar(chave, valor):
    with SessionLocal() as db:
        gravar_config(db, chave, valor)


def eco(texto=FRASE, canal="whatsapp", **kwargs):
    return fala.sintetizar(texto, canal, tom="sussurro", **kwargs)


def test_eco_repetido_e_reinicio_nao_geram_nova_sintese(banco, monkeypatch):
    configurar(fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    primeiro = eco()
    assert primeiro and len(banco[2]) == 1
    assert "SOMBRA" in banco[2][0][1]
    assert eco() == primeiro and len(banco[2]) == 1
    monkeypatch.setattr(fala, "_estado", {"voz": None, "ultimo_erro": None})
    assert eco() == primeiro and len(banco[2]) == 1
    assert len(list(banco[4].rglob("*.mp3"))) == 1


def test_avisos_repetidos_pela_ponte_reutilizam_audio(pronto, caixa, banco, monkeypatch):
    _hora(monkeypatch, 21)
    configurar(fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    for _ in range(2):
        r = pronto.post("/interno/enviar", headers=ROT, json={
            "usuario_id": "1", "texto": FRASE, "voz": True, "tom": "sussurro",
        })
        assert r.status_code == 200 and r.json()["entregues"] == 1
    audios = [m for m in caixa if m[0] == "voz-telegram"]
    assert len(audios) == 2 and audios[0][2:] == audios[1][2:]
    assert len(banco[2]) == 1


def test_voz_do_sistema_e_perfil_da_bella_ficam_separados(banco):
    configurar(fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    bot = fala.sintetizar("Oi, jeff.", "whatsapp", guardar=True)
    sistema = eco()
    assert sistema["perfil_voz"]["voz"] == "SOMBRA"
    assert fala.perfil_ativo()["voz"] == "VOZ_A"
    assert fala.perfil_ativo("sussurro")["voz"] == "SOMBRA"
    assert fala.sintetizar("Oi, jeff.", "whatsapp", guardar=True) == bot
    assert eco() == sistema and len(banco[2]) == 2


def test_trocar_voz_e_voltar_recupera_gravacao_anterior(banco):
    configurar(fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    primeiro = eco()
    configurar(fala.CHAVE_VOZ_SISTEMA, "OUTRA")
    segundo = eco()
    assert primeiro["cache_id"] != segundo["cache_id"]
    configurar(fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    assert eco() == primeiro and len(banco[2]) == 2


def test_texto_modelo_e_ajustes_separam_as_gravacoes(banco, monkeypatch):
    primeiro = eco()
    outro_texto = eco("O Sistema observa.")
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_v4_turbo")
    outro_modelo = eco()
    monkeypatch.setitem(fala.TONS, "sussurro", {
        **fala.TONS["sussurro"], "expressivo": {"stability": .5, "similarity_boost": .75, "style": .7},
    })
    outro_ajuste = eco()
    assert len({a["cache_id"] for a in [primeiro, outro_texto, outro_modelo, outro_ajuste]}) == 4
    assert eco() == outro_ajuste and len(banco[2]) == 4


def test_cada_formato_do_canal_tem_seu_audio_reutilizavel(banco):
    mp3, opus = eco(), eco(canal="telegram")
    assert mp3["mime"] == "audio/mpeg" and opus["mime"] == "audio/ogg"
    assert mp3["cache_id"] != opus["cache_id"]
    assert eco() == mp3 and eco(canal="telegram") == opus
    assert len(banco[2]) == 2


def test_eco_da_reserva_e_reutilizado_sem_tentar_sintetizar_de_novo(banco):
    configurar(fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    banco[3]["chave-principal"] = 402
    primeiro = eco()
    assert primeiro["perfil_voz"]["voz"] == "VOZ_RESERVA"
    assert primeiro["perfil_voz"]["conta"] == "reserva"
    quantidade = len(banco[2])
    assert eco() == primeiro and len(banco[2]) == quantidade
    assert fala.perfil_ativo()["voz"] == "VOZ_A"


def test_modelo_reserva_e_reutilizado(banco, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_MODEL", "eleven_v4_turbo")
    cliente = fala.httpx.Client
    post = cliente.post

    def recusar_modelo(self, url, json, headers):
        if json["model_id"] == "eleven_v4_turbo":
            banco[2].append((headers["xi-api-key"], url, json))
            return fala.httpx.Response(403)
        return post(self, url, json, headers)

    monkeypatch.setattr(cliente, "post", recusar_modelo)
    primeiro = eco()
    assert primeiro["perfil_voz"]["modelo"] == "eleven_flash_v2_5"
    assert eco() == primeiro and len(banco[2]) == 2


def test_pedidos_simultaneos_do_mesmo_eco_so_sintetizam_uma_vez(banco):
    with ThreadPoolExecutor(max_workers=4) as executor:
        audios = list(executor.map(lambda _: eco(), range(4)))
    assert all(a and a["cache_id"] == audios[0]["cache_id"] for a in audios)
    assert len(banco[2]) == 1


def test_falha_na_sintese_nao_cria_gravacao_invalida(banco):
    banco[3].update({"chave-principal": 429, "chave-reserva": 429})
    assert eco() is None and not list(banco[4].rglob("*.mp3"))
    banco[3]["chave-principal"] = 200
    primeiro = eco()
    quantidade = len(banco[2])
    assert primeiro and eco() == primeiro and len(banco[2]) == quantidade


def test_voz_explicita_nao_altera_perfil_do_sistema_no_cache_hit(banco):
    configurar(fala.CHAVE_VOZ_SISTEMA, "SOMBRA")
    primeiro = eco()
    amostra = eco(id_voz="AMOSTRA")
    assert eco(id_voz="AMOSTRA") == amostra
    assert fala.perfil_ativo("sussurro")["voz"] == "SOMBRA"
    assert eco() == primeiro and len(banco[2]) == 2


def test_conta_manual_nao_usa_perfil_da_reserva(banco):
    banco[3]["chave-principal"] = 429
    assert eco()["perfil_voz"]["conta"] == "reserva"
    configurar(fala.CHAVE_CONTA, "principal")
    quantidade = len(banco[2])
    assert eco() is None
    assert all(p[0] == "chave-principal" for p in banco[2][quantidade:])
