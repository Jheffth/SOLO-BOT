"""Cena com várias modelos no modo Models (/addmodel, /removemodel, /modelos).

Quem decide quem fala é o código (diretor de turno). Cada modelo fala por si: uma chamada ao Grok por
fala, cada uma com o próprio contexto montado pelo Solo Models (a relação privada dela, o vínculo com
as outras e a cena desde que ela chegou). Uma mensagem por fala, com o nome e a voz da própria modelo.
Só o Arquiteto usa cenas por enquanto.
"""
import logging
import re
import threading
import time
import unicodedata
from uuid import uuid4

log = logging.getLogger("solobot.models_cena")

LIMITE_PADRAO = 2          # falas de cada modelo por rodada (de 1 a 2, enquanto houver assunto)
SILENCIO = "[silêncio]"
MAX_FALA = 900
# O Bella.exe desiste em 25 s e não recebe mensagens depois: só começa outra fala se ainda houver tempo.
TEMPO_SINCRONO = 10
# Nestes canais a primeira fala sai na hora e as reações chegam depois, uma de cada vez.
CANAIS_DEPOIS = ("whatsapp", "telegram")
_geracao = {}            # conta -> número da rodada; uma mensagem nova interrompe a rodada anterior
_geracao_lock = threading.Lock()


def _m():
    from nucleo import models
    return models


