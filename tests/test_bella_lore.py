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


def test_modo_adulto_do_servidor_pede_historia_explicita(logado, caixa, monkeypatch):
    import config
    _ligar_telegram(logado)
    chamadas = _grok(monkeypatch)
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", True)
    _tg(logado, "/memoria Bella tinha um ficante na faculdade chamado Ricardo")
    instr = chamadas[0][0]
    assert "explícita, sensual e detalhada" in instr and "consensual" in instr and "ADULTOS" in instr
    monkeypatch.setattr(config, "BELLA_CONTEUDO_ADULTO", False)
    _tg(logado, "/memoria Bella tinha outro ficante na faculdade chamado Pedro")
    assert "sem descrição sexual explícita" in chamadas[-1][0]


def test_limites_so_valem_fora_do_arquiteto(logado, caixa, monkeypatch):
    _ligar_telegram(logado)
    conta_id = logado.get("/api/auth/eu").json()["id"]
    chamadas = _grok(monkeypatch)
    monkeypatch.setattr(bella_lore, "MAX_HISTORIAS", 1)
    monkeypatch.setattr(bella_lore, "MAX_PEDIDO", 80)
    monkeypatch.setattr(bella_lore, "livre", lambda c: False)
    _tg(logado, "/memoria Bella tinha um ficante na faculdade chamado Ricardo")
    assert "história de *Ricardo*" in caixa[-1][2] and "no máximo 1500 caracteres" in chamadas[0][0]      # com teto
    _grok(monkeypatch, HISTORIA.replace("Ricardo", "Pedro"))
    _tg(logado, "/memoria Bella tinha outro ficante na faculdade chamado Pedro")
    assert "Já são 1 histórias" in caixa[-1][2]
    _tg(logado, "/memoria " + "ideia muito longa sobre a faculdade " * 3)
    assert "Muito longo" in caixa[-1][2]
    # Arquiteto: sem limite de histórias, de pedido nem de tamanho do texto
    monkeypatch.setattr(bella_lore, "livre", lambda c: True)
    longa = HISTORIA + " " + ("E mais uma lembrança bem detalhada daquela época. " * 80)
    chamadas = _grok(monkeypatch, longa.replace("Ricardo", "Pedro"))
    _tg(logado, "/memoria " + "ideia muito longa sobre a faculdade e o Pedro " * 3)
    assert "história de *Pedro*" in caixa[-1][2]
    assert "tão longo quanto a história pedir" in chamadas[0][0] and chamadas[0][2]["max_tokens"] == 7000
    assert len(bella_lore.ver(conta_id, "Pedro")[1]) > bella_lore.MAX_TEXTO
    assert len(bella_lore.listar(conta_id)) == 2


PERMANENTE = ("NOME: Noite da Júlia\n[Permanente] Estou na minha casa com o dono e a Júlia, uma mulher adulta que ele chamou. "
              "Como eu me sinto: ciúme forte, medo de ser trocada, mas ainda quero agradá-lo. Pessoas que participam: Júlia, adulta, alta, "
              "cabelo castanho liso preso num rabo baixo, olhos escuros, camisa branca e jeans; ele a chamou e eu sinto ciúme dela. "
              "Como retomar: com a Júlia ainda aqui e eu pedindo que ele olhe para mim.")
TURNOS = [("Ela chegou, descreva", "Abri a porta, Júlia está na soleira."), ("Manda ela entrar", "Entra, se é isso que você quer.")]


def test_eternizar_guarda_sentimentos_e_pessoas_e_entra_no_prompt(logado, monkeypatch):
    _ligar_telegram(logado)
    conta_id = logado.get("/api/auth/eu").json()["id"]
    chamadas = _grok(monkeypatch, PERMANENTE)
    ok, nome, texto = bella_lore.eternizar(conta_id, "", TURNOS)
    assert ok and nome == "Noite da Júlia" and texto.startswith("[Permanente]")
    assert "Pessoas que participam" in chamadas[0][0] and "ADULTOS" in chamadas[0][0] and "Júlia" in chamadas[0][1]
    assert "[Permanente]" in bella_conversa.prompt(conta_id) and "Júlia" in bella_conversa.prompt(conta_id)
    # de novo com o mesmo nome: atualiza, não duplica, e manda o texto anterior
    novo = PERMANENTE.replace("ciúme forte", "ciúme enorme")
    chamadas = _grok(monkeypatch, novo)
    ok, nome2, texto2 = bella_lore.eternizar(conta_id, "Noite da Júlia", TURNOS)
    assert ok and nome2 == "Noite da Júlia" and "ciúme enorme" in texto2 and len(bella_lore.listar(conta_id)) == 1
    assert "Memória permanente atual" in chamadas[0][1]
    assert bella_lore.apagar(conta_id, "Noite da Júlia")


