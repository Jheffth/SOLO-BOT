"""O prompt gerado pela Bella vai sozinho para o Solo Prompts, sem nunca atrapalhar a resposta."""
from types import SimpleNamespace
import pytest
from nucleo import acervo_prompts, modulos, roteador


MOD = modulos.Modulo(chave="prompts", nome="Solo Prompts", emoji="📚", cor="#fff", descricao="", url="http://solo_prompts:8000", token="t", painel="")


@pytest.fixture(autouse=True)
def _sem_grok(monkeypatch):
    from nucleo import grok
    monkeypatch.setattr(grok, "gerar", lambda *a, **k: None)      # sem rede: cai no título de reserva


def _sincrono(monkeypatch):
    class Fio:
        def __init__(self, target, args=(), **k):
            self.alvo, self.args = target, args
        def start(self):
            self.alvo(*self.args)
    monkeypatch.setattr(acervo_prompts.threading, "Thread", Fio)


def _conta(vinculado=True):
    sistemas = [SimpleNamespace(app="prompts", usuario_id="7")] if vinculado else []
    return SimpleNamespace(id=1, sistemas=sistemas, prompt_suave=False)


def test_monta_corpo_com_categoria_titulo_e_limites():
    c = acervo_prompts.montar("roupa", "vestido preto", "x" * 9000, "7")
    assert c["categoria"] == "roupa" and c["origem"] == "bella" and c["usuario_id"] == "7"
    assert c["titulo"].startswith("Roupa · vestido preto") and len(c["texto"]) == 8000
    assert acervo_prompts.montar("ficha", "", "Crie uma prancha\nmais", "7")["categoria"] == "ficha"


def test_salva_quando_conta_esta_ligada(monkeypatch):
    _sincrono(monkeypatch)
    enviados = []
    monkeypatch.setattr(modulos, "por_chave", lambda k: MOD)
    monkeypatch.setattr(modulos, "chamar", lambda mod, rota, corpo: enviados.append((rota, corpo)) or {})
    assert acervo_prompts.salvar_em_segundo_plano(_conta(), "modelo", "morena", "texto do prompt") is True
    assert enviados[0][0] == "prompts" and enviados[0][1]["categoria"] == "modelo" and enviados[0][1]["usuario_id"] == "7"


def test_nao_envia_sem_vinculo_sem_modulo_ou_sem_texto(monkeypatch):
    _sincrono(monkeypatch)
    monkeypatch.setattr(modulos, "chamar", lambda *a: (_ for _ in ()).throw(AssertionError("não devia enviar")))
    monkeypatch.setattr(modulos, "por_chave", lambda k: MOD)
    assert acervo_prompts.salvar_em_segundo_plano(_conta(False), "realismo", "x", "texto") is False
    assert acervo_prompts.salvar_em_segundo_plano(_conta(), "realismo", "x", "  ") is False
    monkeypatch.setattr(modulos, "por_chave", lambda k: None)
    assert acervo_prompts.salvar_em_segundo_plano(_conta(), "realismo", "x", "texto") is False
    assert acervo_prompts.salvar_em_segundo_plano(SimpleNamespace(id=1), "realismo", "x", "texto") is False


def test_falha_do_solo_prompts_nao_derruba_a_bella(monkeypatch):
    _sincrono(monkeypatch)
    monkeypatch.setattr(modulos, "por_chave", lambda k: MOD)
    def falha(*a):
        raise modulos.ErroModulo("fora do ar")
    monkeypatch.setattr(modulos, "chamar", falha)
    assert acervo_prompts.salvar_em_segundo_plano(_conta(), "realismo", "x", "texto") is True


def test_prompt_responder_salva_o_que_entregou(monkeypatch):
    from nucleo import prompts_bella
    chamadas = []
    monkeypatch.setattr(prompts_bella, "criar", lambda *a, **k: "PROMPT PRONTO")
    monkeypatch.setattr(roteador, "_registrar", lambda *a, **k: None)
    monkeypatch.setattr(acervo_prompts, "salvar_em_segundo_plano", lambda conta, cat, pedido, texto: chamadas.append((cat, pedido, texto)))
    r = roteador._prompt_responder(None, _conta(), "telegram", "bar à noite", "pose")
    assert chamadas == [("pose", "bar à noite", "PROMPT PRONTO")] and r.mensagens[-1]["prompt"] is True


