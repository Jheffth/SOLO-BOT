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
GROK_API_KEY = _env("GROK_API_KEY")
GROK_STT_MODEL = _env("GROK_STT_MODEL", "grok-voice-transcribe-2.0")

# ── Fala (responder por voz, para todos os sistemas) ─────────────
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_API_KEY_SECONDARY = _env("ELEVENLABS_API_KEY_SECONDARY")   # entra se a principal falhar
ELEVENLABS_VOICE_ID = _env("ELEVENLABS_VOICE_ID")   # se definido, FIXA a voz (a tela de Administração não troca)
ELEVENLABS_MODEL = _env("ELEVENLABS_MODEL")         # se definido, FIXA o modelo; vazio = escolhido na tela

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
