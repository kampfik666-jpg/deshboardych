"""Планировщик: утренняя рассылка и периодическая синхронизация."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import db, sync as sync_mod
from .briefing import send_briefing
from .config import settings

log = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=settings.timezone)


async def _briefing_job() -> None:
    try:
        await send_briefing()
        log.info("Morning briefing sent")
    except Exception:  # noqa: BLE001
        log.exception("Briefing job failed")


async def _payment_reminders_job() -> None:
    """Ежедневные напоминания о платежах (за 3 дня и каждый день до оплаты)."""
    from . import finance as fin
    reminders = fin.upcoming_payment_reminders()
    if not reminders:
        return
    chat_ids = db.owner_ids()
    if not chat_ids or not settings.bot_available:
        return
    lines = ["🔔 <b>Напоминание о платежах:</b>\n"]
    for r in reminders:
        amt = f" — {r['amount']:g} {r.get('currency', 'RUB')}" if r.get("amount") else ""
        lines.append(f"{r['urgency']}: <b>{r['title']}</b>{amt} (до {r['due_date']})")
    text = "\n".join(lines)
    try:
        from telegram import Bot
        bot = Bot(settings.bot_token)
        for cid in chat_ids:
            await bot.send_message(chat_id=cid, text=text, parse_mode="HTML")
        log.info("Payment reminders sent to %d chats", len(chat_ids))
    except Exception:  # noqa: BLE001
        log.exception("Payment reminders failed")


async def _sync_job() -> None:
    try:
        await sync_mod.sync_all()
    except Exception:  # noqa: BLE001
        log.exception("Sync job failed")


def start_scheduler() -> None:
    hour, minute = 6, 0
    try:
        hh, mm = settings.briefing_time.split(":")
        hour, minute = int(hh), int(mm)
    except ValueError:
        log.warning("Bad BRIEFING_TIME=%r, using 06:00", settings.briefing_time)

    scheduler.add_job(
        _briefing_job,
        CronTrigger(hour=hour, minute=minute, timezone=settings.timezone),
        id="morning_briefing",
        replace_existing=True,
    )
    scheduler.add_job(
        _sync_job,
        IntervalTrigger(minutes=settings.sync_every_minutes),
        id="periodic_sync",
        replace_existing=True,
    )
    # Напоминания о платежах — каждый день в 09:00
    scheduler.add_job(
        _payment_reminders_job,
        CronTrigger(hour=9, minute=0, timezone=settings.timezone),
        id="payment_reminders",
        replace_existing=True,
    )
    # Первичная синхронизация через минуту после старта
    scheduler.add_job(
        _sync_job, "date", id="initial_sync",
        run_date=datetime.now().astimezone() + timedelta(minutes=1),
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started: briefing at %02d:%02d (%s), sync every %d min",
        hour, minute, settings.timezone, settings.sync_every_minutes,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
