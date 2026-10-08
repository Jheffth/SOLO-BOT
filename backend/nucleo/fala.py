# -*- coding: utf-8 -*-
"""
A FALA DO SOLO BOT — responder por voz, uma vez, para todos os sistemas.

O par da `nucleo/voz.py` (que OUVE). Aqui o Solo Bot FALA: pega a resposta
de qualquer sistema e, se a pessoa quiser, manda também em áudio, com a
voz da ElevenLabs. Nenhum sistema precisa saber sintetizar.

QUANDO FALA — preferência da Conta Solo (`contas.voz`, comando `/voz`):
  · "audio"  (padrão) responde falado quando a pessoa MANDOU áudio
  · "sempre" responde falado a tudo
  · "nunca"  só texto

O QUE FALA
  · o `falado` que o sistema mandar, se mandar (o Finances manda a versão
    pensada para ouvido: "quarenta e cinco reais", com direção de atuação);
  · senão, uma versão "falável" do texto: sem emoji, sem marcação, sem a
    lista numerada e sem o eco "🎤 …". Resposta longa demais (uma lista de
    missões, um extrato) NÃO é falada: lista é para ler, e crédito da
    ElevenLabs é por caractere.
"""
import base64
import logging
import re
from typing import Optional

import httpx

import config

log = logging.getLogger("solobot.fala")

API = "https://api.elevenlabs.io/v1"
MAX_CARACTERES = 500
FORMATOS = {"telegram": ("opus_48000_64", "audio/ogg"), "whatsapp": ("mp3_44100_64", "audio/mpeg")}
MODELO_RESERVA = "eleven_flash_v2_5"
PREFERENCIAS = ("audio", "sempre", "nunca")

_estado = {"voz": None, "ultimo_erro": None}


def disponivel() -> bool:
    return bool(contas())


def ultimo_erro() -> Optional[str]:
    return _estado["ultimo_erro"]


# ── O que falar ──────────────────────────────────────────────────
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]+")
_TAGS = re.compile(r"\[[^\]\n]{1,40}\]")
_SELO = re.compile(r"^\S{1,3}\s*\*[^*]{2,30}\*$")          # "💰 *Finances*" sozinho na linha


def _reais(m: re.Match) -> str:
    inteiro, cent = m.group(1).replace(".", ""), m.group(2)
    base = f"{int(inteiro)} {'real' if inteiro == '1' else 'reais'}"
    return base if not cent or cent == "00" else f"{base} e {int(cent)} centavos"


def texto_falavel(texto: str, limite: Optional[int] = MAX_CARACTERES) -> Optional[str]:
    linhas = []
    for linha in (texto or "").splitlines():
        l = linha.strip()
        if not l:
            continue
        if l.startswith(("🎤", "🧭")) or re.match(r"^\*?\d+\.\*?\s", l) or "Responda com o número" in l:
            continue                            # eco do áudio, nota de intenção e lista: são para ler
        if _SELO.match(l):
            continue                            # "⚔️ *Rotinas*": o selo é para os olhos
        l = _EMOJI.sub(" ", l)
        l = re.sub(r"[*_`~•▸]", " ", l).replace("→", " para ")
        l = re.sub(r"R\$\s*([\d.]+)(?:,(\d{2}))?", _reais, l)
        l = re.sub(r"\s+", " ", l).strip(" :-–—")
        if l:
            linhas.append(l)
    if not linhas:
        return None
    # Cada linha guarda a própria pontuação: "?" e "!" são entonação, não enfeite.
    falado = " ".join(x if x[-1] in ".!?…" else x + "." for x in linhas)
    return falado if limite is None or len(falado) <= limite else None


def expressivo(modelo: str) -> bool:
    return modelo.startswith(("eleven_v3", "eleven_v4"))


# ── A voz ────────────────────────────────────────────────────────
CHAVE_CONTA = "conta_elevenlabs"


def contas() -> list:
    """Cadastro do servidor. Nunca devolver as chaves na API do painel."""
    itens = [("principal", "Principal", config.ELEVENLABS_API_KEY),
             ("reserva", "Secundária", config.ELEVENLABS_API_KEY_SECONDARY)]
    itens += [(f"conta_{n}", f"Conta {n}", chave)
              for n, chave in sorted(config.ELEVENLABS_CONTAS_EXTRAS.items(), key=lambda par: int(par[0]))]
    return [{"id": id_, "nome": nome, "chave": chave} for id_, nome, chave in itens if chave]


def conta_escolhida() -> str:
    from database import ler_config
    return ler_config(CHAVE_CONTA) or "automatica"


