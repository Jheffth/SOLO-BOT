"""Saudações da chamada Bella: login autenticado, frases fixas e áudio por voz."""
import hashlib
import json

from nucleo import fala

FRASES = (
    "Oi, {nome}. Estou aqui. Pode falar.",
    "Olá, {nome}. O que você precisa?",
    "Sim, {nome}? Estou ouvindo.",
    "Pode falar, {nome}. Estou com você.",
    "Às ordens, {nome}. Como posso ajudar?",
    "Pronta, {nome}. Qual é o pedido?",
    "Estou aqui, {nome}. Vamos lá?",
    "Oi, {nome}. Me diga o que vamos fazer.",
    "Chamou, {nome}? Pode contar comigo.",
    "Olá, {nome}. Pode me dizer.",
    "Estou ouvindo, {nome}. O que faremos agora?",
    "Aqui é a Bella, {nome}. Pode falar.",
    "Diga, {nome}. Estou pronta para ajudar.",
    "Oi, {nome}. Qual é a próxima tarefa?",
    "Conte comigo, {nome}. O que você tem em mente?",
    "Prontinha, {nome}. Estou ouvindo você.",
    "Sim, {nome}. Vamos cuidar disso. Pode falar.",
    "Bella a postos, {nome}. Como posso ajudar?",
    "Olá, {nome}. Qual é a missão de agora?",
    "Estou por aqui, {nome}. Me diga o que precisa.",
)


def catalogo(conta, perfil_voz=None):
    # O login foi solicitado; contas antigas sem login usam o nome cadastrado.
    nome = conta.usuario or conta.nome.split()[0]
    voz = perfil_voz if perfil_voz is not None else fala.perfil_ativo()
    linhas = [{"id": i, "texto": frase.format(nome=nome)} for i, frase in enumerate(FRASES)]
    perfil = hashlib.sha256(json.dumps([conta.id, nome, voz, linhas], sort_keys=True,
                                      ensure_ascii=False).encode()).hexdigest()
    return {"perfil": perfil, "usuario": nome, "voz": voz, "saudacoes": linhas}


def preparar(conta, id_: int, com_audio: bool = True):
    atual = catalogo(conta)
    texto = atual["saudacoes"][id_]["texto"]
    audio = fala.sintetizar(texto, "whatsapp", guardar=True) if com_audio else None
    saida = {"id": id_, "perfil": atual["perfil"], "texto": texto, "falar": texto,
             "voz": atual["voz"], "usuario": atual["usuario"]}
    if audio:
        perfil = catalogo(conta, audio["perfil_voz"])
        saida.update(perfil=perfil["perfil"], voz=perfil["voz"], audio_base64=audio["base64"],
                     mime=audio["mime"], cache_id=audio["cache_id"])
    return saida
