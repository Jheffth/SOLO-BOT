"""Divide textos longos (prompts de até ~8000 caracteres) em mensagens que cabem no Telegram e no WhatsApp."""


def dividir(texto: str, limite: int = 3800) -> list:
    texto = (texto or "").strip()
    if len(texto) <= limite:
        return [texto]
    partes = []
    while len(texto) > limite:
        corte = max(texto.rfind("\n\n", 0, limite), texto.rfind("\n", 0, limite), texto.rfind(". ", 0, limite) + 1, texto.rfind(" ", 0, limite))
        if corte < limite // 2:
            corte = limite
        partes.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    if texto:
        partes.append(texto)
    return partes
