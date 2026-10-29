"""Memória de longo prazo da Bella: /lembrar, /memoria, /esquecer, o prompt e o histórico no banco."""
import config
from nucleo import bella_conversa, bella_memoria, grok
from test_fluxos import _ligar_telegram, _tg


def _conta_id(logado):
    return logado.get("/api/auth/eu").json()["id"]


def _grok(monkeypatch):
    chamadas = []
    monkeypatch.setattr(grok, "gerar", lambda instr, texto, **kw: chamadas.append((instr, texto, kw)) or f"bella:{texto}")
    bella_conversa._MEMORIA.clear()
    return chamadas


def test_lembrar_memoria_e_esquecer_pelo_chat(logado, caixa):
    _ligar_telegram(logado)
    _tg(logado, "/memoria")
    assert "ainda vazia" in caixa[-1][2]
    _tg(logado, "/lembrar gosto de café sem açúcar")
    assert "Guardei" in caixa[-1][2] and "café sem açúcar" in caixa[-1][2]
    _tg(logado, "/lembrar a filha se chama Vivi")
    _tg(logado, "/memoria")
    t = caixa[-1][2]
    assert "2 lembrança" in t and "1. gosto de café sem açúcar" in t and "2. a filha se chama Vivi" in t
    _tg(logado, "/esquecer 1")
    assert "Esqueci" in caixa[-1][2] and "café" in caixa[-1][2]
    _tg(logado, "/memoria")
    assert "1. a filha se chama Vivi" in caixa[-1][2] and "café" not in caixa[-1][2]
    _tg(logado, "/esquecer 9")
    assert "Não achei" in caixa[-1][2]
    _tg(logado, "/esquecer tudo")
    assert "1 lembrança" in caixa[-1][2]
    _tg(logado, "/memoria")
    assert "ainda vazia" in caixa[-1][2]


def test_esquecer_sem_numero_so_apaga_a_conversa(logado, caixa):
    _ligar_telegram(logado)
    _tg(logado, "/lembrar sou de Brasília")
    _tg(logado, "/esquecer")
    assert "esqueci o que conversamos" in caixa[-1][2]
    _tg(logado, "/memoria")
    assert "sou de Brasília" in caixa[-1][2]


def test_lembrar_recusa_vazio_repetido_longo_e_segredos(logado, caixa):
    _ligar_telegram(logado)
    for texto, trecho in (("", "Diga o que devo lembrar"), ("x" * 301, "Muito longo"),
                          ("minha senha do banco é 1234", "senhas"), ("cartão 4111 1111 1111 1111", "cartão"),
                          ("meu cpf é 123.456.789-09", "documentos")):
        _tg(logado, f"/lembrar {texto}".strip())
        assert trecho in caixa[-1][2], texto
    _tg(logado, "/lembrar Adoro   Chocolate")
    _tg(logado, "/lembrar adoro chocolate")
    assert "Já tenho" in caixa[-1][2]
    assert bella_memoria.listar(_conta_id(logado)) == ["Adoro Chocolate"]


def test_limite_de_lembrancas(logado, caixa, monkeypatch):
    monkeypatch.setattr(config, "BELLA_MEMORIA_FATOS_MAX", 5)
    _ligar_telegram(logado)
    for i in range(5):
        _tg(logado, f"/lembrar fato número {i}")
    _tg(logado, "/lembrar fato extra")
    assert "cheia" in caixa[-1][2] and len(bella_memoria.listar(_conta_id(logado))) == 5


def test_a_bella_recebe_as_lembrancas_no_prompt(logado, caixa, monkeypatch):
    chamadas = _grok(monkeypatch)
    _ligar_telegram(logado)
    _tg(logado, "/lembrar a filha se chama Vivi")
    _tg(logado, "/bella oi")
    prompt = chamadas[-1][0]
    assert "Memórias" in prompt and "- a filha se chama Vivi" in prompt
    assert "até 900 caracteres" in prompt                    # o resto do prompt segue intacto


def test_memoria_desligada_nao_vai_ao_prompt_mas_continua_guardada(logado, caixa, monkeypatch):
    chamadas = _grok(monkeypatch)
    _ligar_telegram(logado)
    _tg(logado, "/lembrar gosto de jazz")
    _tg(logado, "/memoria desligar")
    assert "desligada" in caixa[-1][2]
    _tg(logado, "/bella oi")
    assert "Memórias" not in chamadas[-1][0] and "jazz" not in chamadas[-1][0]
    _tg(logado, "/memoria")
    assert "desligada" in caixa[-1][2] and "gosto de jazz" in caixa[-1][2]
    _tg(logado, "/memoria ligar")
    _tg(logado, "/bella oi de novo")
    assert "- gosto de jazz" in chamadas[-1][0]


