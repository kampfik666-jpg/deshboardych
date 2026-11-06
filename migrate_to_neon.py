# -*- coding: utf-8 -*-
"""Миграция данных из локальной SQLite в Neon Postgres.

Запуск:  DATABASE_URL=postgresql://... python migrate_to_neon.py
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# DATABASE_URL должен быть задан ДО импорта app.db
if not os.environ.get("DATABASE_URL"):
    print("❌ Установите DATABASE_URL, например:")
    print("   DATABASE_URL=postgresql://user:pass@host/db python migrate_to_neon.py")
    sys.exit(1)

from app import db

SQLITE_PATH = Path(__file__).resolve().parent / "data" / "lifehub.sqlite3"
if not SQLITE_PATH.exists():
    print(f"❌ Локальная база не найдена: {SQLITE_PATH}")
    sys.exit(1)

# 1. Сброс Neon-схемы (чистый старт)
print("🗑️ Очищаю Neon-таблицы…")
conn = db.connect()
try:
    for t in ["habit_marks", "habits", "expenses", "mail_filters", "sync_log",
              "briefings", "mails", "events", "obligations", "doc_chunks",
              "documents", "tasks", "settings"]:
        conn.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    conn.commit()
finally:
    conn.close()
print("✅ Таблицы удалены")

# 2. Создаём схему заново
db.init_db()
print("✅ Схема создана")

src = sqlite3.connect(str(SQLITE_PATH))
src.row_factory = sqlite3.Row
conn = src

def rows(table):
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
    except sqlite3.Error as e:
        print(f"  ⚠️ {table}: {e}")
        return []

def copy(table, cols, transform=None):
    data = rows(table)
    if not data:
        print(f"  {table}: пусто")
        return 0
    n = 0
    for row in data:
        vals = [row[c] for c in cols] if transform is None else transform(row)
        # Neon/Postgres не принимает NUL (0x00) в текстовых полях
        vals = [v.replace("\x00", "") if isinstance(v, str) else v for v in vals]
        placeholders = ",".join("?" for _ in cols)
        try:
            db.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})", vals)
            n += 1
        except Exception as exc:
            print(f"  ⚠️ {table} id={row.get('id')}: {exc}")
    print(f"  ✅ {table}: {n}/{len(data)}")
    return n

print("\n=== Миграция данных из SQLite в Neon ===")
copy("documents", ["id", "title", "filename", "mime", "size", "sha256", "source", "char_count", "file_data", "created_at"])
copy("doc_chunks", ["id", "doc_id", "idx", "text"])
copy("obligations", ["id", "doc_id", "title", "category", "amount", "currency", "kind", "due_date", "day_of_month", "month_of_year", "note", "status", "created_at"])
copy("tasks", ["id", "title", "category", "due_date", "due_time", "status", "source", "created_at", "completed_at"])
copy("events", ["id", "source", "cal_name", "uid", "title", "start_at", "end_at", "all_day", "location", "description", "fetched_at"],
     transform=lambda r: [r["id"], r["source"], r["cal_name"], r["uid"], r["title"], r["start_at"], r["end_at"], r["all_day"], r["location"], r["description"], r["fetched_at"]])
copy("mails", ["id", "source", "folder", "message_id", "subject", "sender", "date", "snippet", "unread", "fetched_at"])
copy("briefings", ["id", "day", "text", "sent", "created_at"])
copy("sync_log", ["id", "source", "kind", "ok", "detail", "created_at"])
copy("settings", ["key", "value"])
copy("mail_filters", ["id", "kind", "pattern", "action", "label", "created_at"])
copy("habits", ["id", "name", "type", "emoji", "icon", "created_at", "archived"])
copy("habit_marks", ["id", "habit_id", "day", "done", "created_at"])
copy("expenses", ["id", "date", "amount", "category", "description", "source", "created_at"])

# FTS (Neon — без FTS5, индекс не нужен; поиск работает через LIKE)
print("\n✅ Миграция завершена.")
print("   Проверь: SELECT COUNT(*) FROM tasks; и т.д.")
src.close()
