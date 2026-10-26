"""Biblioteca dos prompts da Bella e controle de repetição.

- `biblioteca_prompts.json` (no repositório, só leitura): os prompts já criados na conversa "REALISMO SENSUAL" do
  Grok, divididos nas partes que variam (cenário e gesto, expressão, roupa, luz, fundo), mais os bancos de
  ambientes e de roupas usados para sortear o prompt aleatório.
- `uso.json` (na pasta BIBLIOTECA_DIR, que é um volume e sobrevive ao deploy): quantas vezes cada ambiente e cada
  roupa do banco já foram usados e os prompts gerados depois (resumo de cada um e quantas vezes saiu).

O /prompt aleatório sorteia SEMPRE o ambiente e a roupa menos usados e manda ao Grok a lista do que já saiu para
ele não repetir. O /promptcriativo usa a mesma lista como "proibido repetir". Falha de disco nunca derruba o
pedido: o prompt sai igual, só não é registrado.
"""
import hashlib
import json
import logging
import os
import random
import re
import threading
import time

import config

log = logging.getLogger("solo.biblioteca")

SEMENTE = os.path.join(os.path.dirname(__file__), "biblioteca_prompts.json")
MAX_GERADAS = 300
_TRAVA = threading.Lock()


def _arquivo_uso():
    return os.path.join(config.BIBLIOTECA_DIR, "uso.json")


def semente():
    with open(SEMENTE, encoding="utf-8") as f:
        return json.load(f)


def _uso():
    try:
        with open(_arquivo_uso(), encoding="utf-8") as f:
            dados = json.load(f)
        if isinstance(dados, dict):
            dados.setdefault("ambientes", {})
            dados.setdefault("roupas", {})
            dados.setdefault("geradas", [])
            return dados
    except (OSError, ValueError):
        pass
    return {"versao": 1, "ambientes": {}, "roupas": {}, "geradas": []}


def _gravar(dados):
    try:
        os.makedirs(config.BIBLIOTECA_DIR, exist_ok=True)
        tmp = _arquivo_uso() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
        for _ in range(5):
            try:
                os.replace(tmp, _arquivo_uso())
                break
            except PermissionError:
                time.sleep(0.01)
        else:
            os.replace(tmp, _arquivo_uso())
    except OSError:
        log.warning("Biblioteca: não consegui gravar o controle de uso")


def _id(cenario, roupa):
    base = re.sub(r"\W+", " ", f"{cenario} {roupa}".lower()).strip()
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]


def _menos_usados(banco, usos):
    """Os itens do banco com menos usos, com desempate aleatório (nunca o mesmo atrás do outro)."""
    if not banco:
        return None
    minimo = min(usos.get(x, 0) for x in banco)
    return random.choice([x for x in banco if usos.get(x, 0) == minimo])


def sortear():
    """(ambiente, roupa) menos usados do banco. Só conta como uso depois do prompt aceito (registrar)."""
    sem = semente()
    with _TRAVA:
        uso = _uso()
    return _menos_usados(sem.get("ambientes"), uso["ambientes"]), _menos_usados(sem.get("roupas"), uso["roupas"])


def evitar(limite=24):
    """Resumos do que já saiu (mais usados e mais recentes primeiro), para o Grok não repetir."""
    with _TRAVA:
        uso = _uso()
    itens = []
    biblioteca = [f'{p["cenario"]} | roupa: {p["roupa"]}' for p in semente().get("prompts", [])]
    random.shuffle(biblioteca)      # a biblioteca tem dezenas de prompts: cada pedido mostra uma amostra diferente
    for texto in biblioteca:
        itens.append((0, 0, texto))
    for g in uso["geradas"]:
        itens.append((-g.get("vezes", 1), -g.get("ultima", 0), f'{g["cenario"]} | roupa: {g["roupa"]}'))
    itens.sort(key=lambda x: (x[0], x[1]))
    vistos, saida = set(), []
    for _, _, texto in itens:
        chave = texto[:60].lower()
        if chave not in vistos:
            vistos.add(chave)
            saida.append(texto[:220])
    return saida[:limite]


_PARTES = {
    "cenario": re.compile(r"A modelo está (.+?)\. Postura", re.S),
    "expressao": re.compile(r"Expressão facial (.+?), olhos semicerrados", re.S),
    "roupa": re.compile(r"A roupa é (.+?)\. Por baixo", re.S),
    "luz": re.compile(r"A iluminação é (.+?),? irregular", re.S),
    "fundo": re.compile(r"O fundo é (.+?)\.\s*(?:\n|$)", re.S),
}


def partes(texto):
    """As partes que variam de um prompt pronto, ou None se o texto não segue o modelo."""
    achado = {}
    for nome, regra in _PARTES.items():
        m = regra.search(texto or "")
        achado[nome] = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return achado if achado["cenario"] and achado["roupa"] else None


def registrar(texto, origem, ambiente=None, roupa_base=None):
    """Guarda o prompt aceito: conta o uso do ambiente e da roupa sorteados e lembra o resumo para não repetir."""
    p = partes(texto)
    try:
        with _TRAVA:
            uso = _uso()
            if ambiente:
                uso["ambientes"][ambiente] = uso["ambientes"].get(ambiente, 0) + 1
            if roupa_base:
                uso["roupas"][roupa_base] = uso["roupas"].get(roupa_base, 0) + 1
            if p:
                pid, agora = _id(p["cenario"], p["roupa"]), int(time.time())
                for g in uso["geradas"]:
                    if g["id"] == pid:
                        g["vezes"] = g.get("vezes", 1) + 1
                        g["ultima"] = agora
                        break
                else:
                    uso["geradas"].append({"id": pid, "origem": origem, "vezes": 1, "ultima": agora, **p})
                    uso["geradas"] = uso["geradas"][-MAX_GERADAS:]
            _gravar(uso)
    except Exception:       # a biblioteca nunca derruba o pedido
        log.warning("Biblioteca: falha ao registrar o prompt", exc_info=True)


def resumo():
    """Para conferir: quantos itens cada banco tem e o que já foi usado."""
    sem = semente()
    with _TRAVA:
        uso = _uso()
    return {"prompts_salvos": len(sem.get("prompts", [])), "geradas": len(uso["geradas"]),
            "ambientes": {a: uso["ambientes"].get(a, 0) for a in sem.get("ambientes", [])},
            "roupas": {r: uso["roupas"].get(r, 0) for r in sem.get("roupas", [])}}
