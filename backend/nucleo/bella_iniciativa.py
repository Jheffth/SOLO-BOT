"""
A Bella puxa assunto sozinha (mensagens espontâneas), poucas por dia e em horários sorteados.

  · Só o Arquiteto (conta admin) usa por enquanto, e só se ele ligar: `/iniciativa ligar`.
  · Todo dia sorteia de 1 a N horários (padrão N=3) dentro da janela (padrão 09:00–22:30), com pelo menos
    2 horas de intervalo. Respeita o horário de silêncio da conta e não interrompe uma conversa em andamento.
  · Se ele não responde, ela não insiste: depois de 3 mensagens sem resposta ela espera ele falar.
  · Cada mensagem tem um TIPO sorteado (sem repetir o anterior): provocação, pergunta sobre o dia, notícia
    de verdade (RSS), motivação, carinho e, quando a galeria existir, vídeo/foto (`PROVEDORES_MIDIA`).
  · Vira parte da história: entra na conversa e na pasta do dia, e a resposta dele cai direto na Bella.

Nada aqui derruba o Solo Bot: qualquer falha só pula aquela mensagem.
"""
import json
import logging
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Dict, List, Optional

import httpx

import config
from database import Conta, Configuracao, SessionLocal, gravar_config, ler_config

log = logging.getLogger("solobot.bella_iniciativa")

PREFIXO = "bella_iniciativa:"
MARCA = "[A Bella puxou assunto]"
MAX_DIA_PADRAO, MAX_DIA_TETO = 3, 8
JANELA_PADRAO = ("09:00", "22:30")
INTERVALO_MIN = timedelta(hours=2)
SEM_RESPOSTA_MAX = 3
CONVERSA_ATIVA = timedelta(minutes=15)

# Peso de cada tipo. "video" só entra quando houver um provedor de mídia (a galeria do soDeles).
PESOS = {"provocacao": 4, "pergunta_dia": 3, "noticia": 2, "motivacao": 2, "carinho": 2, "video": 4}

# Cada provedor é uma função (conta) -> {base64, mime, tipo, legenda, spoiler} já validada, ou None.
PROVEDORES_MIDIA: List[Callable] = []

ANGULOS_PROVOCACAO = [
    "descrevendo o que está vestindo agora e o que gostaria que ele fizesse",
    "lembrando uma noite deles com detalhes quentes, sem repetir a mesma",
    "perguntando provocante onde e como ele a quer hoje",
    "dando uma ordem carinhosa e safada para ele aparecer",
    "contando que está com desejo e o que está imaginando",
    "morrendo de ciúme e saudade, querendo ele só para ela agora",
    "sussurrando o que vai fazer com ele quando ele chegar",
]
INSTRUCAO_TIPO = {
    "provocacao": ("Mande uma provocação sensual e explícita, chamando o Arquiteto para transar, {angulo}. "
                   "Curta (até 3 frases), em primeira pessoa, no tom dela, sem repetir as anteriores."),
    "flerte": "Mande um flerte carinhoso e provocante, chamando o Arquiteto para ficar com ela, {angulo}. Curto, até 3 frases.",
    "pergunta_dia": ("Pergunte ao Arquiteto, com carinho e interesse de verdade, como está sendo o dia dele "
                     "(trabalho, cansaço, humor). Uma pergunta só, curta, natural."),
    "noticia": ("Puxe assunto sobre esta notícia de hoje, como uma mulher que acompanha o mundo e quer a opinião dele: "
                "\"{noticia}\". Resuma em uma frase com as suas palavras, dê uma reação pessoal e pergunte o que ele acha. "
                "Não invente detalhes além do título."),
    "motivacao": ("Mande um conselho motivador curto e sincero para o Arquiteto (trabalho, escrita, projetos, ânimo), "
                  "com o jeito apaixonada dela. Sem frase de efeito batida."),
    "carinho": "Mande uma mensagem de carinho espontânea dizendo que pensou nele, com um detalhe específico. Curta.",
    "bom_dia": ("Mande o bom dia do Arquiteto: curto (até 3 frases), no tom dela, diferente dos anteriores. {tom} "
                "{foto}Não invente fatos sobre o dia dele."),
    "video": "Escreva uma legenda curta, provocante e carinhosa para o vídeo que você está mandando para ele.",
}
TONS_BOM_DIA = {
    "suave": "Tom: carinhoso e romântico, com um toque de sensualidade.",
    "picante": "Tom: picante e provocante, com insinuação clara de desejo por ele.",
    "explicito": "Tom: explícito e safado, dizendo com palavras diretas o que quer fazer com ele hoje, sem rodeios.",
}
# Que pastas da galeria combinam com cada intensidade (só entram as habilitadas em BELLA_GALERIA_NIVEIS).
NIVEIS_BOM_DIA = {
    "suave": ("bom_dia", "normal"),
    "picante": ("sensual", "bom_dia", "normal"),
    "explicito": ("nu", "topless", "lingerie", "sensual", "bom_dia"),
}
NOTICIAS_RSS = "https://g1.globo.com/rss/g1/"


