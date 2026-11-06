"""Трекер привычек в стиле Way of Life: баллы, серии (streaks), статистика."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from . import db

log = logging.getLogger(__name__)

HABIT_TYPES = {
    "good": ("✅", "Хорошая привычка (+1 балл за выполнение)"),
    "bad": ("❌", "Плохая привычка (−1 балл за повторение)"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'good',     -- good | bad
    emoji TEXT DEFAULT '⭐',
    icon TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    archived INTEGER DEFAULT 0             -- 1 = удалён/в архиве
);

CREATE TABLE IF NOT EXISTS habit_marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    day TEXT NOT NULL,                      -- ГГГГ-ММ-ДД
    done INTEGER NOT NULL,                  -- 1 выполнено / 0 нет
    created_at TEXT NOT NULL,
    UNIQUE(habit_id, day)
);
"""


def init_habits_schema() -> None:
    from .db import IS_POSTGRES
    if IS_POSTGRES:
        statements = [
            "CREATE TABLE IF NOT EXISTS habits (id SERIAL PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'good', emoji TEXT DEFAULT '⭐', icon TEXT DEFAULT '', created_at TEXT NOT NULL, archived INTEGER DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS habit_marks (id SERIAL PRIMARY KEY, habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE, day TEXT NOT NULL, done INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(habit_id, day))",
        ]
        with db.db() as conn:
            for stmt in statements:
                conn.execute(stmt)
    else:
        with db.db() as conn:
            conn.executescript(SCHEMA)


# ---------- CRUD ----------

def add_habit(name: str, htype: str = "good", emoji: str = "⭐") -> int:
    htype = htype if htype in HABIT_TYPES else "good"
    return db.execute(
        "INSERT INTO habits(name, type, emoji, created_at) VALUES(?,?,?,?)",
        (name[:120], htype, emoji[:10], db.utcnow()),
    )


def delete_habit(habit_id: int) -> None:
    db.execute("DELETE FROM habit_marks WHERE habit_id = ?", (habit_id,))
    db.execute("UPDATE habits SET archived = 1 WHERE id = ?", (habit_id,))


def rename_habit(habit_id: int, name: str, emoji: str | None = None) -> None:
    if emoji:
        db.execute("UPDATE habits SET name = ?, emoji = ? WHERE id = ?", (name[:120], emoji[:10], habit_id))
    else:
        db.execute("UPDATE habits SET name = ? WHERE id = ?", (name[:120], habit_id))


def set_mark(habit_id: int, day: str, done: bool) -> None:
    """Отметка за день: 1 = выполнено (для good) / повторилось (для bad)."""
    db.execute(
        "INSERT INTO habit_marks(habit_id, day, done, created_at) VALUES(?,?,?,?) "
        "ON CONFLICT(habit_id, day) DO UPDATE SET done = excluded.done",
        (habit_id, day, 1 if done else 0, db.utcnow()),
    )


def toggle_mark(habit_id: int, day: str) -> bool:
    """Переключает отметку за день, возвращает новое значение."""
    row = db.query_one(
        "SELECT done FROM habit_marks WHERE habit_id = ? AND day = ?", (habit_id, day)
    )
    new_val = 0 if (row and row["done"]) else 1
    set_mark(habit_id, day, bool(new_val))
    return bool(new_val)


# ---------- Статистика ----------

def _marks_map(days: list[str]) -> dict[tuple[int, str], int]:
    if not days:
        return {}
    placeholders = ",".join("?" for _ in days)
    rows = db.query(
        f"SELECT habit_id, day, done FROM habit_marks WHERE day IN ({placeholders})",
        days,
    )
    return {(r["habit_id"], r["day"]): r["done"] for r in rows}


def _streak(habit_id: int, marks: dict, habit_type: str, today: date, lookback: int = 60) -> int:
    """Текущая серия: для good — дней подряд выполнено (с今天 до первого пропуска); для bad — дней подряд НЕ повторялось."""
    streak = 0
    for i in range(lookback):
        d = today - timedelta(days=i)
        day_str = d.isoformat()
        done = marks.get((habit_id, day_str), 0)
        if habit_type == "good":
            if done:
                streak += 1
            else:
                # Сегодня ещё не отмечено — не обрываем серию, просто останавливаемся
                if i == 0:
                    continue
                break
        else:
            if not done:
                streak += 1
            else:
                if i == 0:
                    continue
                break
    return streak


def habit_score(days: int = 30) -> int:
    """Баллы за период: good-выполнение +1, bad-повтор −1."""
    today = date.today()
    day_list = [(today - timedelta(days=i)).isoformat() for i in range(days)]
    marks = _marks_map(day_list)
    score = 0
    for (_, _), done in marks.items():
        # need habit type: fetch separately
        pass
    # Более эффективно: одним запросом
    rows = db.query(
        f"""SELECT h.type, SUM(CASE WHEN h.type='good' THEN hm.done ELSE -hm.done END) AS pts
            FROM habit_marks hm JOIN habits h ON h.id = hm.habit_id
            WHERE hm.day >= ? GROUP BY h.type""",
        (day_list[-1],),
    )
    for r in rows:
        if r["type"] == "good":
            score += r["pts"] or 0
        else:
            score += r["pts"] or 0
    return score


def get_dashboard(days: int = 7) -> dict:
    """Данные для виджета/вкладки: привычки + сетка отметок + статистика."""
    today = date.today()
    day_list = [(today - timedelta(days=i)).isoformat() for i in range(days)]
    day_list.reverse()  # старые -> новые слева направо
    marks = _marks_map(day_list)

    habits = db.query(
        "SELECT id, name, type, emoji FROM habits WHERE archived = 0 ORDER BY id"
    )
    result = []
    for h in habits:
        week = [
            {
                "day": d,
                "done": bool(marks.get((h["id"], d), 0)),
                "label": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.fromisoformat(d).weekday()],
            }
            for d in day_list
        ]
        streak = _streak(h["id"], marks, h["type"], today)
        # Всего выполнений за 30 дней
        since30 = (today - timedelta(days=30)).isoformat()
        total30 = db.query_one(
            "SELECT COUNT(*) AS n FROM habit_marks WHERE habit_id = ? AND day >= ? AND done = 1",
            (h["id"], since30),
        )["n"]
        result.append({
            **h,
            "week": week,
            "streak": streak,
            "total30": total30,
            "type_label": HABIT_TYPES[h["type"]][0],
        })

    return {
        "days": day_list,
        "habits": result,
        "score": habit_score(days=30),
    }


def weekly_stats() -> dict:
    """Для еженедельного отчёта."""
    today = date.today()
    week_ago = (today - timedelta(days=7)).isoformat()
    rows = db.query(
        """SELECT h.name, h.type, h.emoji,
                  SUM(hm.done) AS done_count
           FROM habit_marks hm JOIN habits h ON h.id = hm.habit_id
           WHERE hm.day >= ?
           GROUP BY h.id ORDER BY done_count DESC""",
        (week_ago,),
    )
    return {"habits": rows, "score": habit_score(days=7)}
