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
    email = Column(String(200), nullable=False, unique=True, index=True)
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


def criar_tabelas():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
