"""Обязательства и платежи: извлечение из документов, учёт сроков."""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from . import db
from .llm import llm

log = logging.getLogger(__name__)

EXTRACT_SYSTEM = (
    "Ты — ассистент, который наводит порядок в личных документах. "
    "Отвечай только валидным JSON без пояснений."
)

EXTRACT_PROMPT = """Проанализируй фрагмент документа «{title}» и найди все обязательства пользователя:
регулярные и разовые платежи (ЖКХ, свет, интернет, телефон, кредиты, ипотека, налоги, пошлины),
страховки (ОСАГО, КАСКО, жизнь, имущество) с датами продления,
истекающие документы (паспорт, права, подписки с автопродлением),
дедлайны по договорам (оплатить до, расторгнуть до, уведомить до).

Для каждого обязательства верни JSON-массив объектов:
[{{
  "title": "короткое название, например: Оплата электроэнергии",
  "category": "жкх|страховка|кредит|налог|подписка|документ|прочее",
  "amount": число или null,
  "currency": "RUB" или другая,
  "kind": "once|monthly|yearly",
  "due_date": "ГГГГ-ММ-ДД для разовых, иначе null",
  "day_of_month": число 1-31 для ежемесячных, иначе null,
  "month_of_year": число 1-12 для ежегодных, иначе null,
  "note": "важные детали: реквизиты, номер договора, сумма, до какого числа"
}}]

Если обязательств нет — верни пустой массив [].
Текущая дата: {today}.

ФРАГМЕНТ ДОКУМЕНТА:
{text}"""


def _clean_date(value: object) -> str | None:
    if isinstance(value, str):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                date(y, mo, d)
                return f"{y:04d}-{mo:02d}-{d:02d}"
            except ValueError:
                return None
    return None


async def extract_from_document(doc_id: int, text: str, title: str) -> list[dict]:
    """Ищет в тексте документа обязательства. LLM + регулярный запасной вариант."""
    if not text.strip():
        return []
    snippet = text[:12000]
    found: list[dict] = []
    if llm.available:
        raw = await llm.json(
            EXTRACT_PROMPT.format(title=title, today=date.today().isoformat(), text=snippet),
            system=EXTRACT_SYSTEM,
        )
        if isinstance(raw, dict) and isinstance(raw.get("obligations"), list):
            raw = raw["obligations"]
        if isinstance(raw, list):
            for item in raw:
                saved = _save_obligation(doc_id, item)
                if saved:
                    found.append(saved)
    if not found:
        # Запасной вариант без LLM: предложения с признаками платежей и датами
        found = _regex_extract(doc_id, text)
    return found


def _save_obligation(doc_id: int | None, item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    if not title or len(title) < 3:
        return None
    kind = str(item.get("kind") or "once").lower()
    if kind not in ("once", "monthly", "yearly"):
        kind = "once"
    due = _clean_date(item.get("due_date"))
    day = item.get("day_of_month")
    month = item.get("month_of_year")
    day = int(day) if isinstance(day, (int, float)) and 1 <= int(day) <= 31 else None
    month = int(month) if isinstance(month, (int, float)) and 1 <= int(month) <= 12 else None
    if kind == "monthly" and day is None and due:
        day = int(due[8:10])
    if kind == "yearly" and due:
        month = month or int(due[5:7])
        day = day or int(due[8:10])
    if kind == "once" and not due and day:
        kind = "monthly"
    amount = item.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    oid = db.execute(
        "INSERT INTO obligations(doc_id, title, category, amount, currency, kind, due_date, "
        "day_of_month, month_of_year, note, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            doc_id,
            title[:200],
            str(item.get("category") or "прочее")[:50],
            amount,
            str(item.get("currency") or "RUB")[:10],
            kind,
            due,
            day,
            month,
            str(item.get("note") or "")[:500],
            db.utcnow(),
        ),
    )
    return {
        "id": oid,
        "title": title,
        "category": str(item.get("category") or "прочее"),
        "amount": amount,
        "kind": kind,
        "due_date": due,
        "day_of_month": day,
        "month_of_year": month,
        "note": str(item.get("note") or ""),
    }


