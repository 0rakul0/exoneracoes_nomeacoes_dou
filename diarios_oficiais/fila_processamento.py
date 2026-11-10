"""Fila SQLite persistente compartilhada entre download e processamento (Windows/CPU)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from diarios_oficiais.config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / ".cache" / "fila_diarios.sqlite3"


def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=60)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=60000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS edicoes (
            arquivo TEXT PRIMARY KEY,
            uf TEXT NOT NULL,
            codigo TEXT NOT NULL,
            data_publicacao TEXT NOT NULL,
            caderno TEXT NOT NULL,
            url TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendente',
            tentativas INTEGER NOT NULL DEFAULT 0,
            disponivel_em TEXT NOT NULL DEFAULT '1970-01-01T00:00:00',
            atualizado_em TEXT NOT NULL,
            erro TEXT NOT NULL DEFAULT ''
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS ix_fila_edicoes
        ON edicoes (estado, disponivel_em, data_publicacao)
    """)
    db.commit()
    return db


def registrar(uf: str, codigo: str, data: str, caderno: str, url: str,
              arquivo: Path) -> None:
    agora = datetime.now().isoformat(timespec="seconds")
    with conectar() as db:
        db.execute("""
            INSERT INTO edicoes
            (arquivo, uf, codigo, data_publicacao, caderno, url, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(arquivo) DO UPDATE SET
                uf=excluded.uf, codigo=excluded.codigo,
                data_publicacao=excluded.data_publicacao,
                caderno=excluded.caderno, url=excluded.url,
                atualizado_em=excluded.atualizado_em
        """, (str(arquivo.resolve()), uf, codigo, data, caderno, url, agora))


def proxima() -> dict | None:
    agora = datetime.now().isoformat(timespec="seconds")
    db = conectar()
    try:
        db.execute("BEGIN IMMEDIATE")
        linha = db.execute("""
            SELECT * FROM edicoes
            WHERE estado IN ('pendente', 'erro') AND disponivel_em <= ?
            ORDER BY data_publicacao DESC, tentativas ASC, arquivo
            LIMIT 1
        """, (agora,)).fetchone()
        if linha is None:
            db.commit()
            return None
        db.execute("""
            UPDATE edicoes SET estado='processando', atualizado_em=? WHERE arquivo=?
        """, (agora, linha["arquivo"]))
        db.commit()
        return dict(linha)
    finally:
        db.close()


def finalizar(arquivo: str) -> None:
    with conectar() as db:
        db.execute("""
            UPDATE edicoes SET estado='concluido', erro='', atualizado_em=?
            WHERE arquivo=?
        """, (datetime.now().isoformat(timespec="seconds"), arquivo))


def falhar(arquivo: str, erro: Exception) -> None:
    with conectar() as db:
        linha = db.execute("SELECT tentativas FROM edicoes WHERE arquivo=?",
                           (arquivo,)).fetchone()
        tentativas = (linha["tentativas"] if linha else 0) + 1
        # Backoff com teto de 6h evita repeticao imediata em portal ou OCR problematico.
        minutos = min(360, 5 * 2 ** min(tentativas - 1, 6))
        agora = datetime.now()
        db.execute("""
            UPDATE edicoes SET estado='erro', tentativas=?,
                disponivel_em=?, atualizado_em=?, erro=?
            WHERE arquivo=?
        """, (tentativas, (agora + timedelta(minutes=minutos)).isoformat(timespec="seconds"),
              agora.isoformat(timespec="seconds"), str(erro)[:3000], arquivo))


def recuperar_interrompidos() -> int:
    with conectar() as db:
        cursor = db.execute("""
            UPDATE edicoes SET estado='pendente', atualizado_em=?
            WHERE estado='processando'
        """, (datetime.now().isoformat(timespec="seconds"),))
        return cursor.rowcount
