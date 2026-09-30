# -*- coding: utf-8 -*-
"""
A INTENÇÃO — entender PARA QUAL sistema é o que a pessoa disse, e O QUE
mandar para ele.

POR QUE EXISTE

"Olhe nas minhas rotinas, quero ver o que tem para hoje" é claramente do
Rotinas — e o Rotinas só entende `/hoje`. Sem esta camada, o hub perguntava
"para qual sistema?" e, mesmo respondido, o Rotinas diria "comando não
reconhecido".

DUAS CAMADAS, da mais barata para a mais cara

  1. PALAVRAS — o manifesto de cada sistema (nomes, comandos, descrições,
     exemplos) + um vocabulário básico. Grátis e instantâneo. Decide o
     sistema quando só um casa.
  2. IA (Gemini) — quando as palavras não bastam, ou quando o sistema de
     destino só entende comandos (manifesto sem `exemplos`): recebe os
     comandos de cada sistema e devolve {app, mensagem, confianca}.
     `mensagem` é o que vai de fato para o sistema: o comando com os
     argumentos ("/ok leitura"), ou o próprio texto, se o sistema aceita
     texto livre (o Finances entende "gastei 30 no almoço").

Nada aqui executa coisa alguma: só traduz. Na dúvida, devolve vazio e o hub
pergunta, como antes.
"""
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional

from nucleo import manifestos, modulos

log = logging.getLogger("solobot.intencao")

CONFIANCA_MINIMA = 0.6        # abaixo disso o hub pergunta
CONFIANCA_TROCA = 0.85        # para SAIR de um modo ativo e ir a outro sistema

VOCABULARIO = {
    "fin": "financas financeiro dinheiro gastei gasto gastos paguei pagar pagamento recebi receita despesa "
           "saldo saldos extrato transferi transferencia pix conta contas cartao fatura reais real banco nubank "
           "santander itau inter caixa boleto compra comprei salario investimento orcamento lancamento lancar",
    "rot": "rotina rotinas missao missoes tarefa tarefas treino dungeon dungeons portao portoes xp nivel "
           "streak corrente meta metas habito habitos penitencia conquista conquistas hunter iniciar concluir "
           "conclui terminei comecei pendente pendentes agenda circuito bloco passiva",
}


