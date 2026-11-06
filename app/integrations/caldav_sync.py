"""Синхронизация календарей по CalDAV (Яндекс 360, Google Calendar).

Все функции синхронные — вызываются из async-кода через asyncio.to_thread.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from .. import db

log = logging.getLogger(__name__)


def _to_local_iso(dt_value) -> tuple[str, bool]:
    """Превращает date/datetime из vobject в (ISO-строка, all_day)."""
    if isinstance(dt_value, datetime):
        if dt_value.tzinfo is None:
            return dt_value.isoformat(timespec="minutes"), False
        return dt_value.astimezone().isoformat(timespec="minutes"), False
    if isinstance(dt_value, date):
        return dt_value.isoformat(), True
    return str(dt_value), False


def _vevent_prop(vevent, name: str):
    prop = getattr(vevent, name, None)
    if prop is None:
        return None
    try:
        return prop.value
    except Exception:  # noqa: BLE001
        return None


def fetch_source_events(
    source: str,
    caldav_url: str,
    username: str,
    password: str,
    days_back: int = 7,
    days_forward: int = 60,
) -> tuple[int, str | None]:
    """Тянет события одного источника в кэш events. Возвращает (число событий, ошибка)."""
    import caldav

    try:
        client = caldav.DAVClient(url=caldav_url, username=username, password=password)
        principal = client.principal()
        calendars = principal.calendars()
    except Exception as exc:  # noqa: BLE001
        log.warning("CalDAV %s connection failed: %s", source, exc)
        return 0, f"{type(exc).__name__}: {exc}"

    start = datetime.now(timezone.utc) - timedelta(days=days_back)
    end = datetime.now(timezone.utc) + timedelta(days=days_forward)
    collected: list[dict] = []
    for cal in calendars:
        cal_name = getattr(cal, "name", "") or ""
        if not cal_name:
            try:
                cal_name = cal.get_property("{DAV:}displayname") or ""
            except Exception:  # noqa: BLE001
                cal_name = ""
        try:
            events = cal.date_search(start=start, end=end, expand=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("CalDAV %s calendar %s search failed: %s", source, cal_name, exc)
            continue
        for ev in events:
            try:
                vevent = ev.vobject_instance.vevent
            except Exception:  # noqa: BLE001
                continue
            dtstart = _vevent_prop(vevent, "dtstart")
            if dtstart is None:
                continue
            start_iso, all_day = _to_local_iso(dtstart)
            dtend = _vevent_prop(vevent, "dtend")
            end_iso = _to_local_iso(dtend)[0] if dtend is not None else None
            uid = str(_vevent_prop(vevent, "uid") or ev.id or "")[:300]
            summary = _vevent_prop(vevent, "summary")
            location = _vevent_prop(vevent, "location")
            description = _vevent_prop(vevent, "description")
            collected.append(
                {
                    "source": source,
                    "cal_name": str(cal_name)[:100],
                    "uid": uid or f"{start_iso}-{summary}",
                    "title": str(summary or "(без названия)")[:300],
                    "start_at": start_iso,
                    "end_at": end_iso,
                    "all_day": 1 if all_day else 0,
                    "location": str(location)[:200] if location else None,
                    "description": str(description)[:1000] if description else None,
                }
            )

    # Перезаписываем кэш источника
    now = db.utcnow()
    with db.db() as conn:
        conn.execute(
            "DELETE FROM events WHERE source = ? AND start_at >= ? AND start_at < ?",
            (source, start.isoformat(), end.isoformat()),
        )
        for item in collected:
            conn.execute(
                "INSERT INTO events(source, cal_name, uid, title, start_at, end_at, "
                "all_day, location, description, fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source, uid, start_at) DO UPDATE SET "
                "cal_name=excluded.cal_name, title=excluded.title, end_at=excluded.end_at, "
                "all_day=excluded.all_day, location=excluded.location, "
                "description=excluded.description, fetched_at=excluded.fetched_at",
                (
                    item["source"], item["cal_name"], item["uid"], item["title"],
                    item["start_at"], item.get("end_at"), item["all_day"], item["location"],
                    item["description"], now,
                ),
            )
    return len(collected), None


def upcoming_events(days: int = 14) -> list[dict]:
    """События на N дней вперёд из кэша, отсортированные по времени."""
    now = datetime.now().astimezone()
    until = now + timedelta(days=days)
    rows = db.query(
        "SELECT * FROM events WHERE start_at >= ? AND start_at < ? ORDER BY start_at",
        (now.isoformat(timespec="minutes"), until.isoformat(timespec="minutes")),
    )
    # События на весь день храним как 'ГГГГ-ММ-ДД' — сравнение строк с ISO их отсекает.
    # Поэтому тянем ещё и короткие даты отдельно:
    today_str = now.date().isoformat()
    until_str = until.date().isoformat()
    allday = db.query(
        "SELECT * FROM events WHERE all_day = 1 AND length(start_at) = 10 "
        "AND start_at >= ? AND start_at <= ? ORDER BY start_at",
        (today_str, until_str),
    )
    seen = set()
    merged = []
    for row in rows + allday:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        merged.append(row)
    merged.sort(key=lambda r: (r["start_at"], r["all_day"]))
    return merged


def events_for_day(day: date) -> list[dict]:
    """События конкретного дня (day — date)."""
    day_str = day.isoformat()
    rows = db.query("SELECT * FROM events WHERE start_at LIKE ?", (f"{day_str}%",))
    rows.sort(key=lambda r: (r["all_day"], r["start_at"]))
    return rows
