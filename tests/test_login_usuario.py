"""Login por usuário (o e-mail é opcional)."""
import sqlite3

import database
from database import Conta, SessionLocal
from seguranca import hash_senha


def test_cadastro_so_com_usuario_e_login_sem_diferenciar_maiusculas(cliente):
    r = cliente.post("/api/auth/cadastro", json={"nome": "Jefferson", "usuario": "Jh3ffth", "senha": "senha-forte-1"})
    assert r.status_code == 200 and r.json()["usuario"] == "Jh3ffth" and r.json()["email"] is None
    cliente.post("/api/auth/sair"); cliente.cookies.clear()
    assert cliente.post("/api/auth/entrar", json={"login": "jh3ffth", "senha": "senha-forte-1"}).status_code == 200
    assert cliente.get("/api/auth/eu").json()["identificacao"] == "Jh3ffth"


def test_login_por_email_continua_valendo(cliente):
    cliente.post("/api/auth/cadastro", json={"nome": "Ana", "usuario": "ana", "email": "ana@solo.dev", "senha": "12345678"})
    cliente.post("/api/auth/sair"); cliente.cookies.clear()
    assert cliente.post("/api/auth/entrar", json={"login": "ANA@solo.dev", "senha": "12345678"}).status_code == 200
    cliente.cookies.clear()
    assert cliente.post("/api/auth/entrar", json={"email": "ana@solo.dev", "senha": "12345678"}).status_code == 200


def test_usuario_repetido_e_invalido(cliente):
    cliente.post("/api/auth/cadastro", json={"nome": "Ana", "usuario": "ana", "senha": "12345678"})
    cliente.cookies.clear()
    assert cliente.post("/api/auth/cadastro", json={"nome": "Outra", "usuario": "ANA", "senha": "12345678"}).status_code == 409
    assert cliente.post("/api/auth/cadastro", json={"nome": "X", "usuario": "com espaço", "senha": "12345678"}).status_code == 422


def test_senha_errada_nao_diz_se_o_usuario_existe(cliente):
    cliente.post("/api/auth/cadastro", json={"nome": "Ana", "usuario": "ana", "senha": "12345678"})
    cliente.cookies.clear()
    a = cliente.post("/api/auth/entrar", json={"login": "ana", "senha": "errada00"})
    b = cliente.post("/api/auth/entrar", json={"login": "ninguem", "senha": "errada00"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_conta_antiga_com_usuario_no_campo_email_entra(cliente):
    """Conta criada por script, antes da coluna `usuario`: o nome estava no e-mail."""
    db = SessionLocal()
    db.add(Conta(nome="Jefferson", email="Jh3ffth", senha_hash=hash_senha("senha-forte-1"), admin=True))
    db.commit(); db.close()
    assert cliente.post("/api/auth/entrar", json={"login": "jh3ffth", "senha": "senha-forte-1"}).status_code == 200


def test_migracao_acrescenta_usuario_em_tabela_antiga(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect
    arq = tmp_path / "antigo.db"
    con = sqlite3.connect(arq)
    con.execute("CREATE TABLE contas (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL, "
                "email VARCHAR(200) NOT NULL UNIQUE, senha_hash VARCHAR(200) NOT NULL, admin BOOLEAN, "
                "ativo BOOLEAN, criado_em DATETIME, ultimo_acesso DATETIME)")
    con.commit(); con.close()
    monkeypatch.setattr(database, "engine", create_engine(f"sqlite:///{arq}"))
    database._migrar()
    database._migrar()                                   # idempotente
    assert "usuario" in {c["name"] for c in inspect(database.engine).get_columns("contas")}
