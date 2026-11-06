"""«Второй мозг»: ответы на вопросы по документам и обязательствам."""
from __future__ import annotations

import logging
import re
from datetime import date

from . import db, documents, obligations
from .llm import llm

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — «второй мозг» пользователя: личный архив документов, платежей и заметок.
Отвечай по-русски, кратко и по делу, опираясь ТОЛЬКО на предоставленные данные
(фрагменты документов, список платежей и задач). Цитируй названия документов, из которых взят ответ.
Если данных недостаточно — честно скажи, что не нашёл информации, и подскажи, какой документ стоит загрузить.
Не выдумывай даты, суммы и реквизиты. Сегодня: {today}."""


def _facts_block(days: int = 90) -> str:
    """Структурированные факты: ближайшие платежи и открытые задачи."""
    lines: list[str] = []
    upcoming = obligations.upcoming(days=days)
    if upcoming:
        lines.append("БЛИЖАЙШИЕ ПЛАТЕЖИ И ОБЯЗАТЕЛЬСТВА:")
        for o in upcoming[:25]:
            amount = f" {o['amount']:g} {o.get('currency') or 'RUB'}" if o.get("amount") else ""
            kind = {"monthly": " (ежемесячно)", "yearly": " (ежегодно)"}.get(o["kind"], "")
            mark = " ⚠️ ПРОСРОЧЕНО," if o.get("overdue") else ""
            lines.append(f"- {o['title']}{kind}{amount} — {o['next_date']}{mark}")
            if o.get("note"):
                lines.append(f"    примечание: {o['note'][:160]}")
    tasks = db.query(
        "SELECT title, category, due_date FROM tasks WHERE status='open' "
        "ORDER BY due_date IS NULL, due_date LIMIT 25"
    )
    if tasks:
        lines.append("\nОТКРЫТЫЕ ЗАДАЧИ:")
        for t in tasks:
            due = f" (до {t['due_date']})" if t.get("due_date") else ""
            lines.append(f"- [{t['category']}] {t['title']}{due}")
    return "\n".join(lines)


async def ask(question: str) -> dict:
    """Отвечает на вопрос пользователя по его данным."""
    question = question.strip()
    if not question:
        return {"answer": "Задай вопрос — например: «когда платить за свет?»", "sources": []}

    chunks = documents.search(question, limit=12)
    sources = sorted({c["title"] for c in chunks})
    facts = _facts_block()

    context_parts = []
    if facts:
        context_parts.append(facts)
    if chunks:
        context_parts.append("ФРАГМЕНТЫ ДОКУМЕНТОВ:")
        for c in chunks:
            context_parts.append(f"--- документ «{c['title']}», фрагмент {c['idx'] + 1} ---\n{c['text'][:1200]}")
    context = "\n\n".join(context_parts) or "Данных пока нет: документы не загружены."

    if llm.available:
        answer = await llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT.format(today=date.today().isoformat())},
                {
                    "role": "user",
                    "content": f"ДАННЫЕ:\n{context[:14000]}\n\nВОПРОС: {question}",
                },
            ],
            temperature=0.2,
            max_tokens=900,
        )
        if answer:
            return {"answer": answer, "sources": sources}

    # Ответ без LLM: выдаём найденные факты и фрагменты
    lines: list[str] = []
    q_lower = question.lower()
    matched = [o for o in obligations.upcoming(days=365) if _words_hit(o["title"] + " " + (o.get("note") or ""), q_lower)]
    if matched:
        lines.append("Нашёл по твоим обязательствам:")
        for o in matched[:8]:
            amount = f", {o['amount']:g} {o.get('currency') or 'RUB'}" if o.get("amount") else ""
            lines.append(f"• {o['title']} — {o['next_date']}{amount}")
    if chunks:
        lines.append("\nФрагменты документов (LLM не подключён, показываю сырой поиск):")
        for c in chunks[:5]:
            lines.append(f"📄 «{c['title']}»: …{c['text'][:300].strip()}…")
    if not lines:
        lines.append(
            "Ничего не нашёл. Загрузи документ в Telegram-бот или на вкладке «Документы», "
            "а для свободных вопросов подключи LLM API-ключ в .env."
        )
    return {"answer": "\n".join(lines), "sources": sources}


SYNONYMS = {
    "свет": ["электроэнерг", "электр"],
    "света": ["электроэнерг", "электр"],
    "электричество": ["электроэнерг", "электр"],
    "жкх": ["коммуналь", "квартплат"],
    "осаго": ["страхов", "полис"],
    "каско": ["страхов", "полис"],
    "страховка": ["полис", "осаго", "каско"],
    "страховки": ["полис", "осаго", "каско"],
    "налог": ["фнс", "пошлин"],
    "аренда": ["найм", "квартир"],
    "аренды": ["найм", "квартир"],
    "телефон": ["мобильн", "связь"],
}


def _words_hit(haystack: str, question_lower: str) -> bool:
    h = haystack.lower()
    words = re.findall(r"[а-яa-z\-.]{3,}", question_lower)
    expanded = set(words)
    for w in words:
        expanded.update(SYNONYMS.get(w, []))
    return any(w in h for w in expanded)