def test_sem_lembrancas_o_prompt_e_o_de_sempre(logado, monkeypatch):
    conta = _conta_id(logado)
    assert "Memórias" not in bella_conversa.prompt(conta)
    assert bella_memoria.bloco_prompt(conta) == "" and bella_memoria.bloco_prompt(None) == ""


def test_bloco_respeita_o_limite_e_prefere_as_mais_recentes(logado):
    conta = _conta_id(logado)
    for i in range(40):
        ok, _ = bella_memoria.adicionar(conta, f"lembrança {i:02d} " + "x" * 60)
        assert ok
    bloco = bella_memoria.bloco_prompt(conta)
    assert len(bloco) <= bella_memoria.BLOCO_MAX + 2
    assert "lembrança 39" in bloco and "lembrança 00" not in bloco
    assert bloco.index("lembrança 38") < bloco.index("lembrança 39")      # ordem natural


def test_lembrancas_sao_por_conta(cliente, caixa):
    cliente.post("/api/auth/cadastro", json={"nome": "Ana", "usuario": "ana", "email": "ana@solo.dev", "senha": "senha-forte-1"})
    ana = cliente.get("/api/auth/eu").json()["id"]
    bella_memoria.adicionar(ana, "segredo da Ana")
    assert bella_memoria.listar(ana + 1) == []
    assert bella_memoria.bloco_prompt(ana + 1) == ""


def test_historico_sobrevive_ao_reinicio_do_servidor(logado, monkeypatch):
    monkeypatch.setattr(config, "BELLA_HISTORICO_PERSISTENTE", True)
    monkeypatch.setattr(config, "BELLA_MEMORIA_TURNOS", 3)
    monkeypatch.setattr(config, "BELLA_MEMORIA_MINUTOS", 30)
    chamadas = _grok(monkeypatch)
    bella_conversa.responder("primeira", "telegram:9")
    bella_conversa.responder("segunda", "telegram:9")
    bella_conversa._MEMORIA.clear()                           # "reiniciou"
    bella_conversa.responder("terceira", "telegram:9")
    assert chamadas[-1][2]["historico"] == [("user", "primeira"), ("assistant", "bella:primeira"),
                                            ("user", "segunda"), ("assistant", "bella:segunda")]
    bella_conversa.esquecer("telegram:9")
    bella_conversa._MEMORIA.clear()
    assert bella_conversa._historico("telegram:9") == []      # esquecer apaga também do banco


def test_historico_antigo_e_podado(logado, monkeypatch):
    from datetime import datetime, timedelta
    import database
    monkeypatch.setattr(config, "BELLA_HISTORICO_PERSISTENTE", True)
    monkeypatch.setattr(config, "BELLA_HISTORICO_DIAS", 7)
    db = database.SessionLocal()
    db.add(database.BellaTurno(chave="x:1", usuario="velho", bella="velho", criado_em=datetime.utcnow() - timedelta(days=8)))
    db.commit()
    db.close()
    bella_memoria.gravar_turno("x:2", "novo", "novo")
    db = database.SessionLocal()
    try:
        assert [t.usuario for t in db.query(database.BellaTurno).all()] == ["novo"]
    finally:
        db.close()


def test_falha_do_banco_nao_derruba_a_conversa(logado, monkeypatch):
    chamadas = _grok(monkeypatch)
    monkeypatch.setattr(bella_memoria, "listar", lambda c: (_ for _ in ()).throw(RuntimeError("banco fora")))
    assert bella_conversa.responder("oi", "telegram:1", numero_conta=_conta_id(logado)) == "bella:oi"
    assert "Memórias" not in chamadas[-1][0]


# ── Identidade, sentimentos e termômetro ─────────────────────────
from datetime import datetime, timedelta  # noqa: E402

from nucleo import bella_estado  # noqa: E402
from test_clonarvoz import _admin  # noqa: E402


def test_classificar_graus():
    c = bella_estado.classificar
    assert c("bom dia, como foi o dia?") == 0
    assert c("quero um beijo seu") == 1
    assert c("você de lingerie, nua") == 2
    assert c("quero transar com você") == 3
    assert c("fala como uma putinha") == 4
    assert c("me amarra e domina") == 5
    assert c("QUERO TRANSAR") == 3 and c("tesão") == 1               # sem acento e sem maiúsculas
    assert c("computador custa") == 0 and c("cultura") == 0          # "cu" só vale como palavra


def test_termometro_sobe_rapido_e_esfria_devagar(cliente, monkeypatch):
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", True)
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    n = lambda t: bella_estado.avancar(conta, t)["nivel"]
    assert n("oi") == 0
    assert n("quero transar com você") == 2          # no máximo dois degraus por mensagem
    assert n("quero transar com você") == 3
    assert n("e o tempo hoje?") == 3                 # uma mensagem calma não esfria
    assert n("e o tempo hoje?") == 2                 # duas esfriam um degrau
    assert n("beijo") == 2 and n("beijo") == 1       # com graus menores, esfria um degrau a cada duas mensagens


