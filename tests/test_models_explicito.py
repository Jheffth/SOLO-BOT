"""Clima sexual com conteúdo adulto liberado: a modelo usa linguagem explícita; fora disso, nada muda."""
from types import SimpleNamespace

from nucleo import models

P = {'nome': 'Kellen', 'classificacao': 'adulto', 'conteudo_adulto_habilitado': True}


def _ctx(temp, adulto=True):
    return {'blocos': [], 'perfil_modelo': {}, 'historico': [], 'perfil_pessoa': {},
            'estado': {'temperatura': temp, 'bloco': ''}, 'conteudo_adulto': adulto}


def test_linguagem_explicita_so_com_clima_sexual_e_adulto():
    conta = SimpleNamespace(admin=True)
    assert models.LINGUAGEM_EXPLICITA in models.montar_prompt(conta, P, _ctx(3))[0]
    assert 'boceta' in models.LINGUAGEM_EXPLICITA and 'clitóris' in models.LINGUAGEM_EXPLICITA
    assert models.LINGUAGEM_EXPLICITA not in models.montar_prompt(conta, P, _ctx(2))[0]
    assert models.LINGUAGEM_EXPLICITA not in models.montar_prompt(conta, P, _ctx(5, adulto=False))[0]
    geral = {**P, 'classificacao': 'geral'}
    assert models.LINGUAGEM_EXPLICITA not in models.montar_prompt(conta, geral, _ctx(5))[0]
