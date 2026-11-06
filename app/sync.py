"""Общая синхронизация всех подключённых сервисов."""
from __future__ import annotations

import asyncio
import logging

from . import db
from .config import settings
from .integrations import caldav_sync, imap_sync

log = logging.getLogger(__name__)


def _log_sync(source: str, kind: str, ok: bool, detail: str) -> None:
    db.execute(
        "INSERT INTO sync_log(source, kind, ok, detail, created_at) VALUES(?,?,?,?,?)",
        (source, kind, 1 if ok else 0, detail[:500], db.utcnow()),
    )


async def sync_all() -> dict:
    """Синхронизирует календари и почту всех включённых источников."""
    sources = settings.enabled_sources()
    results: dict[str, dict] = {}
    if not sources:
        return {"message": "Нет подключённых сервисов — заполните .env (Яндекс/Google)."}

    for name, cfg in sources.items():
        entry: dict = {}
        # Календарь
        if cfg.get("caldav_password"):
            try:
                count, err = await asyncio.to_thread(
                    caldav_sync.fetch_source_events,
                    name, cfg["caldav_url"], cfg["login"], cfg["caldav_password"],
                )
                entry["events"] = count
                entry["events_error"] = err
                _log_sync(name, "caldav", err is None, err or f"{count} событий")
            except Exception as exc:  # noqa: BLE001
                entry["events"] = 0
                entry["events_error"] = str(exc)
                _log_sync(name, "caldav", False, str(exc))
        else:
            entry["events"] = 0
            entry["events_error"] = "не задан пароль календаря"
        # Почта
        if cfg.get("imap_password"):
            try:
                count, err = await asyncio.to_thread(
                    imap_sync.fetch_source_mails,
                    name, cfg["imap_host"], cfg["login"], cfg["imap_password"],
                    settings.mail_since_days, settings.mail_fetch_limit,
                )
                entry["mails"] = count
                entry["mails_error"] = err
                _log_sync(name, "imap", err is None, err or f"{count} писем")
            except Exception as exc:  # noqa: BLE001
                entry["mails"] = 0
                entry["mails_error"] = str(exc)
                _log_sync(name, "imap", False, str(exc))
        else:
            entry["mails"] = 0
            entry["mails_error"] = "не задан пароль почты"
        results[name] = entry
    return results


def last_sync_info() -> list[dict]:
    return db.query(
        "SELECT source, kind, ok, detail, created_at FROM sync_log "
        "WHERE id IN (SELECT MAX(id) FROM sync_log GROUP BY source, kind) "
        "ORDER BY source, kind"
    )
