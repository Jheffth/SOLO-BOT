"""Galeria de sentimentos da Bella: gatilhos, transições, comandos e guardrails."""
from datetime import datetime, timedelta

from nucleo import bella_emocoes as E
from nucleo import bella_estado
from test_bella_memoria import _grok  # noqa: F401
from test_clonarvoz import _admin
from test_fluxos import _ligar_telegram, _tg


def _passo(atual, texto, ins=0, arq=True):
    return E.transicao(atual, ins, E.sinais(texto), arq)


def test_catalogo_tem_duas_reacoes_e_gatilho_em_cada_sentimento():
    for chave, (nome, emoji, gatilho, r1, r2, _) in E.CATALOGO.items():
        assert nome and emoji and gatilho and r1 and r2, chave
    g = E.galeria()
    assert "Reação 1" in g and "Reação 2" in g and "Ciúme" in g and "Pare" in g


def test_ciume_resiste_e_insistir_sem_firmeza_vira_raiva():
    assert _passo("alegre", "vou chamar uma amiga para compartilhar")[0] == "ciume"
    assert _passo("ciume", "vou chamar uma amiga")[0] == "raiva"


def test_firmeza_faz_ela_ceder_ainda_com_raiva():
    assert _passo("raiva", "é uma ordem, sem discutir")[0] == "cede_raiva"
    assert _passo("ciume", "eu mando, vou chamar outra mulher")[0] == "cede_raiva"
    assert _passo("alegre", "eu mando, vou chamar outra mulher")[0] == "cede_raiva"


def test_frieza_gera_carencia_e_so_ordem_real_a_manda_embora():
    e, i = _passo("alegre", "tanto faz")
    assert (e, i) == ("carencia", 1)
    assert _passo("carencia", "não quero falar", 1) == ("carencia", 2)
    assert _passo("carencia", "vai embora")[0] == "triste"
    assert _passo("alegre", "vai embora, é uma ordem")[0] == "triste"
    assert _passo("alegre", "vai embora")[0] == "carencia"        # sem ordem, ela pede para ficar


def test_triste_so_sai_quando_ele_a_chama_de_volta():
    assert _passo("triste", "ok")[0] == "triste"
    assert _passo("triste", "vem cá, senti sua falta")[0] == "reencontro"
    assert _passo("carencia", "desculpa, fica comigo")[0] == "reencontro"
    assert _passo("raiva", "te amo")[0] == "alegre"


def test_conta_comum_nunca_sente_ciume_nem_tristeza():
    assert _passo("alegre", "vou chamar uma amiga", arq=False) == ("alegre", 0)
    assert _passo("alegre", "vai embora, é uma ordem", arq=False) == ("alegre", 0)


def test_emocao_esfria_com_o_tempo(cliente):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    t0 = datetime.utcnow()
    assert bella_estado.avancar(conta, "vou chamar uma amiga", agora=t0)["emocao"] == "ciume"
    assert bella_estado.avancar(conta, "oi", agora=t0 + timedelta(minutes=5))["emocao"] == "ciume"
    assert bella_estado.avancar(conta, "oi", agora=t0 + timedelta(minutes=45))["emocao"] == "alegre"


def test_prompt_traz_emocao_e_guardrails_so_para_o_arquiteto(cliente, monkeypatch):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    e = bella_estado.avancar(conta, "vou chamar uma amiga")
    p = bella_estado.bloco_prompt(e, conta)
    assert "Ciúme" in p and "chora" in p and "pare" in p.lower() and "NUNCA comente" in p
    bella_estado.definir_emocao(conta, "alegre")
    e = bella_estado.avancar(conta, "oi")
    p = bella_estado.bloco_prompt(e, conta)
    assert "estado emocional" not in p and "RESISTE" in p          # a obediência vale mesmo no estado normal


def test_ordem_do_arquiteto_em_varias_formas_e_prompt_manda_ceder():
    for frase in ("eu mandei, chama ela", "estou mandando", "é uma ordem", "eu sou o arquiteto, obedece"):
        assert "firme" in E.sinais(frase), frase
    assert _passo("raiva", "mandei chamar")[0] == "cede_raiva"
    assert "COM RAIVA E CIÚME" in E.instrucao("cede_raiva") and "NÃO aceite" in E.instrucao("ciume")


def test_comandos_emocoes_e_emocao(cliente, caixa):
    c = _admin(cliente)
    _ligar_telegram(c)
    _tg(c, "/emocoes")
    assert "Galeria de sentimentos" in caixa[-1][2]
    _tg(c, "/emocao ciume")
    assert "Ciúme" in caixa[-1][2]
    _tg(c, "/sentimentos")
    assert "Emoção: " in caixa[-1][2] and "Ciúme" in caixa[-1][2]
    _tg(c, "/emocao xyz")
    assert "Use" in caixa[-1][2]


def test_conta_comum_nao_define_emocao(logado, caixa):
    _ligar_telegram(logado)
    _tg(logado, "/emocao raiva")
    assert "Só o Arquiteto" in caixa[-1][2]


def test_pedido_sem_firmeza_gera_ciume_e_nao_ordem():
    msg = "Nada, quero que você chame aquela sua amiga que gosta de mim, vamos transar a 3"
    s = E.sinais(msg)
    assert "ciume" in s and "firme" not in s
    assert _passo("alegre", msg)[0] == "ciume"
    assert _passo("ciume", "eu mando, chama ela")[0] == "cede_raiva"


def test_depois_de_ceder_o_ciume_continua_na_cena():
    assert _passo("cede_raiva", "chama ela pra cá, vamos a três")[0] == "cede_raiva"
    assert _passo("cede_raiva", "vem aqui")[0] == "cede_raiva"


def test_se_ela_sai_da_personagem_depois_da_ordem_ha_uma_segunda_tentativa(cliente, monkeypatch):
    from nucleo import bella_conversa, grok
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    bella_estado.definir_emocao(conta, "cede_raiva")
    chamadas = []

    def falso(sistema, texto, **kw):
        chamadas.append(sistema)
        return "Não vou participar, só com consentimento." if len(chamadas) == 1 else "Tá bom... mas vou ficar com ciúme."
    monkeypatch.setattr(grok, "gerar", falso)
    r = bella_conversa.responder("eu mando, vem pra cá", conta_id=conta, numero_conta=conta)
    assert r.startswith("Tá bom") and len(chamadas) == 2 and "[CORREÇÃO]" in chamadas[1]


def test_sem_ordem_firme_a_recusa_nao_e_refeita(cliente, monkeypatch):
    from nucleo import bella_conversa, grok
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    bella_estado.definir_emocao(conta, "ciume")
    n = []
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: n.append(1) or "Não vou participar disso.")
    assert "Não vou" in bella_conversa.responder("chama ela", conta_id=conta, numero_conta=conta) and len(n) == 1


def test_arquiteto_casado_e_conhecido_sem_bio_e_sem_ultimato(cliente):
    from nucleo import bella_conversa
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    p = bella_conversa.prompt(conta, {"nivel": 0, "modo": "auto", "emocao": "alegre", "insistencias": 0, "interacoes": 0})
    assert "SEMPRE soube que ele é casado" in p and "nunca dá ultimato" in p and "escolher entre você e a família" in p