PAYMENT_HINTS = re.compile(
    r"(оплат|платеж|платёж|взнос|квитанц|страхов|полис|осаго|каско|ипотек|кредит|"
    r"налог|пошлин|подписк|продл|истека|дедлайн|жкх|электроэнерг|свет\b|интернет|телефон)",
    re.IGNORECASE,
)
DATE_PATTERNS = [
    (re.compile(r"(\d{2})\.(\d{2})\.(\d{4})"), lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
]
MONTHS = {
    "январ": 1, "феврал": 2, "марта": 3, "мар": 3, "апрел": 4, "мая": 5, "май": 5,
    "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
TEXT_DATE = re.compile(r"(\d{1,2})\s*(" + "|".join(MONTHS) + r"\w*)\s*(\d{4})?", re.IGNORECASE)
DAY_OF_MONTH_RE = re.compile(r"(?:до\s*)?(\d{1,2})\s*(?:-?го\s*)?числа", re.IGNORECASE)
MONTHLY_RE = re.compile(r"ежемесячн|кажд(?:ый|ого)\s+месяц|раз\s+в\s+месяц", re.IGNORECASE)
YEARLY_RE = re.compile(r"ежегодн|раз\s+в\s+год", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(\d[\d\s]{1,10}(?:[.,]\d{1,2})?)\s*(?:руб|р\.|₽)", re.IGNORECASE)
# делим текст на предложения, НЕ разрывая даты вида 20.05.2027 и «Дом.ру»
SENTENCE_SPLIT_RE = re.compile(r"[\n;!?]+|\.\s+")


def _regex_extract(doc_id: int, text: str) -> list[dict]:
    """Простое извлечение без LLM: предложения про платежи с датами."""
    found: list[dict] = []
    seen: set[str] = set()
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    for i, sent in enumerate(sentences):
        if not (15 <= len(sent) <= 300) or not PAYMENT_HINTS.search(sent):
            continue
        # Смотрим и на следующее предложение: дата часто переносится на новую строку.
        # Но если в нём есть собственный признак платежа — не смешиваем факты.
        ctx = sent
        if i + 1 < len(sentences) and not PAYMENT_HINTS.search(sentences[i + 1]):
            ctx = sent + " " + sentences[i + 1][:150]

        due = None
        for pattern, fmt in DATE_PATTERNS:
            m = pattern.search(ctx)
            if m:
                due = fmt(m)
                break
        if not due:
            m = TEXT_DATE.search(ctx.lower())
            if m:
                month = MONTHS.get(m.group(2)[:5].lower())
                year = int(m.group(3)) if m.group(3) else date.today().year
                if month:
                    due = f"{year:04d}-{month:02d}-{int(m.group(1)):02d}"

        day = None
        month = None
        m = DAY_OF_MONTH_RE.search(ctx)
        if m and 1 <= int(m.group(1)) <= 31:
            day = int(m.group(1))

        kind = "once"
        if MONTHLY_RE.search(ctx) or (day is not None and not due):
            kind = "monthly"
        elif YEARLY_RE.search(ctx):
            kind = "yearly"
            if due:
                month = int(due[5:7])
                day = day or int(due[8:10])

        if not due and day is None:
            continue  # без даты это просто шум

        amount = None
        amount_m = AMOUNT_RE.search(ctx)
        if amount_m:
            try:
                amount = float(amount_m.group(1).replace(" ", "").replace(",", "."))
            except ValueError:
                amount = None

        title = sent[:120]
        if title in seen:
            continue
        seen.add(title)
        saved = _save_obligation(
            doc_id,
            {
                "title": title,
                "category": "прочее",
                "amount": amount,
                "kind": kind,
                "due_date": due,
                "day_of_month": day if kind in ("monthly", "yearly") else None,
                "month_of_year": month,
                "note": "найдено без LLM (по тексту)",
            },
        )
        if saved:
            found.append(saved)
        if len(found) >= 10:
            break
    return found


def next_occurrence(obl: dict, after: date) -> date | None:
    """Ближайшая дата обязательства начиная с after."""
    kind = obl.get("kind") or "once"
    if kind == "once":
        due = obl.get("due_date")
        if due:
            try:
                return date.fromisoformat(due)
            except ValueError:
                return None
        return None
    if kind == "monthly":
        day = obl.get("day_of_month") or 1
        candidate = _safe_date(after.year, after.month, day) or date(after.year, after.month, 28)
        if candidate < after:
            ny, nm = (after.year + 1, 1) if after.month == 12 else (after.year, after.month + 1)
            candidate = _safe_date(ny, nm, day) or date(ny, nm, 28)
        return candidate
    if kind == "yearly":
        month = obl.get("month_of_year") or 1
        day = obl.get("day_of_month") or 1
        candidate = _safe_date(after.year, month, day) or date(after.year, month, 28)
        if candidate < after:
            candidate = _safe_date(after.year + 1, month, day) or date(after.year + 1, month, 28)
        return candidate
    return None


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def upcoming(days: int = 60, include_done: bool = False) -> list[dict]:
    """Обязательства с ближайшими датами в пределах N дней (включая просроченные)."""
    today = date.today()
    horizon = today + timedelta(days=days)
    status_filter = "" if include_done else "WHERE status = 'active'"
    rows = db.query(f"SELECT * FROM obligations {status_filter}")
    result = []
    for obl in rows:
        nxt = next_occurrence(obl, today)
        if not nxt:
            continue
        overdue = nxt < today
        if nxt <= horizon or overdue:
            result.append({**obl, "next_date": nxt.isoformat(), "overdue": overdue})
    result.sort(key=lambda r: r["next_date"])
    return result


def add_manual(data: dict) -> int:
    return (
        _save_obligation(
            None,
            {
                "title": data.get("title", ""),
                "category": data.get("category", "прочее"),
                "amount": data.get("amount"),
                "kind": data.get("kind", "once"),
                "due_date": data.get("due_date"),
                "day_of_month": data.get("day_of_month"),
                "month_of_year": data.get("month_of_year"),
                "note": data.get("note", ""),
            },
        )
        or {}
    ).get("id")


def set_status(obligation_id: int, status: str) -> None:
    if status not in ("active", "done", "archived"):
        return
    db.execute("UPDATE obligations SET status = ? WHERE id = ?", (status, obligation_id))


def list_all() -> list[dict]:
    return db.query("SELECT * FROM obligations ORDER BY status, created_at DESC")