def test_teto_sem_conteudo_adulto(cliente, monkeypatch):
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", False)
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    for _ in range(4):
        e = bella_estado.avancar(conta, "me amarra e domina, quero transar")
    assert e["nivel"] == 2
    assert bella_estado.definir_fixa(conta, 5) == 2


def test_so_o_arquiteto_fixa_a_temperatura(cliente, caixa, monkeypatch):
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", True)
    c = _admin(cliente)
    _ligar_telegram(c)
    _tg(c, "/temperatura")
    assert "Normal" in caixa[-1][2] and "automática" in caixa[-1][2] and "fixa a temperatura" in caixa[-1][2]
    _tg(c, "/temperatura explicita")
    assert "Fixei" in caixa[-1][2] and "[Explícita]" in caixa[-1][2] and "fixada pelo Arquiteto" in caixa[-1][2]
    _tg(c, "/temperatura vulgar")
    assert "[Explícita Vulgar]" in caixa[-1][2]
    _tg(c, "/temperatura banana")
    assert "Não conheço" in caixa[-1][2]
    _tg(c, "/temperatura auto")
    assert "automático" in caixa[-1][2]


def test_conta_comum_nao_fixa_temperatura(logado, caixa):
    _ligar_telegram(logado)
    _tg(logado, "/temperatura quente")
    assert "Só o Arquiteto" in caixa[-1][2]
    _tg(logado, "/temperatura")
    assert "fixa a temperatura" not in caixa[-1][2]
    _tg(logado, "/temperatura auto")
    assert "automático" in caixa[-1][2]


def test_temperatura_fixa_vai_ao_prompt_e_nao_muda_com_a_conversa(cliente, caixa, monkeypatch):
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", True)
    chamadas = _grok(monkeypatch)
    c = _admin(cliente)
    _ligar_telegram(c)
    _tg(c, "/temperatura quente")
    _tg(c, "/bella quero transar com você agora")
    prompt = chamadas[-1][0]
    assert "[Quente]" in prompt and "fixada pelo Arquiteto" in prompt and "Explícita" not in prompt.split("Temperatura da conversa")[1][:80]


def test_arquiteto_e_reconhecido_e_os_limites_fixos_continuam(cliente, caixa, monkeypatch):
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", True)
    chamadas = _grok(monkeypatch)
    c = _admin(cliente)
    _ligar_telegram(c)
    _tg(c, "/bella oi")
    p = chamadas[-1][0]
    assert "o Arquiteto: quem te criou" in p and "apaixonada" in p and "respeito, admiração" in p
    assert "sem cobrar nem culpar" not in p                              # primeira conversa: sem saudade
    # os limites fixos seguem no prompt
    for limite in ("menores de 18 anos", "consentimento", "exclusividade", "pare"):
        assert limite in p


def test_conta_comum_nao_recebe_a_identidade_de_arquiteto(logado, caixa, monkeypatch):
    chamadas = _grok(monkeypatch)
    _ligar_telegram(logado)
    _tg(logado, "/bella oi")
    assert "quem te criou" not in chamadas[-1][0] and "Temperatura da conversa agora: [Normal]" in chamadas[-1][0]


def test_saudade_depois_de_dias_sem_falar(cliente):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    antes = datetime.utcnow() - timedelta(days=4)
    bella_estado.avancar(conta, "oi", agora=antes)
    e = bella_estado.avancar(conta, "voltei")
    assert e["dias_sem_falar"] == 4 and bella_estado.saudade(4) == "muita" and bella_estado.saudade(1) == "um pouco de"
    texto = bella_estado.descricao_sentimentos(e, True, "Jefferson")
    assert "saudade" in texto and "sem cobrar nem culpar" in texto and "Jefferson" in texto


def test_carinho_cresce_e_parte_mais_alto_para_o_arquiteto():
    assert bella_estado.carinho(0, True) == 80 and bella_estado.carinho(0, False) == 20
    assert bella_estado.carinho(50, True) == 90 and bella_estado.carinho(5000, True) == 100


def test_sentimentos_pelo_chat(cliente, caixa):
    c = _admin(cliente)
    _ligar_telegram(c)
    _tg(c, "/sentimentos")
    t = caixa[-1][2]
    assert "Arquiteto" in t and "Carinho: 80/100" in t and "Saudade: nenhuma" in t and "Temperatura" in t


def test_falha_do_estado_nao_derruba_a_conversa(logado, monkeypatch):
    _grok(monkeypatch)
    monkeypatch.setattr(bella_estado, "situacao", lambda c: (_ for _ in ()).throw(RuntimeError("banco fora")))
    assert bella_conversa.responder("oi", "telegram:1", numero_conta=_conta_id(logado)) == "bella:oi"
