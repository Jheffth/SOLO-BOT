# -*- coding: utf-8 -*-
"""
Os modelos do Solo Bot.

A Conta Solo é o hub. Tudo o mais pendura nela: os canais pelos quais a
pessoa fala e os sistemas a que ela se ligou.
"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Text, UniqueConstraint, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

import config

_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class Conta(Base):
    __tablename__ = "contas"

    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    usuario = Column(String(50), nullable=True, unique=True, index=True)   # o login do dia a dia
    email = Column(String(200), nullable=True, unique=True, index=True)    # opcional
    voz = Column(String(10), nullable=True)            # audio (padrão) | sempre | nunca — ver nucleo/fala.py
    avisos_silencio_de = Column(String(5), nullable=True)    # "22:00" — ver nucleo/avisos.py
    avisos_silencio_ate = Column(String(5), nullable=True)   # "07:00"
    avisos_voz = Column(String(10), nullable=True)           # sistema (padrão) | sempre | nunca
    senha_hash = Column(String(200), nullable=False)
    admin = Column(Boolean, default=False, nullable=False)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)
    ultimo_acesso = Column(DateTime, nullable=True)

    canais = relationship("CanalVinculo", back_populates="conta", cascade="all, delete-orphan")
    sistemas = relationship("VinculoSistema", back_populates="conta", cascade="all, delete-orphan")


class CanalVinculo(Base):
    """Um chat do Telegram ou um número de WhatsApp provado como desta conta."""
    __tablename__ = "canais"
    __table_args__ = (
        UniqueConstraint("canal", "origem", name="uq_canal_origem"),
        UniqueConstraint("conta_id", "canal", name="uq_conta_canal"),
    )

    id = Column(Integer, primary_key=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True)
    canal = Column(String(16), nullable=False)      # telegram | whatsapp
    origem = Column(String(80), nullable=False)     # chat_id | JID
    rotulo = Column(String(80), nullable=True)      # @usuario ou nome do contato
    avisos = Column(Boolean, default=True, nullable=False)
    vinculado_em = Column(DateTime, default=datetime.utcnow)

    conta = relationship("Conta", back_populates="canais")


class CodigoCanal(Base):
    """O token que vai no link t.me/…?start= ou na mensagem pronta do wa.me."""
    __tablename__ = "codigos_canal"

    id = Column(Integer, primary_key=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True)
    canal = Column(String(16), nullable=False)
    codigo = Column(String(64), nullable=False, unique=True, index=True)
    expira_em = Column(DateTime, nullable=False)
    usado_em = Column(DateTime, nullable=True)


class TentativaCanal(Base):
    """Limite de erros por origem. Mora no banco: o deploy não zera o castigo."""
    __tablename__ = "tentativas_canal"
    __table_args__ = (UniqueConstraint("canal", "origem", name="uq_tentativa"),)

    id = Column(Integer, primary_key=True)
    canal = Column(String(16), nullable=False)
    origem = Column(String(80), nullable=False)
    erros = Column(Integer, default=0, nullable=False)
    bloqueado_ate = Column(DateTime, nullable=True)


class VinculoSistema(Base):
    """Esta Conta Solo é o usuário `usuario_id` do sistema `app`."""
    __tablename__ = "vinculos_sistema"
    __table_args__ = (
        UniqueConstraint("conta_id", "app", name="uq_conta_app"),
        UniqueConstraint("app", "usuario_id", name="uq_app_usuario"),
    )

    id = Column(Integer, primary_key=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True)
    app = Column(String(16), nullable=False)
    usuario_id = Column(String(64), nullable=False)
    nome_remoto = Column(String(120), nullable=True)
    vinculado_em = Column(DateTime, default=datetime.utcnow)

    conta = relationship("Conta", back_populates="sistemas")


class Sessao(Base):
    """O estado da conversa: modo ativo, pergunta pendente, lista numerada."""
    __tablename__ = "sessoes"
    __table_args__ = (UniqueConstraint("canal", "origem", name="uq_sessao"),)

    id = Column(Integer, primary_key=True)
    canal = Column(String(16), nullable=False)
    origem = Column(String(80), nullable=False)
    modo = Column(String(16), nullable=True)
    modo_em = Column(DateTime, nullable=True)
    pendente = Column(Text, nullable=True)          # texto à espera de "para qual sistema?"
    escolhas = Column(Text, nullable=True)          # JSON da lista numerada (WhatsApp)
    escolhas_em = Column(DateTime, nullable=True)


class MensagemProcessada(Base):
    """Idempotência: Telegram e Evolution reentregam. Só um insert passa."""
    __tablename__ = "mensagens_processadas"
    __table_args__ = (UniqueConstraint("canal", "id_externo", name="uq_msg"),)

    id = Column(Integer, primary_key=True)
    canal = Column(String(16), nullable=False)
    id_externo = Column(String(120), nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Atividade(Base):
    """
    O painel mostra "o que passou pelo bot". Guarda o COMANDO, nunca o texto:
    mensagem sobre dinheiro não deve ficar em mais um lugar.
    """
    __tablename__ = "atividades"

    id = Column(Integer, primary_key=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True)
    canal = Column(String(16), nullable=True)
    app = Column(String(16), nullable=True)
    tipo = Column(String(24), nullable=False)       # comando | aviso | vinculo | canal
    resumo = Column(String(120), nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, index=True)


class ManifestoModulo(Base):
    """
    O que cada sistema declarou saber fazer pelo bot (o `bot_manifesto.json`
    dele). Uma linha por sistema: a versão atual é o que importa.
    """
    __tablename__ = "manifestos"

    app = Column(String(16), primary_key=True)
    versao = Column(String(40), nullable=False)
    dados = Column(Text, nullable=False)             # JSON validado
    recebido_em = Column(DateTime, default=datetime.utcnow)
    origem = Column(String(16), nullable=True)       # empurrado | buscado


class AvisoPendente(Base):
    """Aviso que chegou no horário de silêncio e espera para sair."""
    __tablename__ = "avisos_pendentes"

    id = Column(Integer, primary_key=True)
    conta_id = Column(Integer, ForeignKey("contas.id", ondelete="CASCADE"), nullable=False, index=True)
    canal = Column(String(16), nullable=False)
    origem = Column(String(80), nullable=False)
    app = Column(String(16), nullable=False)
    mensagens = Column(Text, nullable=False)          # JSON [{texto, opcoes, falado?}]
    voz = Column(Boolean, default=False, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Configuracao(Base):
    """Chave/valor do que se ajusta na tela de Administração (voz, modelo)."""
    __tablename__ = "configuracoes"

    chave = Column(String(60), primary_key=True)
    valor = Column(Text, nullable=True)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def ler_config(chave: str):
    db = SessionLocal()
    try:
        c = db.get(Configuracao, chave)
        return c.valor if c else None
    except Exception:  # noqa: BLE001 — tabela ainda não criada, banco fora: vale o padrão
        return None
    finally:
        db.close()


def gravar_config(db, chave: str, valor):
    c = db.get(Configuracao, chave) or Configuracao(chave=chave)
    c.valor = valor
    db.merge(c)
    db.commit()


def criar_tabelas():
    Base.metadata.create_all(bind=engine)
    _migrar()


def _migrar():
    """
    Ajustes em tabelas que JÁ existem — o create_all só cria o que falta, não
    altera. Idempotente: roda em todo startup e só age se precisar.

      · contas.usuario  — login por usuário (antes era só e-mail)
      · contas.email    — deixa de ser obrigatório
      · contas.voz      — preferência de resposta falada
      · contas.avisos_* — silêncio e voz dos avisos
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "contas" not in insp.get_table_names():
        return
    colunas = {c["name"]: c for c in insp.get_columns("contas")}
    with engine.begin() as con:
        if "usuario" not in colunas:
            con.execute(text("ALTER TABLE contas ADD COLUMN usuario VARCHAR(50)"))
            con.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_contas_usuario ON contas (usuario)"))
        for nome, tipo in (("voz", "VARCHAR(10)"), ("avisos_silencio_de", "VARCHAR(5)"),
                           ("avisos_silencio_ate", "VARCHAR(5)"), ("avisos_voz", "VARCHAR(10)")):
            if nome not in colunas:
                con.execute(text(f"ALTER TABLE contas ADD COLUMN {nome} {tipo}"))
        if engine.dialect.name == "postgresql" and not colunas.get("email", {}).get("nullable", True):
            con.execute(text("ALTER TABLE contas ALTER COLUMN email DROP NOT NULL"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
