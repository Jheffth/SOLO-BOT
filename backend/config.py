# -*- coding: utf-8 -*-
"""
Configuração do Solo Bot — tudo vem do ambiente.

Nenhum segredo tem valor padrão. Um default no código é um segredo publicado.
"""
import json
import os


def _env(nome: str, padrao: str = "") -> str:
    return (os.getenv(nome) or padrao).strip()


AMBIENTE = _env("AMBIENTE", "production")
DEV = AMBIENTE in ("dev", "test")

DATABASE_URL = _env("DATABASE_URL", "sqlite:///./solo_bot.db")

SECRET_KEY = _env("SECRET_KEY")
if not SECRET_KEY:
    if DEV:
        SECRET_KEY = "dev-apenas-" + "x" * 32
    else:
        raise RuntimeError("SECRET_KEY vazia: o Solo Bot não assina sessão com chave improvisada.")

ALGORITHM = "HS256"
SESSAO_HORAS = int(_env("SESSAO_HORAS", "168"))  # 7 dias

URL_PUBLICA = _env("URL_PUBLICA", "http://localhost:8000").rstrip("/")
CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", URL_PUBLICA).split(",") if o.strip()]

# Quem vira administrador ao se cadastrar (lista separada por vírgula).
ADMIN_EMAILS = {e.strip().lower() for e in _env("ADMIN_EMAILS").split(",") if e.strip()}

# ── Telegram ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_USERNAME = _env("TELEGRAM_BOT_USERNAME").lstrip("@")
TELEGRAM_SECRET = _env("TELEGRAM_SECRET")

# ── WhatsApp (Evolution API) ──────────────────────────────────────
EVOLUTION_API_URL = _env("EVOLUTION_API_URL", "http://whatsapp:8080").rstrip("/")
EVOLUTION_API_KEY = _env("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE = _env("EVOLUTION_INSTANCE", "solo_rotinas")
EVOLUTION_WEBHOOK_SECRET = _env("EVOLUTION_WEBHOOK_SECRET")
WHATSAPP_NUMERO = _env("WHATSAPP_NUMERO")  # só dígitos, para o link wa.me

# ── Voz (transcrição de áudio para os sistemas que não entendem áudio) ──
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_API_KEY_RESERVA = _env("GEMINI_API_KEY_RESERVA")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_AUDIO_MODEL = _env("GEMINI_AUDIO_MODEL", GEMINI_MODEL)
# Outro modelo de áudio pode funcionar mesmo se o principal estiver sobrecarregado.
# "nenhum" desliga a alternativa; não troca o modelo da interpretação dos comandos.
GEMINI_AUDIO_MODEL_RESERVA = _env("GEMINI_AUDIO_MODEL_RESERVA", "gemini-3.1-flash-lite")
GROK_API_KEY = _env("GROK_API_KEY")
GROK_TEXT_MODEL = _env("GROK_TEXT_MODEL", "grok-4.7")
GROK_IMAGE_MODEL = _env("GROK_IMAGE_MODEL", "grok-imagine-image-2.0")
GROK_VISION_MODEL = _env("GROK_VISION_MODEL")        # lê imagens de referência; vazio = o modelo de texto
GROK_STT_MODEL = _env("GROK_STT_MODEL", "grok-voice-transcribe-2.0")
# Só para o mostrador de saldo da Administração: chave de GERENCIAMENTO (console.x.ai → Settings → Management Keys),
# diferente da GROK_API_KEY, e o ID do time. Vazias = o mostrador fica desligado.
XAI_MANAGEMENT_KEY = _env("XAI_MANAGEMENT_KEY")
XAI_TEAM_ID = _env("XAI_TEAM_ID")
# Libera conversa sexual explícita entre adultos no Modo Safada da Bella. Desligado por padrão.
BELLA_CONTEUDO_ADULTO = _env("BELLA_CONTEUDO_ADULTO").strip().lower() in ("1", "true", "sim", "yes")


def _inteiro(nome, padrao, minimo, maximo):
    try:
        valor = int(_env(nome) or padrao)
    except ValueError:
        valor = padrao
    return max(minimo, min(maximo, valor))


# Conversa pessoal da Bella: tamanho da resposta e memória curta (só em RAM, por conta).
BELLA_CONVERSA_MAX_CHARS = _inteiro("BELLA_CONVERSA_MAX_CHARS", 900, 200, 2000)
BELLA_MEMORIA_TURNOS = _inteiro("BELLA_MEMORIA_TURNOS", 6, 0, 20)      # 0 desliga a memória
BELLA_MEMORIA_MINUTOS = _inteiro("BELLA_MEMORIA_MINUTOS", 30, 1, 240)

# ── Fala (responder por voz, para todos os sistemas) ─────────────
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_API_KEY_SECONDARY = _env("ELEVENLABS_API_KEY_SECONDARY")   # entra se a principal falhar
# Contas adicionais: ELEVENLABS_API_KEY_3, ELEVENLABS_API_KEY_4, ...
ELEVENLABS_CONTAS_EXTRAS = {
    str(int(n.rsplit("_", 1)[1])): _env(n)
    for n in os.environ
    if n.startswith("ELEVENLABS_API_KEY_") and n.rsplit("_", 1)[1].isdigit()
    and int(n.rsplit("_", 1)[1]) >= 3 and _env(n)
}
ELEVENLABS_VOICE_ID = _env("ELEVENLABS_VOICE_ID")   # se definido, FIXA a voz (a tela de Administração não troca)
ELEVENLABS_MODEL = _env("ELEVENLABS_MODEL")         # se definido, FIXA o modelo; vazio = escolhido na tela
BIBLIOTECA_DIR = _env("BIBLIOTECA_DIR", "dados/biblioteca")  # controle de repetição dos prompts da Bella (volume)
BELLA_AUDIO_DIR = _env("BELLA_AUDIO_DIR", "dados/bella-audios")  # cache persistente das saudações e dos Ecos

# ── Sistemas conectados ───────────────────────────────────────────
#
# Cada sistema é UM bloco. Um sistema novo é um bloco novo aqui, nada mais.
#   SOLO_MODULOS='[{"chave":"fin","nome":"Solo Finances","emoji":"💰",
#                   "url":"http://solo_finances:8000","token":"...",
#                   "painel":"https://solofinances...","cor":"#34d399"}]'
#
# O `token` vale nos DOIS sentidos: o Solo Bot o manda ao sistema, e o
# sistema o manda de volta em /interno/enviar.
MODULOS_PADRAO = [
    {"chave": "fin", "nome": "Solo Finances", "emoji": "💰", "cor": "#34d399",
     "descricao": "Lançamentos, saldos e extratos pelo chat.",
     "url": "http://solo_finances:8000", "token": "", "painel": ""},
    {"chave": "rot", "nome": "Solo Rotinas", "emoji": "⚔️", "cor": "#a78bfa",
     "descricao": "Missões do dia, dungeons e avisos.",
     "url": "http://solo_routines:8000", "token": "", "painel": ""},
]


def _modulos() -> list:
    bruto = _env("SOLO_MODULOS")
    if not bruto:
        return MODULOS_PADRAO
    try:
        dados = json.loads(bruto)
        assert isinstance(dados, list)
        return dados
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"SOLO_MODULOS não é uma lista JSON válida: {e}")


