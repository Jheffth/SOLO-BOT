"""Ponte explícita de memórias: somente Bella Legado ↔ seu ID permanente no Models."""
import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal, Conta, Configuracao, BellaArquivo, BellaLore, BellaMemoria, BellaTurno
from nucleo import models


def chave_vinculos(conta_id, modelo_id):
    return f'msync:{conta_id}:{modelo_id}'


def vinculos(db, conta_id, modelo_id):
    row = db.get(Configuracao, chave_vinculos(conta_id, modelo_id))
    return json.loads(row.valor) if row and row.valor else {}


def importar(conta_id, modelo_id, payload):
    """Transação única; os IDs de origem tornam repetição e ida/volta idempotentes."""
    if (payload.get('formato') != 1 or payload.get('modelo_id') != modelo_id
            or payload.get('dono_id') != f'solo-bot:conta:{conta_id}'):
        raise models.ErroModels('A identidade da cópia de memória foi recusada.')
    preparados = []
    ids = set()
    try:
        for r in payload['registros']:
            ident = r['id']
            from uuid import UUID
            if str(UUID(ident)) != ident or ident in ids:
                raise ValueError()
            ids.add(ident)
            tipo, d = r['tipo'], r['dados']
            instante = datetime.fromisoformat(r['criado_em'])
            if instante.tzinfo is None:
                instante = instante.replace(tzinfo=timezone.utc)
            criado = instante.astimezone(timezone.utc).replace(tzinfo=None)
            texto = d['texto']
            if not isinstance(texto, str) or not texto or len(texto) > 40000:
                raise ValueError()
            if tipo == 'lembranca':
                if len(texto) > 300: raise ValueError()
                classe = BellaMemoria
                valores = {'texto': texto}
            elif tipo in ('permanente', 'narrador'):
                classe = BellaLore
                titulo = d.get('titulo') or ('Narrador' if tipo == 'narrador' else 'Conversa permanente')
                if not isinstance(titulo, str) or len(titulo) > 120: raise ValueError()
                # O título completo continua no Models; o legado aceita 40 caracteres.
                nome = titulo if len(titulo) <= 40 else titulo[:31]+'-'+hashlib.sha256(titulo.encode()).hexdigest()[:8]
                valores = {'nome': nome, 'texto': ('[Narrador] ' if tipo == 'narrador' else '[Permanente] ')+texto}
            elif tipo == 'turno':
                classe = BellaArquivo
                if not isinstance(d.get('usuario'), str) or len(d['usuario']) > 20000: raise ValueError()
                valores = {'usuario': d['usuario'], 'bella': texto,
                           'dia': instante.astimezone(ZoneInfo('America/Sao_Paulo')).date().isoformat()}
            else:
                raise ValueError()
            preparados.append((ident, classe, valores, criado))
    except (KeyError, TypeError, ValueError):
        raise models.ErroModels('A cópia de memória está inválida; nenhuma lembrança foi alterada.') from None
    db = SessionLocal()
    novos = atualizados = 0
    try:
        conta = db.query(Conta).filter_by(id=conta_id).with_for_update().one()
        if not conta.admin: raise models.ErroModels('Sincronização disponível somente para o próprio Arquiteto.')
        mapa = vinculos(db, conta_id, modelo_id)
        for ident, classe, valores, criado in preparados:
            anterior = mapa.get(ident, {})
            row = db.query(classe).filter_by(id=anterior.get('id'), conta_id=conta_id).first() if anterior else None
            if not row:
                # Uma lembrança idêntica já gravada no legado não precisa de outra cópia.
                filtro = dict(valores)
                if classe == BellaArquivo: filtro['criado_em'] = criado
                row = db.query(classe).filter_by(conta_id=conta_id, **filtro).first()
            if row:
                if any(getattr(row, k) != v for k, v in valores.items()):
                    for k, v in valores.items(): setattr(row, k, v)
                    atualizados += 1
            else:
                row = classe(conta_id=conta_id, criado_em=criado, **valores)
                db.add(row); db.flush(); novos += 1
            mapa[ident] = {'tipo': classe.__tablename__, 'id': row.id}
            if classe == BellaLore: mapa[ident]['nome'] = valores['nome']
            if classe == BellaArquivo:
                for chave in (str(conta_id), *(f'{c}:{conta_id}' for c in ('whatsapp', 'telegram', 'bella', 'siri'))):
                    if not db.query(BellaTurno.id).filter_by(chave=chave, usuario=row.usuario,
                            bella=row.bella, criado_em=row.criado_em).first():
                        db.add(BellaTurno(chave=chave, usuario=row.usuario, bella=row.bella, criado_em=row.criado_em))
        chave = chave_vinculos(conta_id, modelo_id)
        cfg = db.get(Configuracao, chave) or Configuracao(chave=chave)
        cfg.valor = json.dumps(mapa, ensure_ascii=False); db.add(cfg); db.commit()
    except Exception:
        db.rollback(); raise
    finally:
        db.close()
    from nucleo import bella_conversa
    with bella_conversa._TRAVA:
        for chave in (conta_id, str(conta_id), *(f'{c}:{conta_id}' for c in ('whatsapp','telegram','bella','siri'))):
            bella_conversa._MEMORIA.pop(chave, None)
    return {'novos': novos, 'atualizados': atualizados, 'total': len(preparados)}


def sincronizar(conta):
    if not conta.admin: return 'Sincronização disponível somente para o próprio Arquiteto.'
    try:
        ativo = models.selecionado(conta.id)
        ident = models._requisicao('GET', '/api/servico/bella-legado')['modelo_id']
        if ativo and ativo != ident:
            return 'Esta modelo tem memórias próprias. A Bella Legado só sincroniza com o ID da Bella Models.'
        base = models._rota(conta, ident)
        if ativo:
            payload = models._requisicao('GET', base+'/memorias-legado', conta, ident)
            r = importar(conta.id, ident, payload)
            return f"Memórias sincronizadas: Bella Models → Bella Legado. {r['novos']} novas; {r['atualizados']} atualizadas. Sua conversa continua na Bella Models."
        r = models._requisicao('POST', base+'/sincronizar-memorias', conta, ident)
        return f"Memórias sincronizadas: Bella Legado → Bella Models. {r['total']} registros disponíveis. Sua conversa continua na Bella Legado."
    except models.ErroModels as e:
        return str(e)
    except SQLAlchemyError:
        return 'Não consegui gravar a sincronização agora. Tente novamente; sua escolha foi preservada.'
