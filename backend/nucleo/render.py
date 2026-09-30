# -*- coding: utf-8 -*-
"""
Opções neutras → o que cada aplicativo sabe desenhar.

    [{"titulo": "Banho", "acoes": [{"rotulo": "✅ Concluir", "dados": "ok|r|12"}]}]

Os `dados` ganham o prefixo do dono (`rot:ok|r|12`, `hub:app|fin`). É por
ele que um toque volta para quem o ofereceu.
"""
from typing import Optional


def prefixar(opcoes, dono: str) -> list:
    saida = []
    for g in (opcoes or []):
        acoes = [{"rotulo": a["rotulo"], "dados": f"{dono}:{a['dados']}"}
                 for a in (g.get("acoes") or []) if a.get("rotulo") and a.get("dados")]
        if acoes:
            saida.append({"titulo": g.get("titulo") or "", "acoes": acoes})
    return saida


def plano(opcoes) -> list:
    """Todas as ações numa lista só, na ordem mostrada."""
    saida = []
    for g in (opcoes or []):
        for a in (g.get("acoes") or []):
            saida.append({"rotulo": a["rotulo"], "dados": a["dados"],
                          "titulo": g.get("titulo") or ""})
    return saida


def teclado_telegram(opcoes) -> Optional[dict]:
    if not opcoes:
        return None
    linhas = []
    for g in opcoes:
        acoes = [{"text": a["rotulo"][:60], "callback_data": a["dados"][:64]}
                 for a in (g.get("acoes") or [])]
        if not acoes:
            continue
        titulo = (g.get("titulo") or "").strip()
        if titulo:
            linhas.append([{"text": f"— {titulo[:40]} —", "callback_data": "hub:nada"}])
        linhas.append(acoes)
    return {"inline_keyboard": linhas} if linhas else None


def lista_whatsapp(itens: list, inicio: int = 0) -> str:
    linhas = []
    for i, a in enumerate(itens, inicio + 1):
        titulo = (a.get("titulo") or "").strip()
        linhas.append(f"*{i}.* {a['rotulo']}" + (f" — {titulo}" if titulo else ""))
    linhas.append("")
    linhas.append("_Responda com o número._")
    return "\n".join(linhas)


def para_whatsapp(texto: str) -> str:
    """O Markdown do Telegram usa *negrito* e _itálico_ — o WhatsApp também.
    Só a crase tripla/simples muda pouco; deixamos como está."""
    return texto