@dataclass
class Intencao:
    app: Optional[str] = None
    mensagem: Optional[str] = None
    confianca: float = 0.0
    via: str = ""


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _palavras(t: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", _norm(t)))


def aceita_texto_livre(db, app: str) -> bool:
    """O manifesto com `exemplos` diz que o sistema entende frases soltas."""
    return bool((manifestos.de(db, app) or {}).get("exemplos"))


def _vocab(db, mod: modulos.Modulo) -> set:
    man = manifestos.de(db, mod.chave) or {}
    texto = " ".join([mod.nome.replace("Solo ", ""), VOCABULARIO.get(mod.chave, "")]
                     + [c["comando"].lstrip("/") for c in man.get("comandos", [])]
                     + man.get("exemplos", []))
    return {p for p in _palavras(texto) if p not in {"solo", "com", "que", "para", "hoje", "meu", "minha"}}


def por_palavras(db, texto: str, candidatos: List[modulos.Modulo]) -> dict:
    """{app: pontos} — quantas palavras do texto casam com o vocabulário de cada sistema."""
    ditas = _palavras(texto)
    if re.search(r"r\$\s*\d|\d+[,.]\d{2}\b", texto or "", re.I):
        ditas.add("reais")
    return {m.chave: len(ditas & _vocab(db, m)) for m in candidatos}


# ── A IA ─────────────────────────────────────────────────────────
PROMPT = """Você é o roteador de um bot de chat que atende vários sistemas pessoais.
Receba a MENSAGEM do usuário e a lista de SISTEMAS (com os comandos de cada um).
Decida para qual sistema ela é e o que enviar a ele.

Responda SOMENTE um JSON: {"app": "<chave ou vazio>", "mensagem": "<o que enviar>", "confianca": 0.0}

Regras:
- "app": a chave do sistema. Vazio se não der para saber.
- "mensagem":
  - se o sistema tem aceita_texto_livre=true e a mensagem é um registro/pedido em linguagem natural, repita a mensagem original;
  - senão, traduza para UM comando da lista daquele sistema, com os argumentos que a pessoa disse
    (ex.: "terminei a leitura" -> "/ok leitura"; "o que tenho pra hoje" -> "/hoje"). Sem o prefixo do sistema.
  - se nenhum comando serve, vazio.
- Ao montar um comando:
  - siga o "uso" do comando À RISCA, inclusive a ORDEM dos argumentos (o "exemplo" mostra um caso real);
  - número vai só como número: "R$ 25" -> 25, "vinte e cinco reais" -> 25, "meio litro" -> 500 se a unidade for ml;
    vírgula decimal vira ponto ("12,50" -> 12.5);
  - o título da missão vai em POUCAS palavras que a identifiquem (o sistema procura por trecho do nome);
    descarte palavras de ligação e o que for descrição da meta ("na rotina de R$ 50 no turno da noite" -> "noite");
  - nunca copie a frase inteira para dentro do comando.
- Exemplos:
  - "Some R$ 25 na rotina de R$ 50 no turno da noite" -> {"app":"rot","mensagem":"/somar noite 25","confianca":0.9}
  - "bebi meio litro de água" -> {"app":"rot","mensagem":"/somar água 500","confianca":0.85}
  - "comecei o treino" -> {"app":"rot","mensagem":"/iniciar treino","confianca":0.9}
- "confianca": de 0 a 1.
- Nunca invente comando fora da lista."""


def _ia(texto: str, sistemas: list, modo: Optional[str]) -> Optional[Intencao]:
    from nucleo import gemini
    contexto = json.dumps({"modo_atual": modo or "", "sistemas": sistemas}, ensure_ascii=False)
    bruto = gemini.gerar(PROMPT, f"SISTEMAS: {contexto}\n\nMENSAGEM: {texto}", json_saida=True)
    if not bruto:
        return None
    try:
        d = json.loads(bruto[bruto.find("{"): bruto.rfind("}") + 1])
        return Intencao(app=(d.get("app") or "").strip().lower() or None,
                        mensagem=(d.get("mensagem") or "").strip() or None,
                        confianca=float(d.get("confianca") or 0), via="ia")
    except (ValueError, TypeError):
        log.warning("Intenção: a IA respondeu algo que não é JSON")
        return None


def _descrever(db, mods: List[modulos.Modulo]) -> list:
    saida = []
    for m in mods:
        man = manifestos.de(db, m.chave) or {}
        saida.append({"chave": m.chave, "nome": m.nome, "descricao": m.descricao,
                      "aceita_texto_livre": bool(man.get("exemplos")),
                      "exemplos": man.get("exemplos", [])[:5],
                      "comandos": [{k: v for k, v in (("comando", c["comando"]), ("descricao", c["descricao"]),
                                                        ("uso", c.get("uso")), ("exemplo", c.get("exemplo"))) if v}
                                   for c in man.get("comandos", []) if not c.get("oculto")]})
    return saida


def interpretar(db, texto: str, candidatos: List[modulos.Modulo], modo: Optional[str] = None) -> Intencao:
    """
    Para qual sistema é, e o que mandar. `app` vazio = não deu para saber
    (o hub pergunta). A mensagem só é traduzida para comando quando o
    sistema de destino não aceita texto livre.
    """
    texto = (texto or "").strip()
    if not texto or texto.startswith("/") or not candidatos:
        return Intencao()
    chaves = {m.chave for m in candidatos}
    pontos = por_palavras(db, texto, candidatos)
    com_ponto = [k for k, p in pontos.items() if p > 0]
    unico = com_ponto[0] if len(com_ponto) == 1 else None

    # Palavras bastam quando só um sistema casa E ele entende texto livre.
    # (Com um modo ativo em OUTRO sistema, trocar é sério: quem confirma é a IA.)
    if unico and aceita_texto_livre(db, unico) and (modo is None or unico == modo):
        return Intencao(app=unico, mensagem=texto, confianca=0.7, via="palavras")

    ia = _ia(texto, _descrever(db, candidatos), modo)
    if ia and ia.app in chaves and ia.confianca >= CONFIANCA_MINIMA:
        if not ia.mensagem:
            ia.mensagem = texto if aceita_texto_livre(db, ia.app) else None
        return ia
    if unico:                      # a IA não ajudou, mas as palavras apontam um só
        return Intencao(app=unico, mensagem=texto if aceita_texto_livre(db, unico) else None,
                        confianca=0.5, via="palavras")
    return Intencao()
