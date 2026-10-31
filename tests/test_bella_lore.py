"""Histórias da Bella (/memoria <ideia>): o Grok desenvolve, fica sob o nome do personagem e dá para ver, editar e apagar."""
from nucleo import bella_conversa, bella_lore, grok
from test_fluxos import _ligar_telegram, _tg

HISTORIA = ("NOME: Ricardo\nConheci o Ricardo no segundo ano de Design, na festa de calouros do campus, e logo viramos inseparáveis. "
            "Passávamos as noites na república dele, entre cervejas baratas e beijos demorados. Eu era apaixonada, ele sempre dizia que não queria "
            "compromisso, e o fim veio quando ele mudou de cidade. Ainda sinto um aperto quando lembro dele.")


def _grok(monkeypatch, saida=HISTORIA):
    chamadas = []
    monkeypatch.setattr(grok, "gerar", lambda instr, texto, **kw: chamadas.append((instr, texto, kw)) or saida)
    return chamadas


def test_cria_ve_edita_e_apaga_a_historia_pelo_nome(logado, caixa, monkeypatch):
    _ligar_telegram(logado)
    chamadas = _grok(monkeypatch)
    _tg(logado, "/memória Bella tinha um ficante na faculdade de nome Ricardo, eles sempre transavam, ela era apaixonada por ele")
    assert "história de *Ricardo*" in caixa[-1][2] and "república" in caixa[-1][2]
    assert "ADULTOS" in chamadas[0][0] and "sem descrição sexual explícita" in chamadas[0][0]
    _tg(logado, "/memoria")
    t = caixa[-1][2]
    assert "Histórias da Bella" in t and "*Ricardo*" in t
    _tg(logado, "/memoria ver ricardo")
    assert "república" in caixa[-1][2]
    novo = HISTORIA.replace("mudou de cidade", "traiu a confiança dela")
    _grok(monkeypatch, novo)
    _tg(logado, "/memoria editar Ricardo ele a traiu em vez de mudar de cidade")
    assert "traiu a confiança" in caixa[-1][2]
    _tg(logado, "/memoria texto Ricardo " + "Texto escrito por mim, com mais de vinte caracteres.")
    _tg(logado, "/memoria ver Ricardo")
    assert "Texto escrito por mim" in caixa[-1][2]
    _tg(logado, "/memoria apagar Ricardo")
    assert "Apaguei a história de *Ricardo*" in caixa[-1][2]
    _tg(logado, "/memoria")
    assert "ainda vazia" in caixa[-1][2]


def test_lembranca_numerada_e_editada_e_esquecer_nome_apaga_historia(logado, caixa, monkeypatch):
    _ligar_telegram(logado)
    _grok(monkeypatch)
    _tg(logado, "/lembrar gosto de café sem açúcar")
    _tg(logado, "/memoria editar 1 gosto de café com açúcar")
    assert "Lembrança atualizada" in caixa[-1][2]
    _tg(logado, "/memoria")
    assert "1. gosto de café com açúcar" in caixa[-1][2]
    _tg(logado, "/memoria Bella teve um ficante na faculdade chamado Ricardo")
    _tg(logado, "/esquecer Ricardo")
    assert "Apaguei a história de *Ricardo*" in caixa[-1][2]
    _tg(logado, "/esquecer tudo")                       # as lembranças, não as histórias da Bella
    assert "lembrança" in caixa[-1][2]


def test_recusa_menor_e_saida_ruim_e_nada_e_guardado(logado, caixa, monkeypatch):
    _ligar_telegram(logado)
    chamadas = _grok(monkeypatch)
    _tg(logado, "/memoria Bella tinha um ficante no colégio com 16 anos, o Ricardo")
    assert "adultos" in caixa[-1][2] and not chamadas
    _grok(monkeypatch, "RECUSA: só personagens adultos")
    _tg(logado, "/memoria Bella tinha um ficante na faculdade chamado Pedro")
    assert "Não guardei" in caixa[-1][2]
    _grok(monkeypatch, "sem formato nenhum")
    _tg(logado, "/memoria Bella tinha um ficante na faculdade chamado Pedro")
    assert "fora do formato" in caixa[-1][2]
    _tg(logado, "/memoria curto")
    assert "Conte a ideia" in caixa[-1][2]
    _tg(logado, "/memoria")
    assert "ainda vazia" in caixa[-1][2]


def test_a_bella_usa_as_historias_no_prompt_e_pausar_a_memoria_as_esconde(logado, caixa, monkeypatch):
    _ligar_telegram(logado)
    conta_id = logado.get("/api/auth/eu").json()["id"]
    _grok(monkeypatch)
    _tg(logado, "/memoria Bella tinha um ficante na faculdade chamado Ricardo")
    assert "Sua vida antes dele" in bella_conversa.prompt(conta_id) and "[Ricardo]" in bella_conversa.prompt(conta_id)
    _tg(logado, "/memoria desligar")
    assert "[Ricardo]" not in bella_conversa.prompt(conta_id)
    _tg(logado, "/memoria ligar")
    assert bella_lore.listar(conta_id)[0][0] == "Ricardo"
    _tg(logado, "/memoria apagar tudo")
    assert "confirmo" in caixa[-1][2] and bella_lore.listar(conta_id)
    _tg(logado, "/memoria apagar tudo confirmo")
    assert not bella_lore.listar(conta_id)