def test_bella_exe_conversa_salva_o_prompt_no_acervo(monkeypatch):
    """O Bella.exe usa /api/bella/conversa, não o roteador: o salvamento também tem que valer aqui."""
    from nucleo import prompts_bella as pb
    from routers import bella
    monkeypatch.setattr(pb, "criar", lambda pedido, chave=None, categoria="realismo", **k: "PROMPT:" + pedido)
    monkeypatch.setattr(bella, "_autenticar", lambda db, chave: SimpleNamespace(id=7))
    monkeypatch.setattr(bella, "_limitar", lambda *a: None)
    monkeypatch.setattr(bella, "_guardar_fala", lambda *a: "vid")
    salvos = []
    monkeypatch.setattr(acervo_prompts, "salvar_em_segundo_plano", lambda conta, cat, pedido, texto: salvos.append((cat, pedido, texto)))
    r = bella.conversa(bella.PedidoConversa(texto="crie um prompt de bar", modo="safada"), "k", None)
    assert salvos == [("realismo", "de bar", "PROMPT:de bar")] and r["texto"].startswith(pb.MARCA_PROMPT)
    salvos.clear()
    monkeypatch.setattr("nucleo.bella_conversa.responder", lambda texto, conta_id: "oi, amor")
    bella.conversa(bella.PedidoConversa(texto="oi bella", modo="safada"), "k", None)
    assert salvos == []            # conversa comum não vira prompt


@pytest.mark.parametrize("bruto,esperado", [
    ("Robe de Cetim na Cozinha Industrial", "Robe de Cetim na Cozinha Industrial"),
    ('"robe de cetim na cozinha."', "Robe de cetim na cozinha"),
    ("Título: Look Preto de Inverno\nExplicação longa", "Look Preto de Inverno"),
    ("Prompt · Use a imagem da nova modelo", None),
    ("RECUSA: algo", None), ("", None), (None, None), ("x" * 80, None),
    ("uma frase com muitas palavras demais para ser considerada título de verdade ok", None),
])
def test_limpar_titulo(bruto, esperado):
    assert acervo_prompts.limpar_titulo(bruto) == esperado


def test_titulo_criado_pelo_grok_vai_no_envio(monkeypatch):
    from nucleo import grok
    _sincrono(monkeypatch)
    enviados = []
    monkeypatch.setattr(modulos, "por_chave", lambda k: MOD)
    monkeypatch.setattr(modulos, "chamar", lambda mod, rota, corpo: enviados.append(corpo) or {})
    monkeypatch.setattr(grok, "gerar", lambda instr, texto, **k: "Robe de Cetim na Cozinha")
    longo = "Use a imagem da nova modelo como referência principal para manter o mesmo rosto"
    acervo_prompts.salvar_em_segundo_plano(_conta(), "realismo", longo, "texto do prompt completo")
    assert enviados[0]["titulo"] == "Robe de Cetim na Cozinha"


def test_sem_titulo_do_grok_nao_copia_o_comeco_do_pedido(monkeypatch):
    _sincrono(monkeypatch)
    enviados = []
    monkeypatch.setattr(modulos, "por_chave", lambda k: MOD)
    monkeypatch.setattr(modulos, "chamar", lambda mod, rota, corpo: enviados.append(corpo) or {})
    longo = "Use a imagem da nova modelo como referência principal para manter o mesmo rosto"
    acervo_prompts.salvar_em_segundo_plano(_conta(), "realismo", longo, "texto do prompt completo")
    assert "Use a imagem" not in enviados[0]["titulo"] and enviados[0]["titulo"].startswith("Prompt da Bella")


def test_ficha_vai_para_categoria_propria_e_texto_nao_trava_no_filtro_de_adultos():
    assert acervo_prompts.montar("ficha", "", "texto", "1")["categoria"] == "ficha"
    from nucleo import prompts_bella
    for modo in ("padrao", "roupa", "personagem", "cenario"):      # o Solo Prompts barra a palavra "menores"
        assert "menores" not in prompts_bella.modelo_ficha(modo).lower()
