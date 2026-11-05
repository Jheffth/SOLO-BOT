"""Retrato do modelo selecionado no desktop, sem conversas nem memórias."""
from nucleo import models, models_galeria


def consultar(conta, foto_atual=''):
    ident = models.selecionado(conta.id)
    if not ident:
        return {'origem': 'legado', 'modelo_id': None, 'nome': 'Bella',
                'foto_id': 'legado', 'foto': None, 'inalterada': False}
    perfil = models.pacote(conta, ident)
    capa = (perfil.get('galeria') or {}).get('capa')
    # Confere a posse e o nível antes de usar o download de mídia por serviço.
    fotos = models_galeria.catalogo(conta, {**perfil, 'id': ident}, 'imagem') if capa else []
    capa = next((v['id'] for v in fotos if v['id'] == capa), None)
    assinatura = ident + ':' + (capa or '')
    resultado = {'origem': 'models', 'modelo_id': ident, 'nome': perfil['nome'],
                 'foto_id': assinatura, 'foto': None, 'inalterada': assinatura == foto_atual}
    if capa and not resultado['inalterada']:
        midia = models_galeria.baixar(capa, 'imagem', miniatura=True)
        resultado['foto'] = 'data:' + midia['mime'] + ';base64,' + midia['base64']
    if models.selecionado(conta.id) != ident:
        raise models.ErroModels('Sua seleção mudou durante a consulta. Atualize o perfil novamente.')
    return resultado
