# -*- coding: utf-8 -*-
"""
O ROTEADOR — o cérebro do hub.

Recebe o que chegou de um canal (texto ou toque) e devolve o que dizer.
Não fala com Telegram nem com Evolution: por isso dá para testar tudo sem
rede. Os canais só entregam.

A ordem das decisões é a ordem deste arquivo:

  1. vínculo de canal (/start <token> ou "SOLO 123456") — roda sem conta
  2. sem conta → boas-vindas com o link do painel
  3. comandos do hub (/menu, /sair, /conta, /ajuda, /fin, /rot…)
  4. modo ativo → o texto vai para o sistema
  5. hub → pergunta "para qual sistema?" (ou vai direto, se só houver um)
"""
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import config
from database import (Atividade, CanalVinculo, CodigoCanal, Conta, MensagemProcessada,
                      Sessao, TentativaCanal, VinculoSistema)
from nucleo import modulos, render

log = logging.getLogger("solobot.roteador")

CANAIS = ("telegram", "whatsapp")
SAUDACOES = {"oi", "ola", "olá", "menu", "inicio", "início", "hey", "bom dia", "boa tarde", "boa noite"}
RE_WHATS = re.compile(r"^\s*solo\s*[-:]?\s*(\d{6})\s*$", re.IGNORECASE)


@dataclass
class Resposta:
    mensagens: List[dict] = field(default_factory=list)   # [{texto, opcoes}]
    curta: Optional[str] = None                            # toast do Telegram

    def diz(self, texto: str, opcoes=None, audio=None) -> "Resposta":
        m = {"texto": texto, "opcoes": opcoes or []}
        if audio:
            m["audio"] = audio                           # {base64, mime}: voz depois do texto
        self.mensagens.append(m)
        return self


# ══════════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════════
def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def ja_processada(db: Session, canal: str, id_externo: Optional[str]) -> bool:
    if not id_externo:
        return False
    db.add(MensagemProcessada(canal=canal, id_externo=str(id_externo)[:120]))
    try:
        db.commit()
        return False
    except IntegrityError:
        db.rollback()
        return True


def sessao_de(db: Session, canal: str, origem: str) -> Sessao:
    s = db.query(Sessao).filter(Sessao.canal == canal, Sessao.origem == str(origem)).first()
    if not s:
        s = Sessao(canal=canal, origem=str(origem))
        db.add(s)
        db.commit()
    return s


def conta_de(db: Session, canal: str, origem: str) -> Optional[Conta]:
    if canal in ("siri", "bella"):
        # Os canais diretos autenticam suas chaves antes de construir a
        # origem "<canal>:<conta>" em routers/atalho.py e routers/bella.py.
        try:
            c = db.get(Conta, int(str(origem).split(":", 1)[1]))
        except (IndexError, ValueError):
            return None
        return c if c and c.ativo else None
    v = db.query(CanalVinculo).filter(CanalVinculo.canal == canal,
                                      CanalVinculo.origem == str(origem)).first()
    return v.conta if v and v.conta.ativo else None


def _registrar(db: Session, conta: Conta, canal: str, app: Optional[str], tipo: str, resumo: str):
    db.add(Atividade(conta_id=conta.id, canal=canal, app=app, tipo=tipo, resumo=resumo[:120]))
    db.commit()


def _resumo_comando(texto: str) -> str:
    """Só a cabeça do comando. Texto livre vira 'mensagem' — nunca o conteúdo."""
    t = (texto or "").strip()
    if t.startswith("/"):
        return t.split()[0][:40]
    return "mensagem"


def _modo_valido(s: Sessao) -> Optional[str]:
    if not s.modo or not s.modo_em:
        return None
    if datetime.utcnow() - s.modo_em > timedelta(minutes=config.MODO_MINUTOS):
        return None
    return s.modo


def _entrar_modo(db: Session, s: Sessao, app: Optional[str]):
    s.modo = app
    s.modo_em = datetime.utcnow() if app else None
    db.commit()


def _sistemas_da_conta(db: Session, conta: Conta) -> list:
    """Os módulos a que esta conta está ligada, na ordem do registro."""
    ligados = {v.app for v in conta.sistemas}
    return [m for m in modulos.todos() if m.chave in ligados]


def _primeiro_nome(conta: Conta) -> str:
    return (conta.nome or "").split()[0] if conta.nome else ""


def _comando_de_modulo(cmd: str) -> Optional[modulos.Modulo]:
    """`/fin`, `/rot`, e também `/finances`, `/rotinas`, `/routines`."""
    nome = cmd.lstrip("/").lower()
    m = modulos.por_chave(nome)
    if m:
        return m
    for mod in modulos.todos():
        apelidos = {_sem_acento(mod.nome.lower().replace("solo ", ""))}
        if mod.chave == "rot":
            apelidos |= {"rotina", "rotinas", "routines"}
        if mod.chave == "fin":
            apelidos |= {"financas", "finances", "financeiro"}
        if _sem_acento(nome) in apelidos:
            return mod
    return None


# ══════════════════════════════════════════════════════════════════════
# 1. VÍNCULO DE CANAL
# ══════════════════════════════════════════════════════════════════════
def gerar_codigo(db: Session, conta: Conta, canal: str) -> CodigoCanal:
    from seguranca import token_curto, token_longo
    if canal not in CANAIS:
        raise ValueError("canal inválido")
    db.query(CodigoCanal).filter(CodigoCanal.conta_id == conta.id, CodigoCanal.canal == canal,
                                 CodigoCanal.usado_em.is_(None)).delete()
    for _ in range(8):
        codigo = token_longo() if canal == "telegram" else token_curto()
        if not db.query(CodigoCanal).filter(CodigoCanal.codigo == codigo).first():
            break
    c = CodigoCanal(conta_id=conta.id, canal=canal, codigo=codigo,
                    expira_em=datetime.utcnow() + timedelta(minutes=config.CODIGO_MINUTOS))
    db.add(c)
    db.commit()
    return c


def _bloqueado(db: Session, canal: str, origem: str) -> bool:
    t = db.query(TentativaCanal).filter(TentativaCanal.canal == canal,
                                        TentativaCanal.origem == origem).first()
    return bool(t and t.bloqueado_ate and t.bloqueado_ate > datetime.utcnow())


def _anotar_erro(db: Session, canal: str, origem: str):
    t = db.query(TentativaCanal).filter(TentativaCanal.canal == canal,
                                        TentativaCanal.origem == origem).first()
    if not t:
        t = TentativaCanal(canal=canal, origem=origem, erros=0)
        db.add(t)
    t.erros = (t.erros or 0) + 1
    if t.erros >= config.TENTATIVAS_MAX:
        t.bloqueado_ate = datetime.utcnow() + timedelta(minutes=config.CASTIGO_MINUTOS)
        t.erros = 0
    db.commit()


