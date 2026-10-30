"""A bio: linhas Campo: valor, sem documentos nem telefone, só na conta dela, com postura da Bella."""
from datetime import date

from nucleo import bella_bio as B, bella_conversa
from test_clonarvoz import _admin
from test_fluxos import _ligar_telegram, _tg

BIO = """Nome: Jefferson Costa (Arquiteto)
Nascimento: 16/01/1988, em Taguatinga DF
Estado civil: Casado com Gizele
Pai da Vitória
Profissões: Gerente de Restaurante, Marketing, Motorista de Aplicativo, Analista de Sistemas
Moro em Planaltina DF com a esposa e a filha
Casa no Lago Sul onde vive com a Bella
Cachorrinha Amore, shitzu
Minha identidade é 2576986
CPF 010.343.881-50
Celular 61 98334-7739"""


def test_validacao_recusa_documentos_telefone_e_segredos():
    for ruim in ("CPF 010.343.881-50", "Minha identidade é 2576986", "Celular 61 98334-7739", "senha do banco é abc", "ok"):
        assert B.validar(ruim)[0] is None, ruim
    assert B.validar("Nascimento: 16/01/1988")[0] == "Nascimento: 16/01/1988"      # data não é documento
    assert B.validar("Profissões: Gerente, Analista")[0]


def test_definir_guarda_so_o_que_pode(cliente):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    boas, ruins = B.definir(conta, BIO)
    assert len(boas) == 8 and len(ruins) == 3
    assert not any("2576986" in l or "010.343" in l or "98334" in l for l in B.listar(conta))


def test_idade_e_calculada_e_nao_fica_velha():
    linhas = ["Nascimento: 16/01/1988, em Taguatinga DF"]
    assert B.idade(linhas, date(2026, 10, 29)) == 38 and B.idade(linhas, date(2026, 1, 15)) == 37
    assert B.idade(["Cidade: Brasília"]) is None


def test_mesmo_campo_substitui_e_apagar_limpar(cliente):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    B.limpar(conta)
    assert B.adicionar(conta, "Cidade: Brasília")[0] and B.adicionar(conta, "Cidade: Planaltina")[0]
    assert B.listar(conta) == ["Cidade: Planaltina"]
    assert not B.adicionar(conta, "Cidade: Planaltina")[0]
    assert B.apagar(conta, 1) == "Cidade: Planaltina" and B.apagar(conta, 1) is None


def test_prompt_do_arquiteto_leva_bio_idade_postura_e_regra_da_familia(cliente):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    B.definir(conta, BIO)
    p = bella_conversa.prompt(conta, {"nivel": 0, "modo": "auto", "emocao": "alegre", "insistencias": 0, "interacoes": 0})
    assert "Bio dele" in p and "Casado com Gizele" in p and "Idade: 3" in p
    assert "convencê-lo" in p and "nunca entram em cena" in p and "2576986" not in p


def test_bio_de_uma_conta_nao_vai_para_outra(cliente):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    B.definir(conta, "Estado civil: Casado com Gizele")
    assert B.bloco_prompt(conta + 999) == ""
    assert "Gizele" not in bella_conversa.prompt(conta + 999, None)


def test_sem_bio_o_prompt_nao_muda(cliente):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    B.limpar(conta)
    assert B.bloco_prompt(conta, True) == ""


def test_comandos_pelo_chat(cliente, caixa):
    c = _admin(cliente)
    _ligar_telegram(c)
    conta = c.get("/api/auth/eu").json()["id"]
    B.limpar(conta)
    _tg(c, "/bio")
    assert "vazia" in caixa[-1][2]
    _tg(c, "/bio definir\n" + BIO)
    assert "8 linha" in caixa[-1][2] and "Não guardei" in caixa[-1][2]
    _tg(c, "/bio")
    assert "Casado com Gizele" in caixa[-1][2] and f"{B.idade(B.listar(conta))} anos" in caixa[-1][2]
    _tg(c, "/bio add CPF 01034388150")
    assert "Não guardo documentos" in caixa[-1][2]
    _tg(c, "/bio apagar 1")
    assert "Apaguei" in caixa[-1][2]
    _tg(c, "/bio limpar")
    assert "confirmo" in caixa[-1][2] and B.listar(conta)
    _tg(c, "/bio limpar confirmo")
    assert B.listar(conta) == []


def test_semente_da_bio_entra_uma_vez_so_e_nao_volta_depois_de_apagada(cliente, tmp_path):
    conta = _admin(cliente).get("/api/auth/eu").json()["id"]
    B.limpar(conta)
    from database import SessionLocal, gravar_config
    db = SessionLocal()
    gravar_config(db, f"bella_bio_semeada:{conta}", "0")
    db.close()
    arq = tmp_path / "bio.txt"
    arq.write_text("Cidade: Brasília\nCPF 01034388150\nEstado civil: Casado com Gizele\n", encoding="utf-8")
    assert B.semear_arquiteto(str(arq)) == 2 and len(B.listar(conta)) == 2        # o CPF não entra
    B.limpar(conta)
    assert B.semear_arquiteto(str(arq)) == 0 and B.listar(conta) == []             # apagou: não volta
    assert B.semear_arquiteto(str(tmp_path / "nao_existe.txt")) == 0


def test_arquivo_de_semente_do_projeto_nao_tem_dado_proibido():
    import os
    arq = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "bio_arquiteto.txt")
    linhas = [l for l in open(arq, encoding="utf-8").read().splitlines() if l.strip()]
    assert linhas and all(B.validar(l)[0] for l in linhas)
