"""Двухрежимное хранилище Life Hub: SQLite локально, PostgreSQL (Neon) на сервере.

Диалект определяется по переменной DATABASE_URL:
- если задана → PostgreSQL (psycopg3)
- иначе → локальный SQLite (как раньше)
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import settings

IS_POSTGRES: bool = bool(settings.database_url)

_FTS_AVAILABLE: bool | None = None

import threading

_DB_LOCK = threading.Lock()  # один psycopg-коннект одновременно (поток/асинк)

# Базовая схема (SQLite-вариант). Для Postgres — автоподстановка SERIAL вместо AUTOINCREMENT.
_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime TEXT,
    size INTEGER DEFAULT 0,
    sha256 TEXT,
    source TEXT NOT NULL DEFAULT 'upload',
    char_count INTEGER DEFAULT 0,
    file_data BLOB,           -- оригинальный файл (для сохранения после рестарта на сервере)
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS doc_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON doc_chunks(doc_id);

CREATE TABLE IF NOT EXISTS obligations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    category TEXT DEFAULT 'прочее',
    amount REAL,
    currency TEXT DEFAULT 'RUB',
    kind TEXT NOT NULL DEFAULT 'once',
    due_date TEXT,
    day_of_month INTEGER,
    month_of_year INTEGER,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'inbox',
    due_date TEXT,
    due_time TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    source TEXT NOT NULL DEFAULT 'lifehub',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    cal_name TEXT,
    uid TEXT NOT NULL,
    title TEXT,
    start_at TEXT NOT NULL,
    end_at TEXT,
    all_day INTEGER DEFAULT 0,
    location TEXT,
    description TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(source, uid, start_at)
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_at);

CREATE TABLE IF NOT EXISTS mails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    folder TEXT DEFAULT 'INBOX',
    message_id TEXT NOT NULL,
    subject TEXT,
    sender TEXT,
    date TEXT,
    snippet TEXT,
    unread INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL,
    UNIQUE(source, message_id)
);
CREATE INDEX IF NOT EXISTS idx_mails_date ON mails(date DESC);

CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    text TEXT NOT NULL,
    sent INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    ok INTEGER NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS mail_filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'sender',
    pattern TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'hide',
    label TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""

# Postgres-версия: AUTOINCREMENT → SERIAL, PRAGMA убирается
_PG_SCHEMA = _SQLITE_SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY").replace("file_data BLOB", "file_data BYTEA")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _translate(sql: str) -> str:
    """Конвертирует '?' → '%s' для Postgres."""
    if not IS_POSTGRES:
        return sql
    return sql.replace("?", "%s")


_PG_CONN = None
_PG_LOCK = None


def connect():
    """Подключение к БД. Для Postgres соединение кэшируется и переиспользуется
    (новое соединение ~1,3 сек, переиспользованное — мгновенно)."""
    global _PG_CONN, _PG_LOCK
    if IS_POSTGRES:
        import threading

        if _PG_LOCK is None:
            _PG_LOCK = threading.Lock()
        with _PG_LOCK:
            if _PG_CONN is not None:
                try:
                    _PG_CONN.execute("SELECT 1").fetchone()
                    return _PG_CONN
                except Exception:
                    try:
                        _PG_CONN.close()
                    except Exception:
                        pass
                    _PG_CONN = None
            import psycopg
            from psycopg.rows import dict_row

            _PG_CONN = psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=10)
            return _PG_CONN
    path: Path = settings.abs_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def db():
    with _DB_LOCK:
        conn = connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            if not IS_POSTGRES:
                conn.close()


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with db() as conn:
        cur = conn.execute(_translate(sql), tuple(params))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Выполняет SQL. Для INSERT в Postgres — возвращает сгенерированный id (RETURNING)."""
    stripped = sql.strip().rstrip(";").strip()
    is_insert = stripped.upper().startswith("INSERT")

    if IS_POSTGRES and is_insert and not stripped.upper().endswith("RETURNING ID"):
        try:
            with db() as conn:
                cur = conn.execute(_translate(stripped + " RETURNING id"), tuple(params))
                row = cur.fetchone()
                if row:
                    return row["id"] if isinstance(row, dict) else row[0]
                return cur.rowcount
        except Exception as exc:
            # Таблица может не иметь колонки id (например settings) — повторяем без RETURNING
            if "RETURNING" in str(exc) or "column" in str(exc).lower():
                with db() as conn:
                    cur = conn.execute(_translate(stripped), tuple(params))
                    return cur.rowcount
            raise

    with db() as conn:
        cur = conn.execute(_translate(sql), tuple(params))
        if IS_POSTGRES and is_insert:
            row = cur.fetchone()
            if row:
                return row["id"] if isinstance(row, dict) else row[0]
        return cur.rowcount


def fts_available() -> bool:
    """FTS5 поддерживается только в SQLite."""
    global _FTS_AVAILABLE
    if IS_POSTGRES:
        return False
    if _FTS_AVAILABLE is None:
        try:
            with db() as conn:
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
                conn.execute("DROP TABLE IF EXISTS _fts_probe")
            _FTS_AVAILABLE = True
        except sqlite3.Error:
            _FTS_AVAILABLE = False
    return _FTS_AVAILABLE


def init_db() -> None:
    schema = _PG_SCHEMA if IS_POSTGRES else _SQLITE_SCHEMA
    if IS_POSTGRES:
        # Postgres не поддерживает executescript — выполняем по ;
        with db() as conn:
            for stmt in schema.split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
    else:
        with db() as conn:
            conn.executescript(schema)
        # SQLite: мигрируем старое имя колонки start -> start_at
        with db() as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
            if "start" in cols and "start_at" not in cols:
                conn.execute("ALTER TABLE events RENAME COLUMN start TO start_at")
            elif "start" in cols and "start_at" in cols:
                pass
            if "end" in cols and "end_at" not in cols:
                conn.execute("ALTER TABLE events RENAME COLUMN end TO end_at")
            # SQLite: мигрируем documents — добавляем file_data если нет
            doc_cols = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
            if "file_data" not in doc_cols:
                conn.execute("ALTER TABLE documents ADD COLUMN file_data BLOB")
    if fts_available():
        with db() as conn:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5(chunk_id, doc_id, text)"
            )
    # Таблицы финансов и привычек
    from .finance import init_finance_schema
    init_finance_schema()
    from .habits import init_habits_schema
    init_habits_schema()


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def owner_ids() -> list[int]:
    """ID владельцев: из .env + автоматически запомненные в базе."""
    ids = list(settings.chat_ids)
    stored = get_setting("telegram_owner_ids", "")
    for part in stored.split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in ids:
            ids.append(int(part))
    return ids


def add_owner(user_id: int) -> None:
    """Запоминает первого написавшего пользователя как владельца (режим настройки)."""
    ids = owner_ids()
    if user_id not in ids:
        ids.append(user_id)
    set_setting("telegram_owner_ids", ",".join(str(i) for i in ids))