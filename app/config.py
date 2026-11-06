"""Настройки Life Hub, читаются из .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _split_ids(raw: str) -> list[int]:
    result = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


@dataclass
class Settings:
    # Telegram
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    chat_ids: list[int] = field(
        default_factory=lambda: _split_ids(os.getenv("TELEGRAM_CHAT_ID", ""))
    )

    # Пути и время
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "data/lifehub.sqlite3"))
    upload_dir: str = field(default_factory=lambda: os.getenv("UPLOAD_DIR", "data/uploads"))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Asia/Yekaterinburg"))
    briefing_time: str = field(default_factory=lambda: os.getenv("BRIEFING_TIME", "06:00"))
    briefing_use_llm: bool = field(default_factory=lambda: _bool("BRIEFING_USE_LLM", "true"))

    # LLM
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    )
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))

    # Яндекс (пароли приложений разделяются: почта и календарь — разные)
    yandex_enabled: bool = field(default_factory=lambda: _bool("YANDEX_ENABLED"))
    yandex_login: str = field(default_factory=lambda: os.getenv("YANDEX_LOGIN", ""))
    yandex_mail_password: str = field(
        default_factory=lambda: os.getenv("YANDEX_MAIL_PASSWORD", "")
    )
    yandex_caldav_password: str = field(
        default_factory=lambda: os.getenv("YANDEX_CALDAV_PASSWORD", "")
    )
    yandex_app_password: str = field(
        default_factory=lambda: os.getenv("YANDEX_APP_PASSWORD", "")
    )

    # Google (пароль приложения обычно один на всё, но поддержим и раздельные)
    google_enabled: bool = field(default_factory=lambda: _bool("GOOGLE_ENABLED"))
    google_email: str = field(default_factory=lambda: os.getenv("GOOGLE_EMAIL", ""))
    google_mail_password: str = field(
        default_factory=lambda: os.getenv("GOOGLE_MAIL_PASSWORD", "")
    )
    google_caldav_password: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CALDAV_PASSWORD", "")
    )
    google_app_password: str = field(
        default_factory=lambda: os.getenv("GOOGLE_APP_PASSWORD", "")
    )

    # Синхронизация
    sync_every_minutes: int = field(default_factory=lambda: _int("SYNC_EVERY_MINUTES", 30))
    mail_since_days: int = field(default_factory=lambda: _int("MAIL_SINCE_DAYS", 7))
    mail_fetch_limit: int = field(default_factory=lambda: _int("MAIL_FETCH_LIMIT", 50))

    # Погода
    weather_city: str = field(default_factory=lambda: os.getenv("WEATHER_CITY", "").strip())

    # Веб
    web_host: str = field(default_factory=lambda: os.getenv("WEB_HOST", "127.0.0.1"))
    web_port: int = field(default_factory=lambda: _int("WEB_PORT", 8765))

    # Мини-апп Telegram (публичный туннель + защита токеном)
    miniapp_enabled: bool = field(default_factory=lambda: _bool("MINIAPP_ENABLED", "true"))
    web_app_token: str = field(default_factory=lambda: os.getenv("WEB_APP_TOKEN", ""))

    @property
    def llm_available(self) -> bool:
        return bool(self.llm_api_key.strip())

    @property
    def bot_available(self) -> bool:
        token = self.bot_token.strip()
        return bool(token) and token != "put_your_token_here"

    def abs_db_path(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else BASE_DIR / p

    def abs_upload_dir(self) -> Path:
        p = Path(self.upload_dir)
        return p if p.is_absolute() else BASE_DIR / p

    def enabled_sources(self) -> dict[str, dict]:
        """Активные источники почты/календаря: имя -> параметры.

        Пароли для IMAP и CalDAV могут различаться (Яндекс выдаёт отдельные
        пароли приложений на каждый сервис). Если раздельные не заданы —
        используется общий *_APP_PASSWORD.
        """
        sources: dict[str, dict] = {}
        if self.yandex_enabled and self.yandex_login:
            mail_pw = self.yandex_mail_password or self.yandex_app_password
            cal_pw = self.yandex_caldav_password or self.yandex_app_password
            if mail_pw or cal_pw:
                sources["yandex"] = {
                    "label": "Яндекс",
                    "login": self.yandex_login,
                    "imap_password": mail_pw,
                    "caldav_password": cal_pw,
                    "imap_host": "imap.yandex.ru",
                    "caldav_url": "https://caldav.yandex.ru/",
                }
        if self.google_enabled and self.google_email:
            mail_pw = self.google_mail_password or self.google_app_password
            cal_pw = self.google_caldav_password or self.google_app_password
            if mail_pw or cal_pw:
                sources["google"] = {
                    "label": "Google",
                    "login": self.google_email,
                    "imap_password": mail_pw,
                    "caldav_password": cal_pw,
                    "imap_host": "imap.gmail.com",
                    "caldav_url": "https://www.google.com/calendar/dav/",
                }
        return sources


settings = Settings()