def vincular_canal(db: Session, canal: str, origem: str, codigo: str,
                   rotulo: Optional[str] = None) -> Resposta:
    r = Resposta()
    origem = str(origem)
    if _bloqueado(db, canal, origem):
        return r.diz("⏳ Muitas tentativas erradas. Espere alguns minutos e gere um código novo no painel.")

    c = db.query(CodigoCanal).filter(CodigoCanal.codigo == codigo.strip(),
                                     CodigoCanal.canal == canal).first()
    if not c or c.usado_em or c.expira_em < datetime.utcnow():
        _anotar_erro(db, canal, origem)
        return r.diz("❌ Esse código não vale mais. Gere outro no painel do Solo Bot.")

    conta = db.get(Conta, c.conta_id)
    c.usado_em = datetime.utcnow()
    # Esta origem pode estar em outra conta; esta conta pode ter outra origem.
    db.query(CanalVinculo).filter(CanalVinculo.canal == canal, CanalVinculo.origem == origem).delete()
    db.query(CanalVinculo).filter(CanalVinculo.conta_id == conta.id, CanalVinculo.canal == canal).delete()
    db.add(CanalVinculo(conta_id=conta.id, canal=canal, origem=origem, rotulo=(rotulo or "")[:80]))
    db.commit()
    _registrar(db, conta, canal, None, "canal", f"{canal.capitalize()} conectado")
    return menu(db, conta, prefixo=f"✅ Pronto, {_primeiro_nome(conta) or 'tudo certo'}! "
                                   f"Este {'chat' if canal == 'telegram' else 'número'} agora é da sua Conta Solo.\n\n")


# ══════════════════════════════════════════════════════════════════════
# 3. O HUB
# ══════════════════════════════════════════════════════════════════════
def _boas_vindas() -> Resposta:
    """Para quem não tem conta. Por padrão, NADA: o bot não existe para estranhos
    (config.RESPONDER_DESCONHECIDOS). Código de vínculo continua respondendo."""
    if not config.RESPONDER_DESCONHECIDOS:
        return Resposta()
    return Resposta().diz(
        "👋 Olá! Eu sou o *Solo Bot*.\n\n"
        "Falo por todos os seus sistemas Solo num lugar só. Para começar:\n\n"
        f"1. Crie sua Conta Solo em {config.URL_PUBLICA}\n"
        "2. No painel, toque em *Conectar* neste aplicativo\n\n"
        "_Leva menos de um minuto._"
    )


def menu(db: Session, conta: Conta, prefixo: str = "") -> Resposta:
    ligados = _sistemas_da_conta(db, conta)
    faltam = [m for m in modulos.todos() if m not in ligados]
    nome = _primeiro_nome(conta)
    corpo = prefixo or f"👋 Olá{', ' + nome if nome else ''}!\n\n"

    if ligados:
        corpo += "Com qual sistema vamos falar?\n"
        opcoes = [{"titulo": "", "acoes": [{"rotulo": f"{m.emoji} {m.nome.replace('Solo ', '')}",
                                            "dados": f"hub:app|{m.chave}"} for m in ligados]}]
        atalhos = " · ".join(f"`/{m.chave}`" for m in ligados)
        corpo += f"\n_Atalhos: {atalhos} · `/bella` conversa · `/sair` volta aqui._"
    else:
        opcoes = []
        corpo += ("Você ainda não conectou nenhum sistema.\n\n"
                  "Abra o *Solo Finances* ou o *Solo Rotinas*, vá em *Bots* e toque em "
                  "*Conectar ao Solo Bot*.")
    if ligados and faltam:
        corpo += "\n\nAinda não conectados: " + ", ".join(m.nome for m in faltam) + "."
    return Resposta().diz(corpo, opcoes)


def _ajuda_hub(db: Session, conta: Conta) -> Resposta:
    ligados = _sistemas_da_conta(db, conta)
    linhas = ["🧭 *Solo Bot — comandos*", ""]
    for m in ligados:
        linhas.append(f"▸ `/{m.chave}` — falar com o {m.emoji} {m.nome}")
        # O que o sistema declarou no manifesto dele: a ajuda do hub não
        # precisa ser reescrita a cada comando novo lá.
        from nucleo import manifestos
        cmds = [c for c in manifestos.comandos_visiveis(db, m.chave) if c["comando"] != "/ajuda"]
        for c in cmds[:8]:
            linhas.append(f"    `/{m.chave} {c['comando'].lstrip('/')}` — {c['descricao']}")
        if len(cmds) > 8:
            linhas.append(f"    _…e mais {len(cmds) - 8}: `/{m.chave} ajuda`_")
    linhas += [
        "▸ `/menu` — o cartão inicial",
        "▸ `/sair` — volta ao hub",
        "▸ `/conta` — canais e sistemas ligados",
        "▸ `/bella` — conversar com a Bella (modo adulto, `/esquecer` limpa a memória)",
        "▸ `/clonarvoz Nome` — (administrador) cria uma voz clonada no VoiceStudio com o próximo áudio; `/clonarvoz repetir` tenta de novo",
        "▸ `/vozes` · `/usarvoz Nome` · `/testarvoz` · `/apagarvoz` — (administrador) lista, escolhe, testa e apaga vozes do VoiceStudio",
        "▸ `/prompt` — a Bella cria um prompt de imagem (realismo sensual): `/prompt cozinha, cosplay de odalisca`",
        "▸ `/promptmodelo` — cria uma modelo nova do zero (19 anos, tudo aleatório): `/promptmodelo cabelo ruivo, pele morena, biquíni na praia`",
        "▸ `/promptroupa` — descreve uma roupa (da foto que você mandar ou do pedido) para vestir em outra imagem, sem mexer no resto: `/promptroupa lingerie preta de renda`",
        "▸ `/posehot` — prompt de pose sensual (uma pessoa, sozinha) para aplicar em outra imagem, da foto que você mandar ou do pedido: `/posehot de bruços olhando para trás`",
        "▸ `/promptcriativo` — a Bella inventa um prompt fora da biblioteca, sem repetir os que já saíram: `/promptcriativo praia`",
        "▸ `/voz` — responder falando (áudio, sempre ou nunca)",
        "",
        "_Dentro de um sistema, `/ajuda` mostra os comandos dele. "
        f"O modo dura {config.MODO_MINUTOS} min sem mensagem._",
    ]
    return Resposta().diz("\n".join(linhas))


VOZ_ROTULO = {"audio": "falo quando você manda áudio", "sempre": "falo sempre",
              "nunca": "respondo só por escrito"}