def _chaves() -> list:
    escolhida = conta_escolhida()
    return list(dict.fromkeys(c["chave"] for c in contas()
                             if escolhida == "automatica" or c["id"] == escolhida))


MODELOS = [
    {"id": "eleven_flash_v2_5", "nome": "Rápido", "expressivo": False,
     "descricao": "Flash v2.5: resposta mais rápida e metade do crédito. Voz neutra."},
    {"id": "eleven_v4_turbo", "nome": "Expressivo", "expressivo": True,
     "descricao": "v4 Turbo: entende os jeitos de falar ([animado], [sussurrando]…) e continua rápido."},
    {"id": "eleven_v4", "nome": "Máximo", "expressivo": True,
     "descricao": "v4: a atuação mais rica; um pouco mais lento e mais caro."},
]
CHAVE_VOZ, CHAVE_MODELO = "voz_elevenlabs", "modelo_elevenlabs"
CHAVE_VOZ_SISTEMA = "voz_sistema_elevenlabs"

# ── Os TONS ──────────────────────────────────────────────────────
# Um aviso pode pedir um jeito de falar (`tom`). O tom decide a voz, a
# atuação e se o texto pode ser resumido. Tom desconhecido é ignorado:
# um sistema mais novo que o Solo Bot não quebra nada.
#
#   sussurro — a voz do Sistema quando cobra (os Ecos do Rotinas). Voz
#              própria (admin → "Voz do Sistema"), instável e dramática;
#              nos modelos expressivos, a fala vai marcada [whispers].
#              A frase é a arte: sai EXATAMENTE como veio, nunca resumida.
TONS = {
    "sussurro": {"etiqueta": "[whispers]",
                 "expressivo": {"stability": 0.0, "similarity_boost": 0.75, "style": 0.7},
                 "neutro": {"stability": 0.3, "similarity_boost": 0.75, "style": 0.6}},
}


def tom_valido(tom) -> Optional[str]:
    t = (tom or "").strip().lower() if isinstance(tom, str) else ""
    return t if t in TONS else None


def modelo() -> str:
    """ELEVENLABS_MODEL no .env fixa; senão o escolhido na tela; senão o Rápido."""
    from database import ler_config
    return config.ELEVENLABS_MODEL or ler_config(CHAVE_MODELO) or MODELO_RESERVA


def listar_vozes(chave: Optional[str] = None) -> list:
    """Vozes da conta escolhida, ou das contas em ordem no modo automático."""
    for chave in ([chave] if chave else _chaves()):
        try:
            with httpx.Client(timeout=15) as c:
                r = c.get(f"{API}/voices", headers={"xi-api-key": chave})
        except Exception:  # noqa: BLE001
            continue
        if r.status_code != 200:
            continue
        ordem = {"cloned": 0, "generated": 0, "premade": 1}
        vozes = [{"voice_id": v.get("voice_id"), "nome": v.get("name") or v.get("voice_id"),
                  "categoria": v.get("category"), "propria": v.get("category") in ("cloned", "generated"),
                  "biblioteca": v.get("category") == "professional", "preview_url": v.get("preview_url"),
                  "descricao": ", ".join(x for x in (v.get("labels") or {}).values() if isinstance(x, str))[:80]}
                 for v in (r.json().get("voices") or []) if v.get("voice_id")]
        vozes.sort(key=lambda v: (ordem.get(v["categoria"], 2), (v["nome"] or "").lower()))
        return vozes
    return []


def voz() -> Optional[str]:
    """ELEVENLABS_VOICE_ID fixa; senão a escolhida na tela; senão a 1ª da conta (própria antes de premade)."""
    from database import ler_config
    if config.ELEVENLABS_VOICE_ID:
        return config.ELEVENLABS_VOICE_ID
    escolhida = ler_config(CHAVE_VOZ)
    if escolhida:
        return escolhida
    chaves = tuple(_chaves())
    if _estado["voz"] and _estado.get("voz_chaves") == chaves:
        return _estado["voz"]
    vozes = [v for v in listar_vozes() if not v["biblioteca"]] or listar_vozes()
    _estado["voz"] = vozes[0]["voice_id"] if vozes else None
    _estado["voz_chaves"] = chaves
    return _estado["voz"]


def voz_do_sistema() -> dict:
    """A voz dos sussurros: a escolhida na tela; senão, a mesma voz do bot."""
    from database import ler_config
    escolhida = ler_config(CHAVE_VOZ_SISTEMA)
    return {"id": escolhida or voz(), "origem": "tela" if escolhida else "mesma"}