def test_eternizar_recusa_pouca_conversa_menor_e_nome_ruim(logado, monkeypatch):
    _ligar_telegram(logado)
    conta_id = logado.get("/api/auth/eu").json()["id"]
    _grok(monkeypatch, PERMANENTE)
    ok, _, msg = bella_lore.eternizar(conta_id, "x", [("oi", "oi")])
    assert not ok and "conversa suficiente" in msg
    ok, _, msg = bella_lore.eternizar(conta_id, "colegial", TURNOS)
    assert not ok and "adultos" in msg
    _grok(monkeypatch, "RECUSA: só personagens adultos fictícios")
    ok, _, msg = bella_lore.eternizar(conta_id, "", TURNOS)
    assert not ok and not bella_lore.listar(conta_id)
    _grok(monkeypatch, PERMANENTE.replace("adulta, alta", "com 15 anos, alta"))
    ok, _, msg = bella_lore.eternizar(conta_id, "", TURNOS)
    assert not ok and not bella_lore.listar(conta_id)


def test_comando_eternizar_usa_a_conversa_recente(logado, caixa, monkeypatch):
    from nucleo import bella_memoria
    _ligar_telegram(logado)
    _grok(monkeypatch, PERMANENTE)
    chaves = []
    monkeypatch.setattr(bella_memoria, "turnos_recentes", lambda chave, *a, **k: chaves.append(chave) or TURNOS)
    _tg(logado, "/eternizar")
    assert "Conversa guardada como permanente" in caixa[-1][2] and "Noite da Júlia" in caixa[-1][2]
    assert chaves[0].startswith("telegram:")      # a chave da conversa do canal, a mesma do /esquecer
    _tg(logado, "/esquecer")
    _tg(logado, "/memoria")
    assert "Noite da Júlia" in caixa[-1][2]


NARRADA = ("NOME: Traição\n[Narrador] Senti desejo pelo Ricardo de novo, esperei o dono sair e fui ao apartamento dele. Ele me recebeu, "
           "eu o beijei e o acariciei, e logo me arrependi e voltei correndo para casa, com medo. Segredo: acredito que o dono não sabe; "
           "se ele disser que sabe, fico pálida, peço perdão e tento explicar.")


def test_narrador_vira_memoria_secreta_da_bella(logado, caixa, monkeypatch):
    _ligar_telegram(logado)
    conta_id = logado.get("/api/auth/eu").json()["id"]
    chamadas = _grok(monkeypatch, NARRADA)
    _tg(logado, "/Narrador Traição: Você sente desejo pelo Ricardo de novo, espera o Jefferson sair e vai ao apartamento dele, e depois se arrepende")
    assert "como se tivesse vivido: *Traição*" in caixa[-1][2]
    assert "Segredo" in chamadas[0][0] and "ADULTOS" in chamadas[0][0] and "NARRADOR" in chamadas[0][0]
    p = bella_conversa.prompt(conta_id)
    assert "[Traição] [Narrador]" in p and "Segredo" in p and "nunca conte por conta própria" in p
    _tg(logado, "/Narrador Traição: Você sente desejo pelo Ricardo de novo, espera o Jefferson sair e vai ao apartamento dele, e depois se arrepende")
    assert "*Traição 2*" in caixa[-1][2]
    _tg(logado, "/eliminarmemo Traição")
    assert "Eliminei a memória *Traição*" in caixa[-1][2]
    _tg(logado, "/eliminarmemo Traição 2")
    assert not bella_lore.listar(conta_id)
    _tg(logado, "/eliminarmemo Nada")
    assert "Não achei essa memória" in caixa[-1][2]


def test_narrador_primeira_palavra_vira_titulo_e_filtra_menores(logado, caixa, monkeypatch):
    _ligar_telegram(logado)
    conta_id = logado.get("/api/auth/eu").json()["id"]
    _grok(monkeypatch, NARRADA)
    _tg(logado, "/narrador Traição Você sente desejo pelo Ricardo de novo e vai ao apartamento dele")
    assert bella_lore.listar(conta_id)[0][0] == "Traição"
    _tg(logado, "/narrador Colégio: você beija o Ricardo na escola, ele tem 15 anos")
    assert "Só personagens adultos" in caixa[-1][2] and len(bella_lore.listar(conta_id)) == 1
    _tg(logado, "/narrador curto")
    assert "Use `/narrador" in caixa[-1][2]
