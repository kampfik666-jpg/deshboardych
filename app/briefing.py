"""Утренний брифинг: собирает всё в одно сообщение."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import aiohttp

from . import db, obligations
from .config import settings
from .integrations import caldav_sync, imap_sync
from .llm import llm

log = logging.getLogger(__name__)

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


async def fetch_weather() -> str | None:
    """Погода через wttr.in (без ключа, работает из РФ)."""
    city = settings.weather_city
    if not city:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            # Компактный текстовый формат — быстрый ответ, маленький payload
            fmt = "%C+%t+(%f)+%h+%w"
            url = f"https://wttr.in/{city}?format={fmt}&lang=ru"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                text = (await resp.text()).strip()
                if not text or "Unknown" in text:
                    return None

        # Парсим: "Пасмурно +3°C (-1°C) 94% ↑12km/h"
        parts = text.split("+", 1)
        desc = parts[0].strip() if parts else ""
        rest = "+" + parts[1] if len(parts) > 1 else ""

        # Извлекаем температуру
        import re as _re
        temp_m = _re.search(r'([+-]?\d+)°C', text)
        feels_m = _re.search(r'\(([+-]?\d+)°C\)', text)
        humidity_m = _re.search(r'(\d+)%', text)
        wind_m = _re.search(r'(\d+)\s*km/h', text)

        line = f"🌤 Погода в г. {city}: {desc}"
        if temp_m:
            line += f", {temp_m.group(1)}°C"
        if feels_m:
            line += f" (ощущается {feels_m.group(1)}°C)"
        if humidity_m:
            line += f", влажность {humidity_m.group(1)}%"
        if wind_m:
            line += f", ветер {wind_m.group(1)} км/ч"
        return line
    except Exception as exc:  # noqa: BLE001
        log.debug("Weather fetch failed: %s", exc)
        return None


def collect_facts(day: date) -> dict:
    """Сырые данные для брифинга."""
    events = caldav_sync.events_for_day(day)
    horizon = day + timedelta(days=7)
    payments = obligations.upcoming(days=7)
    tasks = db.query(
        "SELECT * FROM tasks WHERE status='open' ORDER BY due_date IS NULL, due_date, id"
    )
    due_today = [
        t for t in tasks
        if t.get("due_date") and t["due_date"][:10] <= day.isoformat()
    ]
    without_date = [t for t in tasks if not t.get("due_date")][:5]
    next_tasks = db.query(
        "SELECT * FROM tasks WHERE status='open' AND due_date IS NOT NULL AND due_date <= ? "
        "ORDER BY due_date LIMIT 12",
        ((day + timedelta(days=14)).isoformat(),),
    )
    mails = imap_sync.recent_mails(limit=5, unread_only=True) or imap_sync.recent_mails(limit=5)
    unread = imap_sync.unread_count()
    tomorrow_events = caldav_sync.events_for_day(day + timedelta(days=1))
    return {
        "events": events,
        "tomorrow_events": tomorrow_events,
        "payments": payments,
        "due_today": due_today,
        "without_date": without_date,
        "next_tasks": next_tasks,
        "mails": mails,
        "unread": unread,
        "horizon": horizon,
    }


def render_template(day: date, facts: dict, weather: str | None) -> str:
    lines: list[str] = []
    name = db.get_setting("owner_name", "").strip()
    greet = f"☀️ Доброе утро, {name}!" if name else "☀️ Доброе утро!"
    lines.append(
        f"{greet} Брифинг на {WEEKDAYS[day.weekday()]}, "
        f"{day.day} {MONTHS[day.month - 1]} {day.year}"
    )
    if weather:
        lines.append(weather)

    # Платежи
    today_str = day.isoformat()
    due_now = [p for p in facts["payments"] if p["next_date"] <= today_str]
    due_week = [p for p in facts["payments"] if today_str < p["next_date"] <= facts["horizon"].isoformat()]
    if due_now:
        lines.append("")
        lines.append("💰 Сегодня/просрочено:")
        for p in due_now:
            amount = f" — {p['amount']:g} {p.get('currency') or 'RUB'}" if p.get("amount") else ""
            mark = "⚠️ просрочено: " if p.get("overdue") else ""
            lines.append(f"  • {mark}{p['title']}{amount} ({p['next_date']})")
    if due_week:
        lines.append("")
        lines.append("💳 Платежи на неделе:")
        for p in due_week:
            amount = f" — {p['amount']:g} {p.get('currency') or 'RUB'}" if p.get("amount") else ""
            lines.append(f"  • {p['next_date']}: {p['title']}{amount}")

    # Календарь
    lines.append("")
    if facts["events"]:
        lines.append("📅 Сегодня в календаре:")
        for e in facts["events"]:
            if e["all_day"]:
                lines.append(f"  • весь день: {e['title']}")
            else:
                t = e["start_at"][11:16]
                loc = f" @ {e['location']}" if e.get("location") else ""
                lines.append(f"  • {t} — {e['title']}{loc}")
    else:
        lines.append("📅 Сегодня в календаре пусто.")
    if facts["tomorrow_events"]:
        first = facts["tomorrow_events"][0]
        when = "весь день" if first["all_day"] else first["start_at"][11:16]
        lines.append(f"   Завтра первым делом: {first['title']} ({when})")

    # Задачи
    if facts["due_today"]:
        lines.append("")
        lines.append("✅ Задачи:")
        for t in facts["due_today"][:8]:
            lines.append(f"  • {t['title']}")
    elif facts["without_date"]:
        lines.append("")
        lines.append("✅ Открытые задачи (без срока):")
        for t in facts["without_date"]:
            lines.append(f"  • {t['title']}")

    # Почта
    if facts["mails"]:
        lines.append("")
        total_unread = sum(facts["unread"].values())
        head = f"📬 Почта: {total_unread} непрочитанных." if total_unread else "📬 Почта, последнее:"
        lines.append(head)
        for m in facts["mails"][:5]:
            subj = m.get("subject") or "(без темы)"
            sender = (m.get("sender") or "").split("<")[0].strip()[:40]
            lines.append(f"  • {subj} — {sender}")

    return "\n".join(lines)


async def polish_with_llm(template_text: str) -> str:
    """LLM-версия брифинга: короче и человечнее, но факты те же."""
    answer = await llm.chat(
        [
            {
                "role": "system",
                "content": (
                    "Ты составляешь утренний брифинг для пользователя. Перепиши черновик кратко, "
                    "тепло и по-человечески (до 200 слов), сохрани ВС даты, суммы и названия. "
                    "Используй простые эмодзи для разделов. Ничего не выдумывай."
                ),
            },
            {"role": "user", "content": template_text},
        ],
        temperature=0.4,
        max_tokens=700,
    )
    return answer or template_text


async def build_briefing(day: date | None = None) -> str:
    day = day or datetime.now().astimezone().date()
    weather = await fetch_weather()
    facts = collect_facts(day)
    text = render_template(day, facts, weather)
    if settings.briefing_use_llm and llm.available:
        text = await polish_with_llm(text)
    return text


async def send_briefing(day: date | None = None) -> str:
    """Собирает брифинг, синхронизирует сервисы и отправляет в Telegram."""
    from . import sync as sync_mod

    try:
        await sync_mod.sync_all()
    except Exception as exc:  # noqa: BLE001
        log.warning("Pre-briefing sync failed: %s", exc)

    text = await build_briefing(day)
    sent = 0
    chat_ids = db.owner_ids()
    if settings.bot_available and chat_ids:
        try:
            from telegram import Bot

            bot = Bot(settings.bot_token)
            for chat_id in chat_ids:
                await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
                sent += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Briefing send failed: %s", exc)
            text += f"\n\n(не удалось отправить в Telegram: {exc})"
    elif settings.bot_available and not chat_ids:
        text += "\n\n(владелец ещё не зарегистрирован — напиши боту /start в Telegram)"
    day_str = (day or datetime.now().astimezone().date()).isoformat()
    db.execute(
        "INSERT INTO briefings(day, text, sent, created_at) VALUES(?,?,?,?)",
        (day_str, text, sent, db.utcnow()),
    )
    return text


def latest_briefing() -> dict | None:
    return db.query_one(
        "SELECT * FROM briefings ORDER BY id DESC LIMIT 1"
    )
