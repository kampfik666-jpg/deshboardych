"""Умный фильтр почты: скрывает спам, рекламу, промо-рассылки.

Пользователь может добавлять свои правила через /api/mail-filters.
Фильтр применяется ко всем письмам перед отображением в дашборде.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import db

# Встроенные паттерны спама/рекламы (нижний регистр)
# ВАЖНО: исключаем сервисные адреса (безопасность, чеки, уведомления)
BUILTIN_SENDER_PATTERNS = [
    # Маркетплейсы и магазины (промо-рассылки) — ТОЛЬКО явные рекламные адреса
    r"newsletter@", r"promo@", r"marketing@",
    r"news@(?!.*yandex|.*google|.*gosuslugi)", 
    # Русские сервисы (рекламные рассылки)
    r"@wildberries\.", r"@ozon\.", r"@lamoda\.", r"@dns-shop\.",
    r"@mvideo\.", r"@eldorado\.", r"@citilink\.",
    r"@aliexpress\.", r"@joom\.", r"@pandao\.",
    # Подписки и рассылки
    r"@subscribe\.", r"@mailer\.", r"@email\.(?!.*openai)", r"@mailing\.",
    r"@digest\.", r"@weekly\.", r"@daily\.",
    # Кэшбэк/бонусы
    r"sberbonus", r"sberspasibo", r"cashback",
    # Соцсети уведомления (если не нужны)
    r"notification@vk\.", r"no-reply@vk\.",
    r"noreply@facebook\.", r"notification@instagram\.",
]

BUILTIN_SUBJECT_PATTERNS = [
    r"(?i)распродаж", r"(?i)скидк", r"(?i)акци[яи]", r"(?i)промокод",
    r"(?i)купон", r"(?i)выгодн", r"(?i)успей", r"(?i)только сегодня",
    r"(?i)не пропуст", r"(?i)специальн", r"(?i)эксклюзив",
    r"(?i)бесплатн", r"(?i)розыгрыш",
    r"(?i)кэшбэк", r"(?i)кешбек", r"(?i)cashback",
    r"(?i)новостн?\s*рассылк", r"(?i)дайджест",
    r"(?i)unsubscribe", r"(?i)отписать",
    r"(?i)\b-sale\b", r"(?i)%\s*(?:скид|off)",
    r"(?i)лучши[еи]\s*предложен", r"(?i)горяч",
    r"(?i)распродажа", r"(?i)black\s*friday", r"(?i)чёрн.*пятниц",
]


@dataclass
class MailFilter:
    """Правило фильтрации."""
    id: int = 0
    kind: str = "sender"       # sender | subject | domain
    pattern: str = ""          # regex или точное совпадение
    action: str = "hide"       # hide | mark_read
    label: str = ""            # человекочитаемое описание
    builtin: bool = False      # встроенное правило (не удаляется пользователем)


def _load_user_filters() -> list[MailFilter]:
    """Загружает пользовательские фильтры из БД."""
    rows = db.query("SELECT * FROM mail_filters ORDER BY id")
    return [
        MailFilter(
            id=r["id"], kind=r["kind"], pattern=r["pattern"],
            action=r["action"], label=r.get("label", ""), builtin=False,
        )
        for r in rows
    ]


def _builtin_filters() -> list[MailFilter]:
    filters = []
    for p in BUILTIN_SENDER_PATTERNS:
        filters.append(MailFilter(kind="sender", pattern=p, action="hide", builtin=True))
    for p in BUILTIN_SUBJECT_PATTERNS:
        filters.append(MailFilter(kind="subject", pattern=p, action="hide", builtin=True))
    return filters


def get_all_filters() -> list[dict]:
    """Все фильтры (встроенные + пользовательские) для API."""
    result = []
    for f in _builtin_filters():
        result.append({
            "id": None, "kind": f.kind, "pattern": f.pattern,
            "action": f.action, "label": f.label or "(встроенное)", "builtin": True,
        })
    for f in _load_user_filters():
        result.append({
            "id": f.id, "kind": f.kind, "pattern": f.pattern,
            "action": f.action, "label": f.label, "builtin": False,
        })
    return result


def add_filter(kind: str, pattern: str, action: str = "hide", label: str = "") -> int:
    """Добавляет пользовательский фильтр."""
    if kind not in ("sender", "subject", "domain"):
        kind = "sender"
    if action not in ("hide", "mark_read"):
        action = "hide"
    return db.execute(
        "INSERT INTO mail_filters(kind, pattern, action, label, created_at) VALUES(?,?,?,?,?)",
        (kind, pattern[:500], action, label[:200], db.utcnow()),
    )


def remove_filter(filter_id: int) -> None:
    db.execute("DELETE FROM mail_filters WHERE id = ?", (filter_id,))


def is_spam(mail: dict) -> tuple[bool, str]:
    """Проверяет письмо на спам. Возвращает (is_spam, reason)."""
    sender = (mail.get("sender") or "").lower()
    subject = (mail.get("subject") or "").lower()

    # Whitelist: никогда не считаем спамом (важные сервисные письма)
    WHITELIST_SENDERS = [
        "accounts.google.com", "id.yandex.ru",
        "messages@avito.ru", "deposit@emails.tinkoff.ru",
        "check.yandex.ru", "market.yandex.ru",
        "steampowered.com", "email.openai.com", "anthropic.com",
        "render.com", "openrouter.ai", "vanyavpn.com",
        "qr.checkscan.ru",
    ]
    for w in WHITELIST_SENDERS:
        if w in sender:
            return False, ""

    # Пользовательские фильтры
    for f in _load_user_filters():
        try:
            if f.kind == "sender" and re.search(f.pattern, sender):
                return True, f"пользовательский фильтр: {f.label or f.pattern}"
            if f.kind == "subject" and re.search(f.pattern, subject):
                return True, f"пользовательский фильтр: {f.label or f.pattern}"
            if f.kind == "domain":
                domain_m = re.search(r"@([^>]+)", sender)
                if domain_m and f.pattern.lower() in domain_m.group(1).lower():
                    return True, f"пользовательский фильтр: {f.label or f.pattern}"
        except re.error:
            continue

    # Встроенные фильтры
    for p in BUILTIN_SENDER_PATTERNS:
        try:
            if re.search(p, sender):
                return True, f"спам-отправитель ({p})"
        except re.error:
            continue
    for p in BUILTIN_SUBJECT_PATTERNS:
        try:
            if re.search(p, subject):
                return True, f"спам-тема ({p[:30]}…)"
        except re.error:
            continue

    return False, ""


def filter_mails(mails: list[dict], show_spam: bool = False) -> dict:
    """Фильтрует список писем. Возвращает {clean: [...], spam: [...]}."""
    clean = []
    spam = []
    for m in mails:
        is_s, reason = is_spam(m)
        if is_s:
            spam.append({**m, "_spam_reason": reason})
        else:
            clean.append(m)
    if show_spam:
        return {"clean": clean, "spam": spam, "total": len(mails), "spam_count": len(spam)}
    return {"clean": clean, "spam_count": len(spam), "total": len(mails)}