VOZ_APELIDO = {"on": "audio", "ligar": "audio", "audio": "audio", "áudio": "audio", "sempre": "sempre",
               "off": "nunca", "desligar": "nunca", "nunca": "nunca", "texto": "nunca"}


def _cmd_voz(db: Session, conta: Conta, arg: str) -> Resposta:
    from nucleo import fala
    atual = conta.voz if conta.voz in VOZ_ROTULO else "audio"
    if not arg:
        extra = "" if fala.disponivel() else "\n\n⚠️ A voz ainda não está configurada no servidor."
        return Resposta().diz(
            f"🔊 *Voz:* {VOZ_ROTULO[atual]}.\n\n"
            "▸ `/voz audio` — falo quando você manda áudio\n"
            "▸ `/voz sempre` — falo sempre\n"
            "▸ `/voz nunca` — só por escrito" + extra)
    novo = VOZ_APELIDO.get(arg)
    if not novo:
        return Resposta().diz("Use `/voz audio`, `/voz sempre` ou `/voz nunca`.")
    conta.voz = novo
    db.commit()
    _registrar(db, conta, None, None, "conta", f"Voz: {VOZ_ROTULO[novo]}")
    return Resposta().diz(f"🔊 Pronto: {VOZ_ROTULO[novo]}.")


def _conta_resumo(db: Session, conta: Conta) -> Resposta:
    canais = {c.canal: c for c in conta.canais}
    linhas = [f"👤 *{conta.nome}*", f"_{conta.usuario or conta.email}_", "", "*Canais*"]
    for canal, rotulo in (("telegram", "Telegram"), ("whatsapp", "WhatsApp")):
        linhas.append(f"{'🟢' if canal in canais else '⚪'} {rotulo}")
    linhas += ["", "*Sistemas*"]
    ligados = {v.app: v for v in conta.sistemas}
    for m in modulos.todos():
        v = ligados.get(m.chave)
        linhas.append(f"{'🟢' if v else '⚪'} {m.emoji} {m.nome}" + (f" — {v.nome_remoto}" if v and v.nome_remoto else ""))
    linhas += ["", f"Painel: {config.URL_PUBLICA}/painel"]
    return Resposta().diz("\n".join(linhas))


# ══════════════════════════════════════════════════════════════════════
# 4. O SISTEMA
# ══════════════════════════════════════════════════════════════════════
def _vinculo(conta: Conta, app: str) -> Optional[VinculoSistema]:
    return next((v for v in conta.sistemas if v.app == app), None)


def _nao_conectado(mod: modulos.Modulo) -> Resposta:
    return Resposta().diz(
        f"{mod.emoji} Você ainda não conectou o *{mod.nome}*.\n\n"
        f"Abra o {mod.nome}, vá em *Bots* e toque em *Conectar ao Solo Bot*."
    )


def _traduzir(mod: modulos.Modulo, dados: dict, r: Resposta) -> Resposta:
    msgs = dados.get("mensagens") or []
    for i, m in enumerate(msgs):
        texto = (m.get("texto") or "").strip()
        if i == 0:
            texto = f"{mod.selo}\n{texto}" if texto else mod.selo
        audio = m.get("audio") if isinstance(m.get("audio"), dict) else None
        r.diz(texto, render.prefixar(m.get("opcoes"), mod.chave), audio)
        if m.get("falado"):
            r.mensagens[-1]["falado"] = str(m["falado"])[:900]   # a versão para ouvir, feita pelo sistema
    if dados.get("curta"):
        r.curta = str(dados["curta"])[:190]
    return r


def _desvinculado_la(db: Session, conta: Conta, mod: modulos.Modulo, dados: dict) -> bool:
    """O sistema avisou que aquele usuário não existe mais: o vínculo cai aqui também."""
    if not dados.get("desvinculado"):
        return False
    v = _vinculo(conta, mod.chave)
    if v:
        db.delete(v)
        db.commit()
    return True


def para_sistema(db: Session, conta: Conta, canal: str, origem: str, mod: modulos.Modulo,
                 texto: Optional[str] = None, dados: Optional[str] = None,
                 resumo: Optional[str] = None, via_audio: bool = False,
                 audio: Optional[tuple] = None) -> Resposta:
    v = _vinculo(conta, mod.chave)
    if not v:
        return _nao_conectado(mod)
    corpo = {"usuario_id": v.usuario_id, "canal": canal, "origem": f"solo:{conta.id}:{canal}",
             "nome": conta.nome}
    if dados is not None:
        rota, corpo["dados"] = "acao", dados
    elif audio is not None:
        # O sistema entende áudio (manifesto): vão os bytes, e a inteligência é dele.
        import base64
        rota = "mensagem"
        corpo["audio_base64"] = base64.b64encode(audio[0]).decode("ascii")
        corpo["mime"] = audio[1]
    else:
        rota, corpo["texto"] = "mensagem", texto or "/ajuda"
        if via_audio:
            corpo["via_audio"] = True                    # o texto veio de uma transcrição
    try:
        resp = modulos.chamar(mod, rota, corpo)
    except modulos.ErroModulo as e:
        return Resposta(curta=str(e)[:190]).diz(f"⚠️ {e}")
    if _desvinculado_la(db, conta, mod, resp):
        return _nao_conectado(mod)
    _registrar(db, conta, canal, mod.chave, "comando",
               resumo or ("toque" if dados is not None else "áudio" if audio is not None
                          else _resumo_comando(texto or "")))
    return _traduzir(mod, resp, Resposta())


# ══════════════════════════════════════════════════════════════════════
# A ENTRADA — texto
# ══════════════════════════════════════════════════════════════════════
def _pedido_com_prefixo(db: Session, mod: modulos.Modulo, texto: str) -> str:
    """/fin saldo -> /saldo; frases livres e argumentos continuam intactos."""
    from nucleo import manifestos
    texto = texto.strip()
    if not texto:
        return "/ajuda"
    palavra = texto.split(maxsplit=1)[0]
    if palavra.startswith("/"):
        return texto
    comando = "/" + palavra.lower()
    anunciados = {c["comando"] for c in (manifestos.de(db, mod.chave) or {}).get("comandos", [])}
    if comando in anunciados or comando in {"/ajuda", "/help"}:
        return comando + texto[len(palavra):]
    return texto


