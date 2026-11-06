"""Импорт задач из старого personal-notes-bot (notes.sqlite3).

Запуск:  py -m app.importer "путь/до/notes.sqlite3"
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from . import db

DEFAULT_OLD_DB = Path(__file__).resolve().parent.parent.parent / "personal-notes-bot" / "data" / "notes.sqlite3"


def import_tasks(old_db_path: str | Path) -> dict:
    old_db_path = Path(old_db_path)
    if not old_db_path.exists():
        return {"error": f"Файл не найден: {old_db_path}"}
    db.init_db()
    src = sqlite3.connect(old_db_path)
    src.row_factory = sqlite3.Row
    imported = {"tasks": 0, "shopping": 0, "skipped": 0}
    try:
        existing = {
            r["title"]
            for r in db.query("SELECT title FROM tasks")
        }
        for row in src.execute(
            "SELECT title, category, due_date, due_time, status, created_at, completed_at "
            "FROM tasks"
        ):
            title = row["title"].strip()
            if not title or title in existing:
                imported["skipped"] += 1
                continue
            db.execute(
                "INSERT INTO tasks(title, category, due_date, due_time, status, source, "
                "created_at, completed_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    title,
                    row["category"] or "inbox",
                    row["due_date"],
                    row["due_time"],
                    "done" if row["status"] == "done" else "open",
                    "notes-bot",
                    row["created_at"] or db.utcnow(),
                    row["completed_at"],
                ),
            )
            existing.add(title)
            imported["tasks"] += 1
        # Список покупок — как задачи категории shopping
        try:
            for row in src.execute(
                "SELECT title, category, status, created_at, completed_at FROM shopping"
            ):
                title = ("Купить: " + row["title"].strip()).strip()
                if not title or title in existing:
                    imported["skipped"] += 1
                    continue
                db.execute(
                    "INSERT INTO tasks(title, category, status, source, created_at, completed_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (
                        title,
                        "shopping",
                        "done" if row["status"] == "bought" else "open",
                        "notes-bot",
                        row["created_at"] or db.utcnow(),
                        row["completed_at"],
                    ),
                )
                existing.add(title)
                imported["shopping"] += 1
        except sqlite3.OperationalError:
            pass  # таблицы shopping может не быть
    finally:
        src.close()
    return imported


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OLD_DB
    result = import_tasks(path)
    print(result)
