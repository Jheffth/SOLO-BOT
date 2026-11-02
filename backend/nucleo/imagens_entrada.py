"""Separa anexos esportivos de referências de prompts antes de guardar imagens."""
import base64
import re
from datetime import datetime, timezone
from nucleo import modulos, prompts_bella

# A Bella.exe anterior preenchia essa frase automaticamente em anexos sem texto.
# Tratá-la como automática permite reconhecer os prints também no executável antigo.
LEGENDAS_AUTOMATICAS = {'', 'analise esta imagem', 'analise esta imagem.',
                       'crie um prompt com essa referência', 'crie um prompt com essa referencia'}


def prompt_explicito(texto, chave):
    if re.match(r'^\s*/(?:rot\s+)?treino\b', texto or '', re.I):
        return False
    if re.search(r'\b(?:não|nao)\s+(?:(?:é|e|quero|crie|criar|gere|gerar)\s+)?(?:um\s+)?prompt\b', texto or '', re.I):
        return False
    if (texto or '').strip().lower() in LEGENDAS_AUTOMATICAS:
        return False
    return bool(re.search(r'\b(?:prompt(?:modelo|roupa|criativo)?|charactersheet|posehot)\b', texto or '', re.I)
                or prompts_bella.solicitacao(texto or '', chave) is not None)


def instante_envio(valor=None):
    if isinstance(valor, datetime) and valor.tzinfo is not None:
        return valor.astimezone(timezone.utc)
    try:
        if valor is not None:
            return datetime.fromtimestamp(float(valor), timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    return datetime.now(timezone.utc)


def tentar_treino(db, conta, canal, legenda, conteudo, mime, enviado_em=None):
    """Retorna resposta tratada ou None quando o Rotinas confirma que não é Strava."""
    from nucleo import roteador as R
    erro = prompts_bella.validar_referencia(mime, conteudo)
    if erro:
        return R.Resposta().diz(erro)
    chave = R._chave_bella(canal, conta)
    if prompt_explicito(legenda, chave):
        return None
    mod = modulos.por_chave('rot')
    if mod is None or not mod.token:
        return R.Resposta().diz('Não consigo identificar prints de treino enquanto o Rotinas não estiver configurado. '
                               'Para usar esta imagem como referência, envie com /prompt e seu pedido.')
    vinculo = next((v for v in getattr(conta, 'sistemas', []) if v.app == 'rot'), None)
    corpo = dict(usuario_id=str(vinculo.usuario_id) if vinculo else None, canal=canal,
                 origem=f'solo:{conta.id}:{canal}', imagem_base64=base64.b64encode(conteudo).decode('ascii'),
                 mime=mime, legenda=legenda or '', enviado_em=instante_envio(enviado_em).isoformat())
    try:
        dados = modulos.chamar(mod, 'imagem', corpo)
    except modulos.ErroModulo as erro:
        return R.Resposta().diz(f'⚠️ {erro} A imagem não foi usada como referência de prompt. '
                               'Se o objetivo for um prompt, envie com /prompt e o pedido.')
    if not isinstance(dados, dict) or not isinstance(dados.get('tratado'), bool):
        return R.Resposta().diz('O Rotinas precisa ser atualizado para reconhecer prints de treino. '
                               'A imagem não foi usada como referência de prompt. Para criar um prompt, use /prompt.')
    if dados['tratado'] is False:
        return None
    if vinculo and R._desvinculado_la(db, conta, mod, dados):
        return R._nao_conectado(mod)
    if dados.get('estado') in ('registrado', 'duplicado'):
        R._registrar(db, conta, canal, mod.chave, 'imagem', 'print de treino')
    return R._traduzir(mod, dados, R.Resposta())