def _resposta_colada(texto: str) -> bool:
    """Reconhece respostas copiadas, sem bloquear lançamentos com várias linhas."""
    if "\n" not in texto:
        return False
    linhas = [_sem_acento(l.lower()).strip(" *_`⚠️❌✅💰⚔️") for l in texto.splitlines()]
    selos = {_sem_acento(m.nome.replace("Solo ", "").lower()) for m in modulos.todos()}
    return any(l in selos or l.startswith(("nao identifiquei o valor", "registrado com sucesso",
                                           "errou? mande /desfazer"))
               or l.startswith("nao consegui conectar ao solo ")
               or (l.startswith("solo ") and any(e in l for e in ("nao respondeu", "demorou para responder")))
               for l in linhas)


def atender_texto(db: Session, canal: str, origem: str, texto: str,
                  rotulo: Optional[str] = None, via_audio: bool = False) -> Resposta:
    origem = str(origem)
    txt = (texto or "").strip()
    s = sessao_de(db, canal, origem)

    # 1. vínculo — antes de tudo, porque roda sem conta
    if canal == "telegram" and txt.lower().startswith("/start "):
        return vincular_canal(db, canal, origem, txt.split(maxsplit=1)[1], rotulo)
    m = RE_WHATS.match(txt)
    if m and canal == "whatsapp":
        return vincular_canal(db, canal, origem, m.group(1), rotulo)

    # 2. sem conta
    conta = conta_de(db, canal, origem)
    if not conta:
        return _boas_vindas()

    if _resposta_colada(txt):
        return Resposta().diz("📋 Isso parece uma resposta do bot copiada. "
                              "Envie somente o seu comando ou lançamento, sem os exemplos da resposta, "
                              "para evitar registros indevidos.")

    pendente = _apagar_pendente(db, conta, canal, origem, txt)
    if pendente is not None:
        return pendente

    # WhatsApp: um número responde à última lista
    if canal in ("whatsapp", "siri", "bella") and txt.isdigit() and s.escolhas:
        escolhido = _resgatar_escolha(db, s, int(txt))
        if escolhido:
            return atender_toque(db, canal, origem, escolhido["dados"])

    # 3. comandos do hub
    cabeca, _, resto = txt.partition(" ")
    cmd = cabeca.lower().split("@")[0]
    simples = _sem_acento(txt.lower()).strip("!.?")

    if cmd in ("/start", "/menu") or simples in {_sem_acento(x) for x in SAUDACOES}:
        _entrar_modo(db, s, None)
        return menu(db, conta)
    if cmd == "/sair":
        _entrar_modo(db, s, None)
        return menu(db, conta, prefixo="↩️ De volta ao hub.\n\n")
    if cmd == "/conta":
        return _conta_resumo(db, conta)
    if cmd == "/voz":
        return _cmd_voz(db, conta, resto.strip().lower())
    if cmd in ("/prompt", "/promptmodelo", "/promptroupa", "/posehot", "/promptcriativo"):
        padrao = {"/promptmodelo": "modelo", "/promptroupa": "roupa", "/posehot": "pose",
                  "/promptcriativo": "criativo"}.get(cmd, "realismo")
        pedido = prompts_bella_pedido(txt, canal, conta) or (padrao, "")
        return _prompt_responder(db, conta, canal, pedido[1], pedido[0])
    if cmd in ("/bella", "/safada"):
        _entrar_modo(db, s, MODO_BELLA)
        return _bella_entrar(canal, conta, resto.strip())
    if cmd == "/clonarvoz":
        return _cmd_clonarvoz(conta, canal, origem, resto.strip())
    if cmd == "/apagarvoz":
        return _cmd_apagarvoz(db, conta, canal, origem, resto.strip())
    if cmd in ("/vozes", "/usarvoz", "/testarvoz"):
        return _cmd_vozes(db, conta, cmd, resto.strip(), canal)
    if cmd == "/esquecer":
        from nucleo import bella_conversa
        bella_conversa.esquecer(_chave_bella(canal, conta))
        return Resposta().diz("🧹 Pronto, esqueci o que conversamos.")

    if cmd.startswith("/"):
        mod = _comando_de_modulo(cmd)
        if mod:
            if not _vinculo(conta, mod.chave):
                return _nao_conectado(mod)
            _entrar_modo(db, s, mod.chave)
            return para_sistema(db, conta, canal, origem, mod, texto=_pedido_com_prefixo(db, mod, resto),
                                resumo=f"/{mod.chave}", via_audio=via_audio)

    modo = _modo_valido(s)

    if modo in (None, MODO_BELLA):
        pedido_prompt = prompts_bella_pedido(txt, canal, conta)
        if pedido_prompt is not None:
            return _prompt_responder(db, conta, canal, pedido_prompt[1], pedido_prompt[0])

    if modo == MODO_BELLA:
        _entrar_modo(db, s, MODO_BELLA)          # renova a validade
        return _bella_responder(db, conta, canal, txt)

    if cmd in ("/ajuda", "/help", "ajuda") and not modo:
        return _ajuda_hub(db, conta)

    ligados = _sistemas_da_conta(db, conta)

    from nucleo import intencao
    candidatos = [modulos.por_chave(modo)] if modo else ligados
    sugestao = (intencao.Intencao() if intencao.comando_literal(db, txt, ligados, modo).app else
                intencao.sugerir_literal(db, txt, [m for m in candidatos if m]))
    if sugestao.mensagem:
        nome = sugestao.mensagem.lstrip("/")
        verbo = "diga" if via_audio or canal == "bella" else "envie"
        return Resposta().diz(f"🤔 Você quis dizer “{nome}”? Se for isso, {verbo} “{nome}”.")

    # 4. modo ativo
    if modo:
        mod = modulos.por_chave(modo)
        if mod:
            _entrar_modo(db, s, modo)            # renova a validade
            return _com_intencao(db, conta, canal, origem, txt, ligados, via_audio, mod)

    # 5. hub com texto livre
    it = intencao.interpretar(db, txt, ligados) if ligados else intencao.Intencao()

    # Papo livre: se não é de nenhum sistema, quem responde é a Bella.
    if (not it.app or it.confianca < intencao.CONFIANCA_MINIMA) and not txt.startswith("/") and not (ligados and any(c.isdigit() for c in txt)):
        papo = _bella_responder(db, conta, canal, txt, so_se_responder=True)
        if papo:
            return papo

    if not ligados:
        return menu(db, conta)
    if len(ligados) == 1:
        _entrar_modo(db, s, ligados[0].chave)
        return _com_intencao(db, conta, canal, origem, txt, ligados, via_audio, ligados[0], intencao_previa=it)

    # Entender pelo que foi dito, antes de perguntar.
    alvo = modulos.por_chave(it.app) if it.app else None
    if alvo and it.mensagem:
        _entrar_modo(db, s, alvo.chave)
        return _entregar_intencao(db, conta, canal, origem, alvo, txt, it, via_audio)

    s.pendente = txt[:1000]
    db.commit()
    opcoes = [{"titulo": "", "acoes": [{"rotulo": f"{m.emoji} {m.nome.replace('Solo ', '')}",
                                        "dados": f"hub:app|{m.chave}"} for m in ligados]}]
    return Resposta().diz("🤔 Para qual sistema é isso?", opcoes)


