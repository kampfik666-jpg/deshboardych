"""Синхронизация почты по IMAP (Яндекс Почта, Gmail).

Функции синхронные — вызывать через asyncio.to_thread.
"""
from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape

from .. import db

log = logging.getLogger(__name__)


def _decode_header(raw: str | None) -> str:
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    out = []
    for data, charset in parts:
        if isinstance(data, bytes):
            try:
                out.append(data.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                out.append(data.decode("utf-8", errors="replace"))
        else:
            out.append(data)
    return "".join(out).strip()


def _snippet_from_bytes(body: bytes, content_type: str = "text/plain") -> str:
    """Декодирует тело письма с учётом Content-Transfer-Encoding."""
    import base64
    import quopri

    # Проверяем encoding в заголовках (если передан raw MIME part)
    raw = body
    try:
        # Пробуем декодировать base64
        decoded = base64.b64decode(raw, validate=False)
        if len(decoded) > 10 and all(c < 128 or c > 127 for c in decoded[:50]):
            raw = decoded
    except Exception:
        pass

    try:
        # Пробуем декодировать quoted-printable
        decoded = quopri.decodestring(raw)
        if b"=" not in decoded[:100] or b"<html" in decoded.lower():
            raw = decoded
    except Exception:
        pass

    text = raw.decode("utf-8", errors="replace")
    if "html" in content_type or "<html" in text.lower()[:200]:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:3000]


def fetch_source_mails(
    source: str,
    host: str,
    username: str,
    password: str,
    since_days: int = 7,
    limit: int = 50,
    folder: str = "INBOX",
) -> tuple[int, str | None]:
    """Тянет свежие письма источника в кэш mails. Возвращает (число писем, ошибка)."""
    try:
        conn = imaplib.IMAP4_SSL(host)
        conn.login(username, password)
        # Gmail требует от клиента представиться (ID), иначе "Unsafe Login"
        try:
            conn.xatom("ID", '("name" "LifeHub" "version" "1.0" "vendor" "lifehub")')
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        log.warning("IMAP %s login failed: %s", source, exc)
        return 0, f"{type(exc).__name__}: {exc}"

    saved = 0
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            return 0, f"не удалось открыть папку {folder}"
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%d-%b-%Y")
        status, data = conn.search(None, f'(SINCE "{since}")')
        if status != "OK":
            return 0, "поиск писем не удался"
        ids = data[0].split()[-limit:]
        now = db.utcnow()
        for num in ids:
            try:
                status, msg_data = conn.fetch(
                    num, "(FLAGS BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.20000>)"
                )
                if status != "OK" or not msg_data:
                    continue
                flags_blob = b""
                header_blob = b""
                text_blob = b""
                for part in msg_data:
                    if isinstance(part, tuple) and len(part) >= 2:
                        meta = part[0].decode("utf-8", errors="replace")
                        if "HEADER" in meta:
                            header_blob = part[1]
                        elif "TEXT" in meta:
                            text_blob = part[1]
                    elif isinstance(part, bytes):
                        flags_blob = part
                if not header_blob:
                    continue
                msg = email.message_from_bytes(header_blob)
                flags_text = (flags_blob.decode("utf-8", errors="replace") if flags_blob else "") \
                    + " ".join(
                        p[0].decode("utf-8", errors="replace")
                        for p in msg_data
                        if isinstance(p, tuple)
                    )
                unread = 1 if "\\Seen" not in flags_text else 0
                message_id = (msg.get("Message-ID") or "").strip() or f"{source}-{num.decode()}"
                date_raw = msg.get("Date") or ""
                parsed_date = email.utils.parsedate_to_datetime(date_raw) if date_raw else None
                date_iso = (
                    parsed_date.astimezone().isoformat(timespec="seconds")
                    if parsed_date
                    else now
                )
                snippet = ""
                if text_blob:
                    # Парсим как MIME message чтобы правильно декодировать base64/qp
                    try:
                        full_msg = email.message_from_bytes(header_blob + b"\r\n\r\n" + text_blob)
                        # Извлекаем текстовую часть через walk()
                        text_part = None
                        html_part = None
                        for part in full_msg.walk():
                            ct = part.get_content_type()
                            if ct == "text/plain" and text_part is None:
                                text_part = part
                            elif ct == "text/html" and html_part is None:
                                html_part = part
                        chosen = text_part or html_part
                        if chosen:
                            payload = chosen.get_payload(decode=True)  # auto-decodes base64/qp
                            charset = chosen.get_content_charset() or "utf-8"
                            decoded = payload.decode(charset, errors="replace")
                            if chosen.get_content_type() == "text/html":
                                decoded = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", decoded)
                                decoded = re.sub(r"(?s)<[^>]+>", " ", decoded)
                                from html import unescape as _unescape
                                decoded = _unescape(decoded)
                            snippet = re.sub(r"\s+", " ", decoded).strip()[:3000]
                        else:
                            snippet = _snippet_from_bytes(text_blob)
                    except Exception:
                        snippet = _snippet_from_bytes(text_blob)
                with db.db() as d:
                    d.execute(
                        "INSERT INTO mails(source, folder, message_id, subject, sender, date, "
                        "snippet, unread, fetched_at) VALUES(?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(source, message_id) DO UPDATE SET "
                        "subject=excluded.subject, unread=excluded.unread, snippet=excluded.snippet",
                        (
                            source,
                            folder,
                            message_id[:300],
                            _decode_header(msg.get("Subject"))[:300],
                            _decode_header(msg.get("From"))[:200],
                            date_iso,
                            snippet,
                            unread,
                            now,
                        ),
                    )
                saved += 1
            except Exception as exc:  # noqa: BLE001
                log.debug("IMAP %s fetch item failed: %s", source, exc)
                continue
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
    return saved, None


def recent_mails(limit: int = 50, unread_only: bool = False) -> list[dict]:
    where = "WHERE unread = 1" if unread_only else ""
    return db.query(
        f"SELECT * FROM mails {where} ORDER BY date DESC LIMIT ?",
        (limit,),
    )


def unread_count() -> dict[str, int]:
    rows = db.query(
        "SELECT source, COUNT(*) AS n FROM mails WHERE unread = 1 GROUP BY source"
    )
    return {r["source"]: r["n"] for r in rows}