def _norm(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").casefold()) if unicodedata.category(c) != "Mn")


def _citado(nome, texto):
    return bool(nome) and re.search(r"(?<!\w)" + re.escape(_norm(nome)) + r"(?!\w)", _norm(texto)) is not None


def _voz(p):
    return next((v for v in p.get("vozes_por_conta", []) if v.get("principal") and v.get("ativa")), None)


def cena_ativa(conta, ident):
    """A cena aberta do Arquiteto que inclui a modelo selecionada, ou None."""
    m = _m()
    try:
        c = m._requisicao("GET", m._rota(conta, ident) + "/cena", conta, ident)
    except Exception:  # noqa: BLE001  sem cena consultável, a conversa segue individual
        return None
    if not isinstance(c, dict) or not c.get("ativa"):
        return None
    ids = [p.get("modelo_id") for p in c.get("presentes", [])]
    return c if ident in ids and len(ids) >= 2 else None


def _limpar(texto, nome, outros):
    """Só a fala dela: tira o prefixo com o próprio nome e corta onde começaria a fala de outra pessoa."""
    texto = (texto or "").strip()
    texto = re.sub(r"^\s*\**\s*" + re.escape(nome) + r"\s*\**\s*:\s*", "", texto, flags=re.I)
    for outro in [*outros, "Arquiteto", "Narração", "Narrador"]:
        corte = re.search(r"(?:^|\s)\**\s*" + re.escape(outro) + r"\s*\**\s*:", texto, flags=re.I)
        if corte:
            texto = texto[:corte.start()].strip()
    return texto[:MAX_FALA].strip()


def _fala(conta, modelo_id, presentes, nomes, mensagem, ja_ditas, instrucao="", primeira=True, pode_calar=True,
          reagir=None):
    """Uma fala da modelo, gerada com o contexto dela. Devolve dict ou None (silêncio)."""
    from nucleo import grok
    m = _m()
    p = m.pacote(conta, modelo_id)
    voz = _voz(p)
    if not voz:
        raise m.ErroModels(f"{p['nome']} ainda não possui uma voz principal ativa.")
    ctx = m._montar_contexto(conta, modelo_id, mensagem or "[Cena]", origem="usuario" if primeira else "iniciativa",
                             presentes=presentes)
    prompt, factual, historico = m.montar_prompt(conta, p, ctx)
    prompt += ("\nVocê está numa cena com mais de uma modelo. Escreva SOMENTE a sua próxima fala, em primeira pessoa, "
               "curta e natural (até 600 caracteres), sem o seu nome na frente e sem escrever falas ou ações das outras. "
               "Seja você mesma, com criatividade: aja, provoque, brinque, discorde. Não repita frases, bordões ou ideias "
               "que você ou as outras já disseram na cena, e não resuma o que já aconteceu.")
    if pode_calar:
        prompt += f" Se agora não tiver nada relevante a acrescentar, responda exatamente {SILENCIO}."
    partes = []
    if mensagem:
        partes.append("Arquiteto: " + mensagem)
    anteriores = [f for f in ja_ditas if f is not reagir]
    if anteriores:
        partes.append("Antes, nesta rodada:\n" + "\n".join(f"{f['nome']}: {f['texto']}" for f in anteriores))
    if reagir:
        partes.append(f"{reagir['nome']} acabou de dizer: \"{reagir['texto']}\"\n"
                      f"[Situação, não é fala de ninguém] Responda a essa fala de {reagir['nome']} (e ao Arquiteto, se fizer "
                      "sentido) do seu jeito. Traga algo novo: não repita nem parafraseie o que ela disse e não reuse as "
                      "expressões dela.")
    if instrucao:
        partes.append("[Situação, não é fala de ninguém] " + instrucao)
    partes.append(f"Agora é a sua vez, {p['nome']}.")
    pergunta = "\n\n".join(partes) + ("\n\n[CONTEXTO INTERNO ATUAL — não é fala da pessoa]" + factual if factual else "")
    saida = grok.gerar(prompt, pergunta, max_tokens=600, historico=historico)
    if (saida and conta.admin and p.get("obediencia_arquiteto", True) is not False and mensagem
            and m._ordem_firme(mensagem) and _citado(p["nome"], mensagem) and m._recusou(saida)):
        outra = grok.gerar(prompt + m.LEMBRETE_OBEDECER, pergunta, max_tokens=600, historico=historico)
        if outra and not m._recusou(outra):
            saida = outra
    outros = [n for i, n in nomes.items() if i != modelo_id]
    texto = _limpar(saida, p["nome"], outros)
    if not texto or (pode_calar and _norm(SILENCIO.strip("[]")) in _norm(texto) and len(texto) < 40):
        return None
    return {"modelo_id": modelo_id, "nome": p["nome"], "texto": texto, "voz": voz, "contexto_id": ctx.get("contexto_id")}


def _registrar(conta, ident, usuario, falas, narracao=""):
    m = _m()
    try:
        m._requisicao("POST", m._rota(conta, ident) + "/cena/rodada", conta, ident, {
            "usuario": usuario or "", "narracao": narracao or "", "requisicao_id": str(uuid4()),
            "falas": [{"modelo_id": f["modelo_id"], "texto": f["texto"]} for f in falas],
            "contextos": {f["modelo_id"]: f["contexto_id"] for f in falas if f.get("contexto_id")}})
    except m.ErroModels:
        log.warning("Rodada da cena não registrada no Models")


def _ordem(texto, presentes, nomes, anfitria):
    """Quem fala primeiro: as chamadas pelo nome, na ordem em que aparecem; sem nome, a anfitriã."""
    citadas = sorted((p for p in presentes if _citado(nomes[p], texto)),
                     key=lambda p: _norm(texto).find(_norm(nomes[p])))
    if re.search(r"\b(?:voces|todas|meninas|as duas|as tres)\b", _norm(texto)):
        citadas = citadas or list(presentes)
    primeiras = citadas or [anfitria]
    return primeiras + [p for p in presentes if p not in primeiras]


def _palavras(t):
    return {w for w in re.findall(r"\w+", _norm(t)) if len(w) > 3}


def _repetida(texto, falas):
    """Fala que só ecoa outra (mesmas palavras) não vale uma mensagem nova."""
    novas = _palavras(texto)
    if len(novas) < 4:
        return False
    return any(len(novas & _palavras(f["texto"])) / len(novas | _palavras(f["texto"])) >= 0.6 for f in falas)


def _nova_geracao(conta_id):
    with _geracao_lock:
        _geracao[conta_id] = _geracao.get(conta_id, 0) + 1
        return _geracao[conta_id]


def _vigente(conta_id, geracao):
    return _geracao.get(conta_id) == geracao


def _continuar(conta, texto, presentes, nomes, ordem, limite, falas, prazo=None, entregar=None, geracao=None):
    """Uma fala de cada vez, cada uma respondendo à anterior, enquanto houver assunto, limite e tempo."""
    m = _m()
    contagem = {p: sum(1 for f in falas if f["modelo_id"] == p) for p in presentes}
    caladas = set()
    while len(falas) < limite * len(presentes):
        if prazo is not None and time.monotonic() > prazo:
            break
        if geracao is not None and not _vigente(conta.id, geracao):
            break
        ultima = falas[-1]
        citadas = [p for p in presentes if p != ultima["modelo_id"] and contagem[p] < limite and _citado(nomes[p], ultima["texto"])]
        novas = [p for p in ordem if contagem[p] == 0 and p != ultima["modelo_id"] and p not in caladas]
        proxima = next(iter(citadas + novas), None)
        if not proxima:
            break
        try:
            f = _fala(conta, proxima, presentes, nomes, texto, falas, primeira=contagem[proxima] == 0,
                      pode_calar=True, reagir=ultima)
        except m.ErroModels:
            break
        if not f or _repetida(f["texto"], falas):
            caladas.add(proxima)
            if proxima in citadas:
                break
            continue
        if geracao is not None and not _vigente(conta.id, geracao):
            break
        falas.append(f)
        contagem[proxima] += 1
        if entregar:
            entregar(f)
    return falas


def _em_segundo_plano(alvo, *args):
    threading.Thread(target=alvo, args=args, daemon=True, name="cena-models").start()


def _seguir_depois(conta_id, ident, texto, presentes, nomes, ordem, limite, falas, canal, geracao):
    """Gera as reações depois que a primeira fala já saiu e manda cada uma assim que fica pronta."""
    from canais import entrega
    from database import Conta, SessionLocal
    from nucleo import roteador
    m = _m()
    db = SessionLocal()
    try:
        conta = db.get(Conta, conta_id)
        vinculo = next((c for c in conta.canais if c.canal == canal), None) if conta else None
        if not vinculo:
            return

        def entregar(f):
            r = roteador.resposta_models(m.CenaModels([{"nome": f["nome"], "texto": f["texto"], "voz": f["voz"]}]))
            try:
                entrega.entregar(db, canal, vinculo.origem, r)
            except Exception:  # noqa: BLE001  a entrega nunca derruba a cena
                log.exception("Falha ao entregar fala da cena")

        _continuar(conta, texto, presentes, nomes, ordem, limite, falas, entregar=entregar, geracao=geracao)
        _registrar(conta, ident, texto, falas)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao continuar a cena")
        try:
            _registrar(conta, ident, texto, falas)
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


def rodada(conta, ident, texto, cena, canal=None):
    """Uma rodada da cena: uma modelo responde à mensagem; a outra responde ao que ela disse, e assim por diante.

    Cada fala é gerada depois da anterior, com o contexto da própria modelo. No WhatsApp e no Telegram a primeira
    fala sai na hora e as seguintes chegam uma a uma; no Bella.exe só cabe o que ficar pronto a tempo.
    """
    m = _m()
    inicio = time.monotonic()
    geracao = _nova_geracao(conta.id)
    presentes = [p["modelo_id"] for p in cena["presentes"]]
    nomes = {p["modelo_id"]: p["nome"] for p in cena["presentes"]}
    anfitria = next((p["modelo_id"] for p in cena["presentes"] if p.get("anfitria")), ident)
    limite = max(1, min(2, int(cena.get("limite_falas") or LIMITE_PADRAO)))
    ordem = _ordem(texto, presentes, nomes, anfitria)
    try:
        primeira = _fala(conta, ordem[0], presentes, nomes, texto, [], primeira=True, pode_calar=False)
    except m.ErroModels as e:
        return str(e)
    if not primeira:
        return "A cena ficou em silêncio. Fale com uma delas pelo nome."
    falas = [primeira]
    if canal in CANAIS_DEPOIS:
        _em_segundo_plano(_seguir_depois, conta.id, ident, texto, presentes, nomes, ordem, limite, list(falas), canal, geracao)
    else:
        _continuar(conta, texto, presentes, nomes, ordem, limite, falas, prazo=inicio + TEMPO_SINCRONO, geracao=geracao)
        _registrar(conta, ident, texto, falas)
    return m.CenaModels([{"nome": f["nome"], "texto": f["texto"], "voz": f["voz"]} for f in falas])


def _narrar(conta, ident, presentes, instrucao):
    """Narração curta (sem voz) da chegada ou da saída, a partir do contexto recente da anfitriã."""
    from nucleo import grok
    m = _m()
    ctx = m._montar_contexto(conta, ident, "[Narração da cena]", origem="iniciativa", presentes=presentes)
    recentes = "\n".join(f"Arquiteto: {v['usuario']}\nResposta: {v['texto']}" for v in ctx.get("historico", [])[-6:])
    sistema = ("Você é o narrador de uma conversa ficcional entre o Arquiteto e personagens adultas. Escreva de 1 a 3 frases, "
               "em terceira pessoa e no presente, sem falas entre aspas, sem nada íntimo ou explícito, sem inventar fatos "
               "importantes. Responda só com a narração.")
    texto = grok.gerar(sistema, f"Conversa recente:\n{recentes or '(sem conversa recente)'}\n\nO que narrar: {instrucao}",
                       max_tokens=300, historico=[])
    texto = (texto or "").strip().strip('"')
    return texto[:600] if texto else ""


def adicionar(conta, ident, nome):
    m = _m()
    if not conta.admin:
        return "Cenas com várias modelos estão disponíveis somente para o Arquiteto."
    if not nome:
        return "Use /addmodel seguido do nome. Exemplo: /addmodel Kellen"
    try:
        cena = m._requisicao("POST", m._rota(conta, ident) + "/cena/adicionar", conta, ident, {"nome": nome})
    except m.ErroModels:
        return f'Não consegui chamar "{nome}". Confira o nome, se ela está publicada e se a cena tem menos de 3 modelos.'
    presentes = [p["modelo_id"] for p in cena["presentes"]]
    nomes = {p["modelo_id"]: p["nome"] for p in cena["presentes"]}
    nova = presentes[-1]
    anfitria = nomes.get(ident, "a anfitriã")
    try:
        if not _voz(m.pacote(conta, nova)):
            raise m.ErroModels("sem voz")
    except m.ErroModels:
        _remover_silencioso(conta, ident, nova)
        return f"{nomes[nova]} ainda não pode entrar: falta uma voz principal ativa ou ela não está liberada."
    outras_presentes = ", ".join(nomes[p] for p in presentes if p != nova)
    narracao = _narrar(conta, ident, presentes,
        f"{nomes[nova]} chega à cena onde estão o Arquiteto e {outras_presentes}. Use o contexto: se o Arquiteto pediu "
        f"para {anfitria} chamar {nomes[nova]}, mostre {anfitria} chamando (ligação ou mensagem) e {nomes[nova]} chegando; "
        "se estão num lugar, ela chega ali (campainha, porta, entra); sem gancho, uma chegada natural para o momento.") \
        or f"{nomes[nova]} chega."
    falas = []
    try:
        f = _fala(conta, nova, presentes, nomes, "", [], instrucao=f"Você acabou de chegar. {narracao} Diga sua primeira fala ao chegar.",
                  pode_calar=False)
        if f:
            falas.append(f)
        reacao = _fala(conta, ident, presentes, nomes, "", falas,
                       instrucao=f"{nomes[nova]} acabou de chegar. {narracao} Reaja à chegada dela do seu jeito.",
                       primeira=False, pode_calar=True)
        if reacao:
            falas.append(reacao)
    except m.ErroModels as e:
        log.warning("Falha ao gerar a chegada: %s", type(e).__name__)
    _registrar(conta, ident, "", falas, narracao)
    return m.CenaModels([{"nome": "", "texto": "🎬 " + narracao, "voz": None},
                         *({"nome": f["nome"], "texto": f["texto"], "voz": f["voz"]} for f in falas)])


def _remover_silencioso(conta, ident, modelo_id):
    m = _m()
    try:
        m._requisicao("POST", m._rota(conta, ident) + "/cena/remover", conta, ident, {"outra_modelo_id": modelo_id})
    except m.ErroModels:
        pass


def remover(db, conta, ident, nome):
    m = _m()
    if not conta.admin:
        return "Cenas com várias modelos estão disponíveis somente para o Arquiteto."
    cena = cena_ativa(conta, ident)
    if not cena:
        return "Não há outra modelo na conversa agora."
    nomes = {p["modelo_id"]: p["nome"] for p in cena["presentes"]}
    presentes = list(nomes)
    sai = next((i for i, n in nomes.items() if _norm(n) == _norm(nome)), None)
    if not sai:
        return f'{nome or "Essa modelo"} não está na cena. Veja quem está com /modelos.'
    narracao = _narrar(conta, ident, presentes, f"{nomes[sai]} se despede e sai da cena (vai embora, desliga ou sai do lugar), "
                       "de um jeito coerente com o momento.") or f"{nomes[sai]} vai embora."
    falas = []
    try:
        f = _fala(conta, sai, presentes, nomes, "", [], instrucao=f"Você está saindo da cena. {narracao} Despeça-se.",
                  primeira=False, pode_calar=False)
        if f:
            falas.append(f)
    except m.ErroModels:
        pass
    _registrar(conta, ident, "", falas, narracao)
    try:
        r = m._requisicao("POST", m._rota(conta, ident) + "/cena/remover", conta, ident, {"outra_modelo_id": sai})
    except m.ErroModels:
        return "Não consegui tirar essa modelo da cena agora. Tente de novo."
    restante = r.get("restante")
    aviso = ""
    if restante and restante != ident:
        try:
            m.escolher(db, conta, restante)
            aviso = f"Agora a conversa segue só com {nomes.get(restante, 'ela')}."
        except m.ErroModels:
            pass
    elif restante:
        aviso = f"Agora a conversa segue só com {nomes.get(restante, 'ela')}."
    itens = [{"nome": "", "texto": "🎬 " + narracao, "voz": None},
             *({"nome": f["nome"], "texto": f["texto"], "voz": f["voz"]} for f in falas)]
    if aviso:
        itens.append({"nome": "", "texto": aviso, "voz": None})
    return m.CenaModels(itens)


def quem(conta, ident):
    m = _m()
    cena = cena_ativa(conta, ident)
    if not cena:
        try:
            nome = m.pacote(conta, ident)["nome"]
        except m.ErroModels:
            nome = "a modelo escolhida"
        return f"Só {nome} está na conversa. Chame outra com /addmodel Nome."
    nomes = [p["nome"] + (" (anfitriã)" if p.get("anfitria") else "") for p in cena["presentes"]]
    return "Na cena: " + ", ".join(nomes) + ". Fale com uma delas pelo nome; /removemodel Nome faz alguém sair."