# ── Modo Bella: conversa pessoal (a mesma do Bella.exe), sem sistemas ──
MODO_BELLA = "bella"


def _chave_bella(canal: str, conta: Conta) -> str:
    return f"{canal}:{conta.id}"          # memória própria deste canal, separada do Bella.exe


def prompts_bella_pedido(txt: str, canal: str, conta: Conta):
    """(categoria, pedido) se a mensagem pede um prompt; senão None."""
    from nucleo import prompts_bella
    return prompts_bella.solicitacao(txt, _chave_bella(canal, conta))


def _prompt_responder(db, conta: Conta, canal: str, pedido: str, categoria: str = "realismo") -> Resposta:
    """A Bella cria um prompt de imagem (realismo sensual). A voz diz só que está pronto."""
    from nucleo import prompts_bella
    try:
        extra = {"suave": True} if getattr(conta, "prompt_suave", False) else {}      # "Sem sensualização" da conta
        texto = prompts_bella.criar(pedido, _chave_bella(canal, conta), categoria, **extra)
    except prompts_bella.Recusa as erro:
        return Resposta().diz(f"🖼️ Não criei o prompt: {erro}.")
    if not texto:
        from nucleo import grok as _grok
        motivo = _grok.motivo()
        return Resposta().diz("😶 Não consegui criar o prompt agora" + (f": {motivo}." if motivo else ".") + " Tente de novo em instantes.")
    _registrar(db, conta, canal, None, "bella", "prompt")
    r = Resposta().diz(texto)
    r.mensagens[-1]["falado"] = prompts_bella.FALADO
    r.mensagens[-1]["prompt"] = True        # o Bella.exe mostra numa caixa de texto para copiar
    return r


def _bella_entrar(canal: str, conta: Conta, primeira: str) -> Resposta:
    if primeira:
        return _bella_responder(None, conta, canal, primeira)
    return Resposta().diz("💋 Oi, sou a Bella. Pode falar. `/esquecer` apaga a conversa, `/sair` volta ao hub.")


def _bella_responder(db, conta: Conta, canal: str, txt: str, so_se_responder: bool = False) -> Optional[Resposta]:
    from nucleo import bella_conversa
    texto = bella_conversa.responder(txt, _chave_bella(canal, conta))
    if not texto and so_se_responder:
        return None                          # sem Grok: o hub segue como antes
    if db is not None:
        _registrar(db, conta, canal, None, "bella", "conversa")
    if not texto:
        return Resposta().diz("😶 Não consegui responder agora. Tente de novo em instantes.")
    r = Resposta().diz(texto)
    r.mensagens[-1]["literal"] = True        # a voz LÊ o que a Bella disse; nunca passa por resumo de IA
    return r


def _entregar_intencao(db, conta, canal, origem, mod, txt, it, via_audio) -> Resposta:
    """Manda o que a intenção decidiu, e mostra em uma linha o que foi entendido."""
    r = para_sistema(db, conta, canal, origem, mod, texto=it.mensagem, via_audio=via_audio)
    if it.mensagem != txt and r.mensagens:
        nota = f"🧭 _Entendi: {mod.nome.replace('Solo ', '')} · `{it.mensagem}`_"
        r.mensagens[0]["texto"] = f"{nota}\n\n{r.mensagens[0]['texto']}"
    return r


def _com_intencao(db, conta, canal, origem, txt, ligados, via_audio, mod, intencao_previa=None) -> Resposta:
    """
    Texto livre com um sistema já definido (modo ativo, ou único conectado).

      · Comando ("/..."): vai direto, como sempre.
      · Comando anunciado sem barra: ganha a barra, preservando argumentos.
      · O sistema entende texto livre (Finances): vai direto, A NÃO SER que as
        palavras também apontem para outro sistema ou sejam uma consulta —
        aí a IA traduz e, com confiança alta, pode trocar de sistema.
      · O sistema só entende comandos (Rotinas): a IA traduz a frase para o
        comando ("o que tem pra hoje" → "/hoje").
    """
    from nucleo import intencao
    if txt.startswith("/"):
        return para_sistema(db, conta, canal, origem, mod, texto=txt, via_audio=via_audio)
    literal = intencao.comando_literal(db, txt, ligados or [mod], modo=mod.chave)
    livre = intencao.aceita_texto_livre(db, mod.chave)
    consulta = intencao.eh_consulta(txt)
    if livre and not literal.app and not consulta:
        outros = [m for m in ligados if m.chave != mod.chave]
        pontos = intencao.por_palavras(db, txt, [mod] + outros)
        if not any(pontos.get(m.chave) for m in outros):
            return para_sistema(db, conta, canal, origem, mod, texto=txt, via_audio=via_audio)
    # No hub com um único sistema, essa mesma mensagem já foi interpretada.
    # Reutiliza também o resultado vazio: uma falha não justifica repetir a IA.
    it = literal if literal.app else intencao_previa
    if it is None:
        it = intencao.interpretar(db, txt, ligados or [mod], modo=mod.chave)
    if it.app and it.app != mod.chave and it.confianca >= intencao.CONFIANCA_TROCA and it.mensagem:
        outro = modulos.por_chave(it.app)
        if outro and _vinculo(conta, outro.chave):
            _entrar_modo(db, sessao_de(db, canal, origem), outro.chave)
            return _entregar_intencao(db, conta, canal, origem, outro, txt, it, via_audio)
    if it.app == mod.chave and it.mensagem:
        return _entregar_intencao(db, conta, canal, origem, mod, txt, it, via_audio)
    if consulta:
        return Resposta().diz("🤔 Não consegui identificar essa consulta. Use /ajuda para ver os comandos.")
    return para_sistema(db, conta, canal, origem, mod, texto=txt, via_audio=via_audio)