MODULOS = _modulos()

FUSO = _env("FUSO", "America/Sao_Paulo")   # para o horário de silêncio dos avisos

MODO_MINUTOS = 30          # modo ativo expira
# Quem não tem Conta Solo: o bot fica MUDO (padrão). Só responde a quem manda um
# código de vínculo (/start CODIGO no Telegram, SOLO 123456 no WhatsApp).
# RESPONDER_DESCONHECIDOS=1 volta a mandar a mensagem de boas-vindas.
RESPONDER_DESCONHECIDOS = _env("RESPONDER_DESCONHECIDOS", "0").strip().lower() in ("1", "true", "sim", "yes")
ESCOLHA_MINUTOS = 10       # lista numerada do WhatsApp expira
CODIGO_MINUTOS = 10        # tokens de canal
TENTATIVAS_MAX = 5         # erros por origem antes do castigo
CASTIGO_MINUTOS = 15
MANIFESTO_MINUTOS = int(_env("MANIFESTO_MINUTOS", "0" if AMBIENTE == "test" else "10"))  # 0 = não busca

# Motor secundario: vazio desativa, ElevenLabs continua sempre em primeiro lugar.
VOICESTUDIO_URL = _env("VOICESTUDIO_URL")
VOICESTUDIO_API_KEY = _env("VOICESTUDIO_API_KEY")
VOICESTUDIO_VOICE_ID = _env("VOICESTUDIO_VOICE_ID")
VOICESTUDIO_MODEL = _env("VOICESTUDIO_MODEL", "omnivoice")
VOICESTUDIO_TIMEOUT = _inteiro("VOICESTUDIO_TIMEOUT", 35, 5, 300)
# Mesmo padrao interativo do VoiceStudio; 32 prioriza qualidade sobre latencia.
VOICESTUDIO_STEPS = _inteiro("VOICESTUDIO_STEPS", 5, 1, 128)