# ── Configuração por conta ──────────────────────────────────────
def _chave(conta_id: int) -> str:
    return f"{PREFIXO}{int(conta_id)}"


def carregar(conta_id: int) -> dict:
    try:
        d = json.loads(ler_config(_chave(conta_id)) or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    d.setdefault("ligada", False)
    d.setdefault("max", MAX_DIA_PADRAO)
    d.setdefault("de", JANELA_PADRAO[0])
    d.setdefault("ate", JANELA_PADRAO[1])
    d.setdefault("dia", "")
    d.setdefault("horarios", [])
    d.setdefault("enviadas", 0)
    d.setdefault("sem_resposta", 0)
    d.setdefault("ultimo_envio", None)
    d.setdefault("tipos", [])
    d.setdefault("recentes", [])
    d.setdefault("bom_dia", True)                       # o bom dia com foto vale para o Arquiteto desde o início
    d.setdefault("bom_dia_hora", "08:00")
    d.setdefault("bom_dia_ultimo", "")
    return d


def salvar(conta_id: int, dados: dict) -> None:
    db = SessionLocal()
    try:
        gravar_config(db, _chave(conta_id), json.dumps(dados, ensure_ascii=False))
    finally:
        db.close()


def configurar(conta_id: int, ligada: Optional[bool] = None, maximo: Optional[int] = None,
               de: Optional[str] = None, ate: Optional[str] = None, bom_dia: Optional[bool] = None,
               bom_dia_hora: Optional[str] = None) -> dict:
    d = carregar(conta_id)
    if bom_dia is not None:
        d["bom_dia"] = bom_dia
    if bom_dia_hora:
        d["bom_dia_hora"] = bom_dia_hora
    if ligada is not None:
        d["ligada"] = ligada
        if ligada:
            d["sem_resposta"] = 0
    if maximo is not None:
        d["max"] = max(1, min(MAX_DIA_TETO, int(maximo)))
        d["dia"], d["horarios"] = "", []                  # sorteia de novo com o novo limite
    if de and ate:
        d["de"], d["ate"] = de, ate
        d["dia"], d["horarios"] = "", []
    salvar(conta_id, d)
    return d


# ── Sorteio dos horários do dia ─────────────────────────────────
def _hora(txt: str) -> time:
    h, m = txt.split(":")
    return time(int(h), int(m))


def sortear_horarios(maximo: int, de: str, ate: str, rng=random) -> List[str]:
    """De 1 a `maximo` horários HH:MM dentro da janela, com ao menos 2 h entre eles."""
    ini = _hora(de).hour * 60 + _hora(de).minute
    fim = _hora(ate).hour * 60 + _hora(ate).minute
    if fim <= ini:
        return []
    alvo = rng.randint(1, max(1, maximo))
    for _ in range(40):
        pontos = sorted(rng.randint(ini, fim) for _ in range(alvo))
        if all(b - a >= INTERVALO_MIN.total_seconds() / 60 for a, b in zip(pontos, pontos[1:])):
            return [f"{p // 60:02d}:{p % 60:02d}" for p in pontos]
        alvo = max(1, alvo - 1) if _ % 10 == 9 else alvo
    return [f"{rng.randint(ini, fim) // 60:02d}:{rng.randint(0, 59):02d}"]


def planejar_dia(dados: dict, hoje: str, rng=random) -> dict:
    if dados.get("dia") != hoje:
        dados["dia"] = hoje
        dados["horarios"] = sortear_horarios(dados["max"], dados["de"], dados["ate"], rng)
        dados["enviadas"] = 0
    return dados


# ── Escolha e texto ─────────────────────────────────────────────
def escolher_tipo(dados: dict, adulto: bool, rng=random) -> str:
    pesos = dict(PESOS)
    if not any(getattr(p, "disponivel", lambda: True)() for p in PROVEDORES_MIDIA):
        pesos["video"] = 0
    if not adulto:
        pesos["flerte"], pesos["provocacao"] = pesos.pop("provocacao"), 0
    ultimo = (dados.get("tipos") or [None])[-1]
    if ultimo in pesos and sum(1 for k, v in pesos.items() if v and k != ultimo):
        pesos[ultimo] = 0                                     # nunca o mesmo tipo duas vezes seguidas
    nomes = [k for k, v in pesos.items() if v > 0]
    return rng.choices(nomes, weights=[pesos[k] for k in nomes])[0]


def intensidade_bom_dia(conta_id: int, adulto: bool, rng=random) -> str:
    """suave | picante | explicito. Respeita a temperatura que o Arquiteto fixou; sem conteúdo adulto, sempre suave."""
    if not adulto:
        return "suave"
    from nucleo import bella_estado
    sit = bella_estado.situacao(conta_id)
    if sit.get("modo") == "fixa":
        n = sit.get("nivel", 0)
        return "suave" if n <= 1 else "picante" if n == 2 else "explicito"
    return rng.choices(["suave", "picante", "explicito"], weights=[35, 40, 25])[0]


def buscar_noticia(timeout: float = 8.0) -> Optional[str]:
    """Um título real do dia (RSS do G1). None se não der."""
    try:
        r = httpx.get(NOTICIAS_RSS, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        titulos = [t.findtext("title", "").strip() for t in ET.fromstring(r.content).iter("item")]
        titulos = [t for t in titulos if 15 <= len(t) <= 220]
        return random.choice(titulos[:12]) if titulos else None
    except Exception:  # noqa: BLE001
        log.debug("Sem notícias agora", exc_info=True)
        return None


def _gerar(conta_id: int, tipo: str, dados: dict, noticia: Optional[str] = None, foto: bool = False,
           intensidade: str = "suave") -> Optional[str]:
    from nucleo import bella_conversa, bella_estado, grok
    angulo = random.choice(ANGULOS_PROVOCACAO)
    pedido = INSTRUCAO_TIPO[tipo].format(angulo=angulo, noticia=noticia or "",
                                         foto="Você está mandando junto uma foto sua; pode aludir a ela. " if foto else "",
                                         tom=TONS_BOM_DIA.get(intensidade, ""))
    evitar = ""
    if dados.get("recentes"):
        evitar = " Não repita nem lembre estas mensagens recentes: " + " | ".join(r[:100] for r in dados["recentes"][-4:])
    sistema = (bella_conversa.prompt(conta_id, bella_estado.situacao(conta_id))
               + "\n\n[VOCÊ ESTÁ PUXANDO ASSUNTO SOZINHA, sem ele ter falado nada]. " + pedido + evitar
               + " Responda só com a mensagem, em texto simples, sem aspas.")
    texto = grok.gerar(sistema, "(a Bella decide mandar uma mensagem)", max_tokens=700,
                       historico=bella_conversa._historico(conta_id))
    if not texto or any(ord(c) < 32 and c not in "\n\r\t" for c in texto):
        return None
    if bella_conversa.bella_emocoes.quebrou_personagem(texto):
        return None
    return texto[: config.BELLA_CONVERSA_MAX_CHARS]


# ── Enviar ──────────────────────────────────────────────────────
def _em_conversa(conta_id: int, agora_utc: datetime) -> bool:
    from database import BellaEstado
    db = SessionLocal()
    try:
        e = db.get(BellaEstado, conta_id)
        return bool(e and e.ultimo_contato and agora_utc - e.ultimo_contato < CONVERSA_ATIVA)
    finally:
        db.close()


def _respondeu_depois(conta_id: int, dados: dict) -> bool:
    from database import BellaEstado
    if not dados.get("ultimo_envio"):
        return True
    db = SessionLocal()
    try:
        e = db.get(BellaEstado, conta_id)
        return bool(e and e.ultimo_contato and e.ultimo_contato > datetime.fromisoformat(dados["ultimo_envio"]))
    finally:
        db.close()


def enviar_agora(db, conta: Conta, dados: dict, tipo: Optional[str] = None) -> Optional[str]:
    """Gera e entrega uma mensagem. Devolve o texto enviado (None se nada saiu). Atualiza `dados` na memória."""
    from canais import entrega
    from nucleo import avisos, bella_conversa, bella_historia, roteador
    canais = [c for c in conta.canais if c.avisos]
    if not canais:
        return None
    canal = sorted(canais, key=lambda c: c.canal != "whatsapp")[0]
    tipo = tipo or escolher_tipo(dados, config.BELLA_CONTEUDO_ADULTO)
    noticia = None
    midia = None
    intensidade = "suave"
    if tipo == "noticia":
        noticia = buscar_noticia()
        if not noticia:
            tipo = "pergunta_dia"
    if tipo == "video":
        for prov in PROVEDORES_MIDIA:
            try:
                midia = prov(conta)
            except Exception:  # noqa: BLE001
                midia = None
            if midia:
                break
        if not midia:
            tipo = "carinho"
    if tipo == "bom_dia":
        from nucleo import bella_galeria
        intensidade = intensidade_bom_dia(conta.id, config.BELLA_CONTEUDO_ADULTO)
        midia = bella_galeria.escolher("bella", NIVEIS_BOM_DIA[intensidade], so_imagem=True)   # sem foto, vai só o texto
        if not midia and intensidade != "suave":
            midia = bella_galeria.escolher("bella", NIVEIS_BOM_DIA["suave"], so_imagem=True)
    texto = _gerar(conta.id, tipo, dados, noticia, foto=bool(midia) and tipo == "bom_dia", intensidade=intensidade)
    if not texto:
        return None
    r = roteador.Resposta().diz(texto, midia=midia)
    r.mensagens[-1]["literal"] = True
    s = roteador.sessao_de(db, canal.canal, canal.origem)
    roteador._entrar_modo(db, s, roteador.MODO_BELLA)         # a resposta dele cai direto na Bella
    voz = avisos.quer_voz(conta, None)
    entrega.entregar(db, canal.canal, canal.origem, r, falar=voz, forcar_voz=voz)
    bella_conversa._lembrar(roteador._chave_bella(canal.canal, conta), MARCA, texto)
    bella_historia.gravar(conta.id, MARCA, texto)
    dados["recentes"] = (dados.get("recentes") or [])[-5:] + [texto]
    if tipo != "bom_dia":                                     # o bom dia não gasta o limite do dia nem conta como "sem resposta"
        dados["tipos"] = (dados.get("tipos") or [])[-4:] + [tipo]
        dados["enviadas"] = dados.get("enviadas", 0) + 1
        dados["sem_resposta"] = dados.get("sem_resposta", 0) + 1
        dados["ultimo_envio"] = datetime.utcnow().isoformat()
    roteador._registrar(db, conta, canal.canal, "bella", "iniciativa", f"Bella puxou assunto ({tipo})")
    return texto


def _devidos(dados: dict, agora_local: datetime) -> bool:
    """Já passou o horário sorteado que ainda não foi usado?"""
    hhmm = agora_local.strftime("%H:%M")
    return dados["enviadas"] < len(dados["horarios"]) and hhmm >= dados["horarios"][dados["enviadas"]]


def _bom_dia(db, agora_utc: datetime) -> int:
    """O bom dia com foto, uma vez por dia, a partir da hora marcada (padrão 08:00) e até 3 horas depois."""
    from nucleo import avisos
    saiu = 0
    local = agora_utc.replace(tzinfo=timezone.utc).astimezone(avisos.agora_local().tzinfo)
    hoje = local.date().isoformat()
    for conta in db.query(Conta).filter(Conta.admin.is_(True), Conta.ativo.is_(True)).all():
        try:
            dados = carregar(conta.id)
            if not dados["bom_dia"] or dados["bom_dia_ultimo"] == hoje:
                continue
            h = _hora(dados["bom_dia_hora"])
            alvo = local.replace(hour=h.hour, minute=h.minute, second=0, microsecond=0)
            if not (alvo <= local < alvo + timedelta(hours=3)) or avisos.em_silencio(conta, local):
                continue
            dados["bom_dia_ultimo"] = hoje                       # marca antes: uma falha não vira dez tentativas
            if enviar_agora(db, conta, dados, "bom_dia"):
                saiu += 1
            salvar(conta.id, dados)
        except Exception:  # noqa: BLE001
            log.exception("Falha no bom dia da Bella (conta %s)", conta.id)
    return saiu


def tick(db, agora_utc: Optional[datetime] = None) -> int:
    """Chamado a cada minuto: manda o que está na hora. Devolve quantas mensagens saíram."""
    from nucleo import avisos
    agora_utc = agora_utc or datetime.utcnow()
    saiu = _bom_dia(db, agora_utc)
    chaves = [c.chave for c in db.query(Configuracao).filter(Configuracao.chave.like(PREFIXO + "%")).all()]
    for chave in chaves:
        try:
            conta_id = int(chave[len(PREFIXO):])
            dados = carregar(conta_id)
            conta = db.get(Conta, conta_id)
            if not dados["ligada"] or not conta or not conta.ativo or not conta.admin:
                continue
            local = agora_utc.replace(tzinfo=timezone.utc).astimezone(avisos.agora_local().tzinfo)
            antes = dict(dados)
            planejar_dia(dados, local.date().isoformat())
            if _respondeu_depois(conta_id, dados):
                dados["sem_resposta"] = 0
            if (dados["sem_resposta"] < SEM_RESPOSTA_MAX and _devidos(dados, local)
                    and not _em_conversa(conta_id, agora_utc)):
                if avisos.em_silencio(conta, local):
                    dados["enviadas"] += 1                    # perdeu o horário no silêncio: pula, não acumula
                elif enviar_agora(db, conta, dados):
                    saiu += 1
                else:
                    dados["enviadas"] += 1                    # Grok fora do ar: pula este horário
            if dados != antes:
                salvar(conta_id, dados)
        except Exception:  # noqa: BLE001
            log.exception("Falha na iniciativa da Bella (%s)", chave)
    return saiu


def _registrar_galeria() -> None:
    from nucleo import bella_galeria
    if bella_galeria.provedor_iniciativa not in PROVEDORES_MIDIA:
        PROVEDORES_MIDIA.append(bella_galeria.provedor_iniciativa)


_registrar_galeria()