# ══════════════════════════════════════════════════════════════════════
# A ENTRADA — áudio
# ══════════════════════════════════════════════════════════════════════
def atender_imagem(db: Session, canal: str, origem: str, conteudo: bytes, mime: str,
                   legenda: str = "", rotulo: Optional[str] = None) -> Resposta:
    """Imagem de referência para os prompts da Bella: só a roupa, a menos que o pedido peça mais."""
    from nucleo import prompts_bella
    origem = str(origem)
    conta = conta_de(db, canal, origem)
    if not conta:
        return _boas_vindas()
    chave = _chave_bella(canal, conta)
    erro = prompts_bella.guardar_referencia(chave, mime, conteudo)
    if erro:
        return Resposta().diz(erro)
    pedida = prompts_bella.solicitacao(legenda, chave)
    if pedida and pedida[0] != "realismo":          # legenda "/promptmodelo", "/promptroupa" ou "/posehot ..."
        return _prompt_responder(db, conta, canal, pedida[1], pedida[0])
    pedido = prompts_bella.pedido_da_legenda(legenda, chave)
    if pedido:
        return _prompt_responder(db, conta, canal, pedido)
    return Resposta().diz(
        "📎 Recebi a referência (vale por 15 min). Vou usar só a *roupa*.\n\n"
        "Agora diga o resto: `/prompt bar à noite`.\n"
        "Para usar também o penteado, a maquiagem ou o cenário da foto, peça: "
        "`/prompt use o penteado e o cenário da foto`.\n"
        "`/promptmodelo` cria uma modelo nova a partir das características da foto.\n"
        "`/promptroupa` descreve toda a roupa da foto para vestir em outra imagem.\n"
        "`/posehot` copia a pose da foto para aplicar em outra imagem.\n"
        "`/promptcriativo` usa a foto como roupa e inventa o resto.\n"
        "`/prompt sem referência ...` descarta a imagem.")


# ── /clonarvoz: o próximo áudio da conta administradora vira uma voz clonada no VoiceStudio ──
_CLONAR = {}                     # (canal, origem) -> (validade monotônica, nome); só na RAM, de propósito
CLONAR_ESPERA = 10 * 60
CLONAR_MIN_SEGUNDOS = 5


def _cmd_clonarvoz(conta: Conta, canal: str, origem: str, nome: str) -> Resposta:
    import time
    from nucleo import voicestudio
    chave = (canal, str(origem))
    if not conta.admin:
        return Resposta().diz("🔒 Só a conta administradora pode criar vozes.")
    if nome.lower() in ("cancelar", "cancela", "sair"):
        _CLONAR.pop(chave, None)
        return Resposta().diz("Tudo bem, cancelei a clonagem de voz.")
    if not voicestudio.disponivel_servidor():
        return Resposta().diz("🎙️ O VoiceStudio não está configurado no servidor (VOICESTUDIO_URL).")
    if nome.lower() in ("repetir", "tentar de novo"):
        guardada = _AMOSTRAS.get(chave)
        if not guardada or guardada[0] < time.monotonic():
            _AMOSTRAS.pop(chave, None)
            return Resposta().diz("🎙️ Não tenho nenhuma amostra guardada para repetir. Use `/clonarvoz Nome` e mande o áudio.")
        return _criar_voz(canal, origem, guardada[1], guardada[2], guardada[3])
    if not nome:
        return Resposta().diz("🎙️ Diga o nome da voz: `/clonarvoz Bella Casa`. Depois mande um áudio de 10 a 60 segundos (o ideal é de 10 a 15s).")
    _CLONAR[chave] = (time.monotonic() + CLONAR_ESPERA, nome[:60])
    return Resposta().diz(
        f"🎙️ Vou criar a voz *{nome[:60]}*. Agora mande UM áudio falando normalmente, de 10 a 60 segundos, "
        "num lugar silencioso e sem música. Use só uma voz que é sua ou que você tem permissão para clonar. "
        "O computador com o VoiceStudio precisa estar ligado. `/clonarvoz cancelar` desiste.")


def entrega_aviso(canal: str, origem: str, texto: str):
    from canais import evolution, telegram
    if canal == "telegram":
        telegram.enviar(str(origem), texto)
    elif canal == "whatsapp":
        evolution.enviar(str(origem), render.para_whatsapp(texto))


def _receber_amostra_de_voz(conta: Conta, canal: str, origem: str, conteudo: bytes, mime: str,
                            segundos: int) -> Optional[Resposta]:
    """Resposta se este áudio era a amostra pedida; None se não havia pedido (segue o fluxo normal)."""
    import time
    from nucleo import voicestudio
    chave = (canal, str(origem))
    pedido = _CLONAR.get(chave)
    if not pedido:
        return None
    if pedido[0] < time.monotonic() or not conta.admin:
        _CLONAR.pop(chave, None)
        return None
    if 0 < segundos < CLONAR_MIN_SEGUNDOS:
        return Resposta().diz("🎙️ Esse áudio ficou curto. Mande um de pelo menos 10 segundos, falando normalmente.")
    _CLONAR.pop(chave, None)
    return _criar_voz(canal, origem, pedido[1], conteudo, mime)


_AMOSTRAS = {}                   # (canal, origem) -> (validade, nome, bytes, mime): só se a criação falhou
AMOSTRA_GUARDADA = 30 * 60


def _chave_nome(nome: str) -> str:
    return re.sub(r"\s+", " ", _sem_acento(nome or "").lower()).strip()


def _voz_existente(nome: str):
    from nucleo import voicestudio
    alvo = _chave_nome(nome)
    return next((v for v in voicestudio.listar_vozes(forcar=True) if _chave_nome(v["nome"]) == alvo), None)


def _criar_voz(canal: str, origem: str, nome: str, conteudo: bytes, mime: str) -> Resposta:
    """Cria a voz clonada. Não duplica nome; se falhar, guarda a amostra para `/clonarvoz repetir`."""
    import time
    from nucleo import voicestudio
    existe = _voz_existente(nome)
    if existe:
        return Resposta().diz(f"🎙️ Já existe uma voz chamada *{existe['nome']}*. Para usá-la: `/usarvoz {existe['nome']}`. "
                              "Para criar outra, escolha outro nome em `/clonarvoz`.")
    try:        # a criação leva de segundos a minutos (o VoiceStudio transcreve a amostra): avisa que chegou
        entrega_aviso(canal, origem, f"🎙️ Recebi a amostra. Criando a voz *{nome}*… pode levar 1 ou 2 minutos.")
    except Exception:  # noqa: BLE001
        pass
    r = voicestudio.criar_perfil(nome, conteudo, mime)
    if not r["ok"]:
        _AMOSTRAS[(canal, str(origem))] = (time.monotonic() + AMOSTRA_GUARDADA, nome, conteudo, mime)
        return Resposta().diz(f"🎙️ Não consegui criar a voz: {r['erro']}. Guardei a amostra por 30 minutos: "
                              "mande `/clonarvoz repetir` para tentar de novo sem reenviar o áudio.")
    _AMOSTRAS.pop((canal, str(origem)), None)
    return Resposta().diz(f"✅ Voz *{r['nome']}* criada. Para usar: `/usarvoz {r['nome']}` (e `/testarvoz` para ouvir).")