def voz_para(tom: Optional[str]) -> Optional[str]:
    return voz_do_sistema()["id"] if tom_valido(tom) else voz()


def creditos() -> list:
    """O saldo de caracteres de cada chave (GET /user/subscription; a chave precisa de "User: read")."""
    from datetime import datetime, timezone
    saida = []
    for conta in contas():
        chave = conta["chave"]
        item = {"rotulo": conta["id"], "nome": conta["nome"]}
        try:
            with httpx.Client(timeout=12) as c:
                r = c.get(f"{API}/user/subscription", headers={"xi-api-key": chave})
            if r.status_code in (401, 403):
                item["erro"] = 'A chave não pode ler os créditos: dê a ela a permissão "User → Read" na ElevenLabs.'
            elif r.status_code != 200:
                item["erro"] = f"A ElevenLabs respondeu HTTP {r.status_code}."
            else:
                d = r.json()
                usados, limite = int(d.get("character_count") or 0), int(d.get("character_limit") or 0)
                reset = d.get("next_character_count_reset_unix")
                item.update({"usados": usados, "limite": limite, "restantes": max(limite - usados, 0),
                             "plano": d.get("tier"),
                             "renova_em": datetime.fromtimestamp(int(reset), tz=timezone.utc).date().isoformat()
                             if reset else None})
        except Exception:  # noqa: BLE001
            item["erro"] = "Não consegui falar com a ElevenLabs agora."
        saida.append(item)
    return saida


def sintetizar(texto: str, canal: str, id_voz: Optional[str] = None,
               tom: Optional[str] = None) -> Optional[dict]:
    """{base64, mime} pronto para a entrega, ou None (sem chave, sem crédito, fora do ar)."""
    if not disponivel() or not texto:
        return None
    tom = tom_valido(tom)
    voz_explicita = id_voz
    id_voz = id_voz or voz_para(tom)
    formato, mime = FORMATOS.get(canal, FORMATOS["whatsapp"])
    modelo_id = modelo()

    def corpo(m: str) -> dict:
        exp = expressivo(m)
        dito = texto if exp else _TAGS.sub("", texto).strip()
        ajustes = {"stability": 0.4 if exp else 0.5, "similarity_boost": 0.8}
        if tom:
            t = TONS[tom]
            ajustes = dict(t["expressivo" if exp else "neutro"])
            if exp and t.get("etiqueta") and not dito.lstrip().startswith("["):
                dito = f"{t['etiqueta']} {dito}"
        return {"text": dito, "model_id": m, "language_code": "pt", "voice_settings": ajustes}

    chaves = _chaves()
    if not chaves:
        _estado["ultimo_erro"] = "A conta de voz escolhida não está configurada. Selecione outra conta ou Automática."
        return None
    for indice, chave in enumerate(chaves):
        voz_atual = id_voz
        if (indice or not voz_atual) and not voz_explicita and not config.ELEVENLABS_VOICE_ID:
            # Vozes clonadas pertencem à conta. A reserva pode ter outro catálogo.
            catalogo = listar_vozes(chave)
            if catalogo and not any(v["voice_id"] == voz_atual for v in catalogo):
                proprias = [v for v in catalogo if not v["biblioteca"]] or catalogo
                voz_atual = proprias[0]["voice_id"]
        if not voz_atual:
            _estado["ultimo_erro"] = "nenhuma voz disponível na conta da ElevenLabs"
            continue
        c_atual = corpo(modelo_id)
        for _ in range(3):
            try:
                with httpx.Client(timeout=40) as c:
                    r = c.post(f"{API}/text-to-speech/{voz_atual}?output_format={formato}",
                               json=c_atual, headers={"xi-api-key": chave})
            except Exception:  # noqa: BLE001
                _estado["ultimo_erro"] = "ElevenLabs fora do alcance"
                break
            if r.status_code == 200 and r.content:
                _estado["ultimo_erro"] = None
                return {"base64": base64.b64encode(r.content).decode("ascii"), "mime": mime}
            if r.status_code == 422 and "language_code" in c_atual:
                c_atual.pop("language_code")          # modelo que não aceita o parâmetro
                continue
            if r.status_code in (400, 402, 403, 404) and c_atual["model_id"] != MODELO_RESERVA:
                c_atual = corpo(MODELO_RESERVA)       # modelo recusado pelo plano: cai no Flash
                continue
            _estado["ultimo_erro"] = f"ElevenLabs respondeu HTTP {r.status_code}"
            break                                      # 401/429/402 no Flash: tenta a outra chave
    log.warning("Fala falhou: %s", _estado["ultimo_erro"])
    return None


