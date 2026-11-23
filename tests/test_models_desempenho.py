"""Velocidade da resposta das modelos: cache do pacote, gravação do turno em segundo plano e tempos no log."""
import logging
import threading
import time
from types import SimpleNamespace

import pytest

from nucleo import models

CONTA = SimpleNamespace(id=7, admin=True)


def test_pacote_fica_um_minuto_em_cache_e_a_escolha_busca_o_atual(monkeypatch):
    pedidos = []
    monkeypatch.setattr(models, "_requisicao", lambda metodo, rota, *a, **k: pedidos.append(rota) or
                        {"modelo": {"nome": "Isabella", "classificacao": "adulto"}})
    models.pacote(CONTA, "isa")
    models.pacote(CONTA, "isa")
    assert len(pedidos) == 1
    models.pacote(CONTA, "isa", fresco=True)              # escolher a modelo: sempre o pacote atual
    models.pacote(CONTA, "isa")
    assert len(pedidos) == 3
    monkeypatch.setattr(models, "PACOTE_SEGUNDOS", 0)     # cache vencido: busca de novo
    models.pacote(CONTA, "isa")
    assert len(pedidos) == 4


def test_cache_nao_libera_modelo_adulta_para_quem_nao_e_arquiteto(monkeypatch):
    monkeypatch.setattr(models, "_requisicao", lambda *a, **k: {"modelo": {"nome": "Isabella", "classificacao": "adulto"}})
    models.pacote(CONTA, "isa")
    with pytest.raises(models.ErroModels):
        models.pacote(SimpleNamespace(id=8, admin=False), "isa")


def test_gravacao_em_segundo_plano_mantem_a_ordem_e_nao_segura_a_resposta(monkeypatch):
    monkeypatch.setattr(models, "GRAVAR_EM_SEGUNDO_PLANO", True)
    gravados, liberar = [], threading.Event()

    def gravar(conta, ident, tipo, texto, **kw):
        if texto == "primeira":
            liberar.wait(5)
        gravados.append(texto)
    monkeypatch.setattr(models, "_gravar", gravar)
    inicio = time.monotonic()
    models._gravar_depois(CONTA, "isa", "turno", "primeira")
    models._gravar_depois(CONTA, "isa", "turno", "segunda")
    assert time.monotonic() - inicio < 0.5 and gravados == []      # a resposta não espera
    liberar.set()
    models.aguardar_gravacao(CONTA.id)
    assert gravados == ["primeira", "segunda"]


def test_falha_na_gravacao_nao_derruba_a_conversa(monkeypatch):
    monkeypatch.setattr(models, "GRAVAR_EM_SEGUNDO_PLANO", True)
    monkeypatch.setattr(models, "_gravar", lambda *a, **k: (_ for _ in ()).throw(models.ErroModels("fora do ar")))
    models._gravar_depois(CONTA, "isa", "turno", "x")
    models.aguardar_gravacao(CONTA.id)                     # não levanta


def test_montar_contexto_espera_a_gravacao_anterior(monkeypatch):
    monkeypatch.setattr(models, "GRAVAR_EM_SEGUNDO_PLANO", True)
    ordem = []

    def gravar(*a, **k):
        time.sleep(0.2)
        ordem.append("gravou")
    monkeypatch.setattr(models, "_gravar", gravar)

    def requisicao(metodo, rota, *a, **k):
        ordem.append("montou")
        return {"formato": 1, "perfil_modelo": {}, "historico": [], "blocos": [], "memorias_usadas": []}
    monkeypatch.setattr(models, "_requisicao", requisicao)
    models._gravar_depois(CONTA, "isa", "turno", "anterior")
    models._montar_contexto(CONTA, "isa", "e agora?")
    assert ordem == ["gravou", "montou"]


def test_tempos_de_cada_etapa_vao_para_o_log(caplog):
    caplog.set_level(logging.INFO, logger="solobot.models")
    models._registrar_tempos([("inicio", 0.0), ("pacote", 0.1), ("contexto", 1.6), ("ia", 5.6), ("gravar", 5.61)], 9000, 640)
    linha = caplog.records[-1].getMessage()
    assert "resposta em 5.61s" in linha and "contexto 1.50s" in linha and "ia 4.00s" in linha
    assert "prompt 9000 car." in linha and "resposta 640 car." in linha