_APAGAR = {}                     # (canal, origem) -> (validade, [vozes mostradas]); só na RAM
APAGAR_ESPERA = 3 * 60


def _cmd_apagarvoz(db: Session, conta: Conta, canal: str, origem: str, resto: str) -> Resposta:
    import time
    from nucleo import voicestudio
    chave = (canal, str(origem))
    if not conta.admin:
        return Resposta().diz("🔒 Só a conta administradora pode apagar vozes.")
    if resto.lower() in ("cancelar", "cancela", "sair"):
        _APAGAR.pop(chave, None)
        return Resposta().diz("Tudo bem, não apaguei nada.")
    if not voicestudio.disponivel_servidor():
        return Resposta().diz("🎙️ O VoiceStudio não está configurado no servidor (VOICESTUDIO_URL).")
    vozes = voicestudio.listar_vozes(forcar=True)
    if not vozes:
        return Resposta().diz("🎙️ Não achei nenhuma voz no VoiceStudio (computador desligado ou sem conexão?).")
    _APAGAR[chave] = (time.monotonic() + APAGAR_ESPERA, list(vozes))
    atual = voicestudio.voz_id()
    linhas = [f"{i}. {v['nome']}{'  (em uso)' if v['voice_id'] == atual else ''}" for i, v in enumerate(vozes, 1)]
    return Resposta().diz("🗑️ *Apagar voz do VoiceStudio*\n" + "\n".join(linhas)
                          + "\n\nResponda com o *número* da voz que quer apagar. Não tem volta. "
                          "Vale por 3 minutos; `/apagarvoz cancelar` desiste.")


def _apagar_pendente(db: Session, conta: Conta, canal: str, origem: str, txt: str) -> Optional[Resposta]:
    """Se há uma lista de `/apagarvoz` esperando, um número apaga; qualquer outra mensagem cancela."""
    import time
    from database import gravar_config
    from nucleo import voicestudio
    chave = (canal, str(origem))
    pedido = _APAGAR.get(chave)
    if not pedido:
        return None
    if pedido[0] < time.monotonic() or not conta.admin:
        _APAGAR.pop(chave, None)
        return None
    if not txt.isdigit():
        if txt.lower().split(" ")[0].split("@")[0] != "/apagarvoz":
            _APAGAR.pop(chave, None)            # falou de outra coisa: a lista perde a validade
        return None
    _APAGAR.pop(chave, None)
    n = int(txt)
    vozes = pedido[1]
    if not 1 <= n <= len(vozes):
        _APAGAR[chave] = pedido                  # número fora da lista: pode tentar de novo
        return Resposta().diz(f"🗑️ Escolha um número de 1 a {len(vozes)}, ou `/apagarvoz cancelar`.")
    voz = vozes[n - 1]
    r = voicestudio.apagar_perfil(voz["voice_id"])
    if not r["ok"]:
        return Resposta().diz(f"🗑️ Não consegui apagar *{voz['nome']}*: {r['erro']}.")
    extra = ""
    if voicestudio.voz_id() == voz["voice_id"]:
        gravar_config(db, voicestudio.CHAVE_VOZ, "")
        extra = " Era a voz em uso: escolha outra com `/usarvoz`."
    if r.get("aviso"):
        extra += f" Atenção: {r['aviso']}."
    return Resposta().diz(f"✅ Voz *{voz['nome']}* apagada do VoiceStudio.{extra}")


def _cmd_vozes(db: Session, conta: Conta, cmd: str, resto: str, canal: str) -> Resposta:
    import time
    from database import gravar_config
    from nucleo import fala, voicestudio
    if not conta.admin:
        return Resposta().diz("🔒 Só a conta administradora pode mexer nas vozes.")
    if not voicestudio.disponivel_servidor():
        return Resposta().diz("🎙️ O VoiceStudio não está configurado no servidor (VOICESTUDIO_URL).")
    vozes = voicestudio.listar_vozes(forcar=True)
    if not vozes:
        return Resposta().diz("🎙️ Não achei nenhuma voz no VoiceStudio (computador desligado ou sem conexão?). "
                              "`/clonarvoz Nome` cria uma.")
    atual = voicestudio.voz_id()
    motor = fala.motor_escolhido()
    if cmd == "/vozes":
        linhas = [f"{i}. {v['nome']}{'  ✅ em uso' if v['voice_id'] == atual else ''}" for i, v in enumerate(vozes, 1)]
        nota = "" if motor == "voicestudio" else f"\n_O motor de voz está em *{motor}*: o VoiceStudio só fala quando o motor for VoiceStudio (ou a ElevenLabs falhar)._"
        return Resposta().diz("🎙️ *Vozes do VoiceStudio*\n" + "\n".join(linhas) + "\n\n`/usarvoz Nome` escolhe · `/testarvoz` ouve" + nota)
    if cmd == "/usarvoz":
        if not resto:
            return Resposta().diz("🎙️ Diga qual: `/usarvoz Nome` ou `/usarvoz 2` (veja `/vozes`).")
        achada = None
        if resto.isdigit() and 1 <= int(resto) <= len(vozes):
            achada = vozes[int(resto) - 1]
        else:
            alvo = _chave_nome(resto)
            exatas = [v for v in vozes if _chave_nome(v["nome"]) == alvo]
            parecidas = exatas or [v for v in vozes if alvo and alvo in _chave_nome(v["nome"])]
            if len(parecidas) > 1:
                return Resposta().diz("🎙️ Mais de uma voz combina: " + ", ".join(f"*{v['nome']}*" for v in parecidas[:6])
                                      + ". Escreva o nome completo ou use o número de `/vozes`.")
            achada = parecidas[0] if parecidas else None
        if not achada:
            return Resposta().diz(f"🎙️ Não achei a voz “{resto[:40]}”. Veja `/vozes`.")
        gravar_config(db, voicestudio.CHAVE_VOZ, achada["voice_id"])
        nota = "" if motor == "voicestudio" else f" Atenção: o motor está em *{motor}*; ela só fala quando o motor for VoiceStudio."
        return Resposta().diz(f"✅ Voz *{achada['nome']}* escolhida.{nota} `/testarvoz` para ouvir.")
    # /testarvoz
    frase = (resto or "Oi, aqui é a Bella. Se você está me ouvindo, a minha voz está funcionando.")[:200]
    nome = next((v["nome"] for v in vozes if v["voice_id"] == atual), None)
    if not voicestudio.disponivel():
        return Resposta().diz("🎙️ Escolha primeiro uma voz do VoiceStudio: `/usarvoz Nome`.")
    inicio = time.monotonic()
    audio = voicestudio.sintetizar(frase, "telegram" if canal == "telegram" else "whatsapp")
    segundos = time.monotonic() - inicio
    if not audio:
        return Resposta().diz("🎙️ O VoiceStudio não gerou o áudio agora (computador desligado, ocupado ou voz com problema). "
                              "Tente de novo em instantes.")
    r = Resposta().diz(f"🎙️ Voz *{nome or atual}* · gerada em {segundos:.1f} s")
    r.mensagens[-1]["audio"] = {"base64": audio["base64"], "mime": audio["mime"]}
    return r