# ── Decidir e anexar ─────────────────────────────────────────────
def quer_falar(preferencia: Optional[str], entrada_audio: bool) -> bool:
    p = preferencia if preferencia in PREFERENCIAS else "audio"
    return p == "sempre" or (p == "audio" and entrada_audio)


RESUMO = """Você é a voz de um assistente pessoal que fala com o usuário pelo celular.
Receba a RESPOSTA ESCRITA de um sistema (texto e, às vezes, itens com botões) e diga o essencial
em voz alta, em português do Brasil, como uma pessoa falaria.

Regras:
- No máximo 2 ou 3 frases curtas, até 300 caracteres.
- Tom natural e direto, na segunda pessoa ("você tem…"). Nada de "aqui está", nada de saudação longa.
- Lista longa: diga quantos são e cite no máximo 3 itens, os mais importantes (pendentes antes de concluídos).
- Sem emoji, sem markdown, sem ler comandos (/hoje), sem números de lista.
- NUNCA invente nada que não esteja na resposta. Se não houver o que falar, responda vazio."""


def _para_ia(mensagens: list) -> str:
    """O que a IA precisa ver: o texto e os itens das opções (é lá que moram as missões)."""
    blocos = []
    for m in mensagens:
        blocos.append(m.get("texto") or "")
        itens = []
        for g in m.get("opcoes") or []:
            titulo = (g.get("titulo") or "").strip()
            acoes = ", ".join(a.get("rotulo", "") for a in g.get("acoes") or [])
            if titulo or acoes:
                itens.append(f"- {titulo} ({acoes})" if titulo else f"- {acoes}")
        if itens:
            blocos.append("Itens com botões:\n" + "\n".join(itens))
    return "\n\n".join(b for b in blocos if b).strip()[:4000]


def resumir(mensagens: list) -> Optional[str]:
    """Um resumo falado, feito pela IA, para quando a resposta é longa ou só lista."""
    from nucleo import gemini
    base = _para_ia(mensagens)
    if not base:
        return None
    dito = gemini.gerar(RESUMO, base, max_tokens=200, temperatura=0.3)
    if not dito:
        return None
    dito = re.sub(r"[*_`#]", "", _EMOJI.sub("", dito)).strip()
    return dito[:MAX_CARACTERES] or None


def o_que_falar(mensagens: list) -> Optional[str]:
    """
    1. o `falado` que o sistema mandou (o Finances manda);
    2. o texto limpo, se for curto;
    3. senão, um resumo falado pela IA (listas, respostas longas, sistemas
       que não escrevem para o ouvido — o Rotinas).
    """
    feitos = [m.get("falado") for m in mensagens if m.get("falado")]
    if feitos:
        return " ".join(feitos)
    if any(tom_valido(m.get("tom")) for m in mensagens):      # frase com tom: literal, nunca resumida
        literal = " ".join(t for t in (texto_falavel(m.get("texto") or "", None) for m in mensagens) if t)
        return literal[:MAX_CARACTERES] or None
    limpos = [texto_falavel(m.get("texto") or "") for m in mensagens]
    tem_lista = any(m.get("opcoes") for m in mensagens)
    if all(limpos) and not tem_lista:
        falado = " ".join(limpos)
        if len(falado) <= MAX_CARACTERES:
            return falado
    return resumir(mensagens)


def falar_resposta(conta, canal: str, resposta, entrada_audio: bool, forcar: bool = False) -> None:
    """
    Anexa a voz à ÚLTIMA mensagem da resposta, se a pessoa quiser. Nunca
    levanta: a voz é um a mais, e a resposta escrita sai de qualquer jeito.
    """
    if conta is None or not resposta.mensagens or not disponivel():
        return
    # `forcar`: quem decidiu já foi outra regra (a voz dos avisos, em nucleo/avisos.py).
    if not forcar and not quer_falar(getattr(conta, "voz", None), entrada_audio):
        for m in resposta.mensagens:         # quem pediu "nunca" não recebe nem a voz de um sistema
            if getattr(conta, "voz", None) == "nunca":
                m.pop("audio", None)
        return
    if any(m.get("audio") for m in resposta.mensagens):
        return                                # o sistema já mandou a própria voz
    try:
        falado = o_que_falar(resposta.mensagens)
        tom = next((tom_valido(m.get("tom")) for m in resposta.mensagens if tom_valido(m.get("tom"))), None)
        if not falado:
            audio = None
        elif tom:
            audio = sintetizar(falado, canal, tom=tom)
        else:
            audio = sintetizar(falado, canal)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao preparar a fala")
        audio = None
    if audio:
        resposta.mensagens[-1]["audio"] = audio
