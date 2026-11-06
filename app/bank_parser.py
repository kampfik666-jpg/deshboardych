"""Парсер писем от банков: автоматический учёт расходов из email-уведомлений."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from . import db, finance

log = logging.getLogger(__name__)

# Паттерны отправителей банков
BANK_SENDERS = [
    r"sberbank\.ru",
    r"sber\.",
    r"notify@sber",
    r"no-reply@sber",
    r"tinkoff\.ru",
    r"t-bank\.ru",
    r"alfabank",
    r"vtb\.ru",
    r"raiffeisen",
]

# Паттерны для извлечения суммы и описания из текста письма
AMOUNT_PATTERNS = [
    r"списан[оаы]?\s*[:\-]?\s*(\d[\d\s.,]*\d)\s*(?:руб|₽|RUB)",
    r"сумм[аы]\s*(?:операции|списания|покупки)?\s*[:\-]?\s*(\d[\d\s.,]*\d)\s*(?:руб|₽|RUB)",
    r"(\d[\d\s.,]*\d)\s*(?:руб|₽|RUB)\s*(?:списано|оплачен|покупк)",
    r"оплат[аы][^\d]*(\d[\d\s.,]*\d)\s*(?:руб|₽|RUB)",
    r"покупк[аи][^\d]*(\d[\d\s.,]*\d)\s*(?:руб|₽|RUB)",
    # Формат "1 234.56 ₽" или "1234,56 руб"
    r"(\d{1,3}(?:\s\d{3})*(?:[.,]\d{1,2})?)\s*(?:руб|₽)",
]

DESC_PATTERNS = [
    r"(?:в\s+(?:пользу|адрес)|получатель|место\s*покупки|торговая\s*точка|магазин)[:\s]+([^\n,;]{3,80})",
    r"(?:оплат[аы]|покупк[аи]|перевод)[:\s]+([^\n,;]{3,80})",
    r"MCC[:\s]*(\d{4})\s*[-–]?\s*([^\n]{3,50})",
]

DATE_PATTERNS = [
    r"(\d{2}[./-]\d{2}[./-]\d{4})",
    r"(\d{4}[./-]\d{2}[./-]\d{2})",
    r"(\d{1,2}\s+(?:январ|феврал|марта|апрел|мая|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*\s+\d{4})",
]


def is_bank_email(sender: str) -> bool:
    """Проверяет, является ли письмо банковским уведомлением."""
    low = sender.lower()
    return any(re.search(p, low) for p in BANK_SENDERS)


def parse_amount(text: str) -> float | None:
    """Извлекает сумму из текста."""
    for pattern in AMOUNT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(" ", "").replace(",", ".")
            try:
                amount = float(raw)
                if 0.01 <= amount <= 9_999_999:
                    return amount
            except ValueError:
                continue
    return None


def parse_description(text: str) -> str:
    """Извлекает описание операции."""
    for pattern in DESC_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            desc = m.group(m.lastindex).strip()
            if len(desc) >= 3:
                return desc[:200]
    return ""


def parse_date_from_text(text: str) -> str:
    """Извлекает дату операции из текста."""
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            raw = m.group(1)
            for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    return datetime.strptime(raw.replace("/", ".").replace("-", "."), fmt).date().isoformat()
                except ValueError:
                    continue
    return date.today().isoformat()


def is_expense_notification(subject: str, body: str) -> bool:
    """Определяет, является ли письмо уведомлением о списании (не пополнении)."""
    combined = f"{subject} {body}".lower()
    expense_keywords = ["списан", "оплат", "покупк", "перевод", "снят", "расход"]
    income_keywords = ["зачислен", "поступил", "пополнен", "возврат", "кэшбэк", "кешбек", "начислен"]

    has_expense = any(kw in combined for kw in expense_keywords)
    has_income = any(kw in combined for kw in income_keywords)

    return has_expense and not has_income


def process_bank_email(mail: dict) -> dict | None:
    """Обрабатывает банковское письмо и возвращает данные расхода или None."""
    sender = mail.get("sender", "")
    subject = mail.get("subject", "")
    body = mail.get("snippet", "")

    if not is_bank_email(sender):
        return None

    if not is_expense_notification(subject, body):
        return None

    amount = parse_amount(body) or parse_amount(subject)
    if not amount:
        log.debug("Bank email without amount: %s", subject[:50])
        return None

    description = parse_description(body) or subject[:100]
    expense_date = parse_date_from_text(body)
    category = finance.classify_expense(description)

    # Проверяем дубликат (same date + amount + similar desc within 24h)
    existing = db.query_one(
        "SELECT id FROM expenses WHERE date = ? AND amount = ? AND source = 'bank_email' "
        "AND created_at > datetime('now', '-1 day') LIMIT 1",
        (expense_date, amount),
    )
    if existing:
        return None

    expense_id = finance.add_expense(
        expense_date=expense_date,
        amount=amount,
        description=description,
        category=category,
        source="bank_email",
    )

    return {
        "id": expense_id,
        "date": expense_date,
        "amount": amount,
        "category": category,
        "description": description,
    }


def scan_mails_for_expenses(mails: list[dict]) -> list[dict]:
    """Сканирует список писем и извлекает расходы из банковских уведомлений."""
    found = []
    for mail in mails:
        result = process_bank_email(mail)
        if result:
            found.append(result)
    return found