def atender_audio(db: Session, canal: str, origem: str, conteudo: bytes, mime: str,
                  rotulo: Optional[str] = None, segundos: int = 0) -> Resposta:
    """
    Com vários sistemas, transcreve antes de escolher o destino pelo texto.
    Com um único sistema que entende áudio, entrega os bytes diretamente.
    A transcrição aparece no topo da resposta para conferir o que foi ouvido.
    """
    from nucleo import manifestos, voz
    origem = str(origem)
    conta = conta_de(db, canal, origem)
    if not conta:
        return _boas_vindas()
    if segundos > voz.MAX_SEGUNDOS or len(conteudo or b"") > voz.MAX_BYTES:
        return Resposta().diz(f"🎤 Áudio longo demais. Mande até {voz.MAX_SEGUNDOS} segundos.")
    if not conteudo:
        return Resposta().diz("🎤 Não consegui baixar o áudio. Tente de novo, ou mande por escrito.")

    amostra = _receber_amostra_de_voz(conta, canal, origem, conteudo, mime, segundos)
    if amostra is not None:
        return amostra

    s = sessao_de(db, canal, origem)
    modo = _modo_valido(s)
    ligados = _sistemas_da_conta(db, conta)
    alvo = modulos.por_chave(modo) if modo else (ligados[0] if len(ligados) == 1 else None)
    if len(ligados) == 1 and alvo and _vinculo(conta, alvo.chave) and manifestos.recebe_audio(db, alvo.chave):
        _entrar_modo(db, s, alvo.chave)
        return para_sistema(db, conta, canal, origem, alvo, audio=(conteudo, voz._limpo(mime)))

    try:
        texto = voz.transcrever(conteudo, mime)
    except voz.SemVoz:
        return Resposta().diz("🎤 Ainda não entendo áudio: falta a chave de transcrição no servidor. "
                              "Mande por escrito.")
    except voz.FalhaVoz as erro:
        detalhe = f" Motivo: {erro}." if str(erro) else ""
        return Resposta().diz("🎤 Não consegui ouvir agora." + detalhe + " Mande por escrito ou tente mais tarde.")
    if not texto:
        return Resposta().diz("🎤 Não entendi o áudio. Pode repetir, ou mandar por escrito?")

    r = atender_texto(db, canal, origem, texto, rotulo, via_audio=True)
    eco = f"🎤 _“{texto}”_"
    if r.mensagens:
        r.mensagens[0]["texto"] = f"{eco}\n\n{r.mensagens[0]['texto']}"
    else:
        r.diz(eco)
    return r


# ══════════════════════════════════════════════════════════════════════
# A ENTRADA — toque (botão do Telegram ou número do WhatsApp)
# ══════════════════════════════════════════════════════════════════════
def atender_toque(db: Session, canal: str, origem: str, dados: str) -> Resposta:
    origem = str(origem)
    conta = conta_de(db, canal, origem)
    if not conta:
        return _boas_vindas()
    s = sessao_de(db, canal, origem)

    dono, _, resto = (dados or "").partition(":")
    if dono == "hub":
        if resto == "nada":
            return Resposta()
        if resto == "menu":
            _entrar_modo(db, s, None)
            return menu(db, conta)
        if resto.startswith("app|"):
            mod = modulos.por_chave(resto.split("|", 1)[1])
            if not mod:
                return Resposta(curta="Sistema desconhecido.")
            if not _vinculo(conta, mod.chave):
                return _nao_conectado(mod)
            _entrar_modo(db, s, mod.chave)
            pendente, s.pendente = s.pendente, None
            db.commit()
            r = (_com_intencao(db, conta, canal, origem, pendente, [mod], False, mod) if pendente
                 else para_sistema(db, conta, canal, origem, mod, texto="/ajuda"))
            r.curta = r.curta or f"{mod.emoji} {mod.nome}"
            return r
        return Resposta(curta="Opção desconhecida.")

    mod = modulos.por_chave(dono)
    if not mod:
        return Resposta(curta="Essa opção não vale mais.")
    _entrar_modo(db, s, mod.chave)
    return para_sistema(db, conta, canal, origem, mod, dados=resto)


# ══════════════════════════════════════════════════════════════════════
# A LISTA NUMERADA (WhatsApp)
# ══════════════════════════════════════════════════════════════════════
def guardar_escolhas(db: Session, canal: str, origem: str, itens: list):
    s = sessao_de(db, canal, origem)
    s.escolhas = json.dumps(itens, ensure_ascii=False) if itens else None
    s.escolhas_em = datetime.utcnow() if itens else None
    db.commit()


def _resgatar_escolha(db: Session, s: Sessao, numero: int) -> Optional[dict]:
    """Uso único e validade curta: um '2' meia hora depois responde a outra pergunta."""
    try:
        itens = json.loads(s.escolhas or "[]")
    except ValueError:
        itens = []
    velho = not s.escolhas_em or datetime.utcnow() - s.escolhas_em > timedelta(minutes=config.ESCOLHA_MINUTOS)
    s.escolhas, s.escolhas_em = None, None
    db.commit()
    if velho or not (1 <= numero <= len(itens)):
        return None
    return itens[numero - 1]


# ══════════════════════════════════════════════════════════════════════
# AVISOS (sistema → pessoa)
# ══════════════════════════════════════════════════════════════════════
def aviso(db: Session, mod: modulos.Modulo, usuario_id: str, texto: str, opcoes=None) -> list:
    """
    Devolve [(canal, origem, Resposta)] para cada canal com avisos ligados.
    Responder a um aviso cai no sistema dele: o modo já fica ativo.
    """
    v = db.query(VinculoSistema).filter(VinculoSistema.app == mod.chave,
                                        VinculoSistema.usuario_id == str(usuario_id)).first()
    if not v:
        return []
    conta = v.conta
    saida = []
    for c in conta.canais:
        if not c.avisos:
            continue
        s = sessao_de(db, c.canal, c.origem)
        _entrar_modo(db, s, mod.chave)
        r = Resposta().diz(f"{mod.selo}\n{texto}", render.prefixar(opcoes, mod.chave))
        saida.append((c.canal, c.origem, r))
    _registrar(db, conta, None, mod.chave, "aviso", "Aviso recebido")
    return saida
