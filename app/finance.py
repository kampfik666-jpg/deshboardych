"""Финансы: учёт расходов, статистика, напоминания о платежах."""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime, timedelta

from . import db

log = logging.getLogger(__name__)

# Категории расходов для автоклассификации (обогащено по реальной выписке Сбера)
EXPENSE_CATEGORIES = {
    "здоровье": ["аптек", "apteka", "apteki", "aptechnyj", "лекарств", "клиник",
                 "больниц", "стомат", "анализ", "magnit ma apteka"],
    "продукты": ["пятёрочка", "пятерочка", "pyaterochka", "магнит", "magnit",
                 "дикси", "вкусвилл", "перекре", "perekrest", "самокат", "samokat",
                 "лавка", "edarit", "kuper", "сбермаркет", "ozon fresh", "fixprice",
                 "krasnoe&beloe", "красное", "жизньмарт", "супермаркет",
                 "kirovskij", "кировский", "krasnolesye", "краснолесь",
                 "dostavka iz pyaterochki", "tore", "продукт",
                 "торо bravo", "badenlend", "toroid", "ks park"],
    "еда вне дома": ["dodo", "додо", "итальян пицца", "буфет", "bufet", "столовая",
                     "stolovaya", "кофейня", "kofejnya", "bow jones", "rest megamart",
                     "главборщ", "karavaj", "карав", "vilka-lozhka", "вилка-ложка",
                     "restaurant", "ресторан", "кафе", "kfc", "бургер", "burger",
                     "макдоналдс", "mcdonald", "delivery club", "яндекс еда",
                     "yandex*5814*eda", "юмвенд", "пицц", "coffee", "кофе",
                     "sushkof", "сушкоф", "toro", "toro bravo"],
    "транспорт": ["bilet.nspk", "nspk", "metro biometriya", "biometriya", "яндекс го",
                  "yandex*4121*go", "yandex*4121*fasten", "fasten", "yandex go",
                  "go_runcharge", "runcharge", "такси", "taxi", "uber", "ситимобил",
                  "ситидрайв", "метро", "автобус", "трамвай", "электричк", "бензин",
                  "азс", "заправк", "топлив", "парковк", "оплата проезда",
                  "yandex*4215*dostavka", "whoosh", "вуш"],
    "жкх": ["жкх", "коммунал", "электроэнерг", "вода", "отоплен", "управляющ",
            "тсж", "домофон", "росводоканал", "енрц", "ерц", "газ", "квартплат"],
    "связь и подписки": ["vanyavpn", "vpn", "podpiska paket", "подписка пакет",
                        "yandex*5815*plus", "netflix", "ivi", "okko", "kinopoisk",
                        "мтс", "билайн", "мегафон", "теле2", "yota", "ростелеком",
                        "дом.ру", "интернет", "мобильн"],
    "онлайн-шопинг": ["wildberries", "wb*", "озон", "aliexpress", "joom", "lamoda",
                      "мегамаркет", "sbermegamarket", "яндекс маркет", "market"],
    "одежда и обувь": ["familia", "shankhaj", "шанхай", "zara", "uniqlo", "h&m",
                       "одежд", "обувь", "reserved", "спортмастер", "zenden"],
    "техника": ["dns", "ammont", "mvideo", "мвидео", "eldorado", "ситилинк",
                "technopark", "технопарк", "электрон"],
    "развлечения": ["кино", "театр", "музей", "концерт", "steam", "playstation",
                    "xbox", "plati.market", "игр", "rose mix", "цветы"],
    "вредные привычки": ["табак", "tabak", "vape", "вейп", "сигарет"],
    "образование": ["курс", "обучен", "книг", "учебн", "skillbox", "geekbrains"],
    "кредиты": ["karta-credit", "карта-кредит", "кредит", "ипотек", "рассрочк",
                "yandex*5262*split", "split", "райффайзен", "raiffeisen",
                "mapp_sberbank_onl@in_pay", "mapp_sberbank", "in_pay",
                "эво_орехи", "evo_orekhi", "кб локо-банк", "локо-банк"],
    "налоги и штрафы": ["налог", "фнс", "пошлин", "гибдд", "штраф"],
    "переводы": ["перевод для", "перевод сбп", "перевод с карты", "sbol перевод",
                 "перевод на платежный", "перевод между"],
}

# Доходы и операции которые не являются расходами
INCOME_PATTERNS = [
    "заработная плата", "аванс по заработной", "премия", "перевод от", "зачислен",
    "внесение наличных", "возврат", "проценты на остаток", "кэшбэк", "кешбек",
    "выплата", "стипендия", "больничн", "выдача наличных", "поощрительные",
    "прочие выплаты",
]


def classify_expense(description: str) -> str:
    """Автоклассификация расхода по описанию (keyword-based fallback)."""
    low = description.lower()
    for cat, keywords in EXPENSE_CATEGORIES.items():
        if any(kw in low for kw in keywords):
            return cat
    return "прочее"


async def classify_expense_llm(description: str) -> str:
    """Классификация расхода через LLM для точности."""
    from .llm import llm
    if not llm.available:
        return classify_expense(description)

    cats = ", ".join(EXPENSE_CATEGORIES.keys())
    prompt = f"""Определи категорию расхода по описанию. Выбери ОДНУ из: {cats}, прочее.
Верни ТОЛЬКО название категории, без пояснений.

Описание: {description[:200]}"""

    result = await llm.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=30, temperature=0.1,
    )
    if result:
        clean = result.strip().lower().strip('"').strip("'")
        if clean in EXPENSE_CATEGORIES:
            return clean
    return classify_expense(description)  # fallback


def init_finance_schema():
    """Создаёт таблицы для финансов если их нет."""
    from .db import IS_POSTGRES
    if IS_POSTGRES:
        statements = [
            "CREATE TABLE IF NOT EXISTS expenses (id SERIAL PRIMARY KEY, date TEXT NOT NULL, amount REAL NOT NULL, category TEXT NOT NULL DEFAULT 'прочее', description TEXT, source TEXT DEFAULT 'manual', created_at TEXT NOT NULL)",
            "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)",
            "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)",
        ]
        with db.db() as conn:
            for stmt in statements:
                conn.execute(stmt)
    else:
        with db.db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL DEFAULT 'прочее',
                    description TEXT,
                    source TEXT DEFAULT 'manual',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
                CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
            """)


def add_expense(expense_date: str, amount: float, description: str,
                category: str | None = None, source: str = "manual") -> int:
    """Добавляет расход."""
    if category is None:
        category = classify_expense(description)
    return db.execute(
        "INSERT INTO expenses(date, amount, category, description, source, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (expense_date, abs(amount), category, description[:500], source, db.utcnow()),
    )


def parse_sber_csv(data: bytes, encoding: str = "utf-8") -> list[dict]:
    """Парсит CSV-выписку Сбербанка. Поддерживает разные форматы."""
    text = data.decode(encoding, errors="replace")
    # Убираем BOM
    if text.startswith("\ufeff"):
        text = text[1:]

    reader = csv.reader(io.StringIO(text), delimiter=";")
    rows = list(reader)

    expenses = []
    header_found = False
    date_col = amount_col = desc_col = -1

    for row in rows:
        if not row or all(not c.strip() for c in row):
            continue
        # Ищем заголовок
        if not header_found:
            low_row = [c.lower().strip() for c in row]
            for i, col in enumerate(low_row):
                if "дата" in col:
                    date_col = i
                elif "сумм" in col and ("списан" in col or "расход" in col or "операци" in col):
                    amount_col = i
                elif "сумм" in col and amount_col < 0:
                    amount_col = i
                elif "описан" in col or "назначен" in col or "получатель" in col:
                    desc_col = i
            if date_col >= 0 and amount_col >= 0:
                header_found = True
            continue

        # Парсим строку данных
        try:
            raw_date = row[date_col].strip() if date_col < len(row) else ""
            raw_amount = row[amount_col].strip() if amount_col < len(row) else ""
            raw_desc = row[desc_col].strip() if desc_col >= 0 and desc_col < len(row) else ""

            if not raw_date or not raw_amount:
                continue

            # Парсим дату (форматы: ДД.ММ.ГГГГ или ГГГГ-ММ-ДД)
            parsed_date = None
            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).date().isoformat()
                    break
                except ValueError:
                    continue
            if not parsed_date:
                continue

            # Парсим сумму
            amount_str = raw_amount.replace(" ", "").replace(",", ".").replace("₽", "").replace("руб", "")
            amount = float(amount_str)
            if amount == 0:
                continue

            expenses.append({
                "date": parsed_date,
                "amount": abs(amount),
                "description": raw_desc or "Без описания",
            })
        except (ValueError, IndexError):
            continue

    return expenses


def get_stats(months: int = 12) -> dict:
    """Статистика расходов за N месяцев (исключая переводы между своими счетами)."""
    since = (date.today() - timedelta(days=months * 30)).isoformat()

    # По категориям (без переводов)
    by_cat = db.query(
        "SELECT category, SUM(amount) as total, COUNT(*) as count "
        "FROM expenses WHERE date >= ? AND category != 'переводы' "
        "GROUP BY category ORDER BY total DESC",
        (since,),
    )

    # По месяцам (без переводов)
    by_month = db.query(
        "SELECT substr(date, 1, 7) as month, SUM(amount) as total, COUNT(*) as count "
        "FROM expenses WHERE date >= ? AND category != 'переводы' "
        "GROUP BY month ORDER BY month",
        (since,),
    )

    # Общая сумма (без переводов)
    total = db.query_one(
        "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date >= ? AND category != 'переводы'",
        (since,),
    )["total"]

    # Топ расходов (без переводов)
    top = db.query(
        "SELECT description, amount, date, category FROM expenses "
        "WHERE date >= ? AND category != 'переводы' ORDER BY amount DESC LIMIT 10",
        (since,),
    )

    return {
        "period_months": months,
        "total": total,
        "by_category": by_cat,
        "by_month": by_month,
        "top_expenses": top,
    }


def upcoming_payment_reminders() -> list[dict]:
    """Платежи с напоминаниями: за 3 дня до срока и каждый день до оплаты."""
    today = date.today()
    horizon = today + timedelta(days=30)
    from . import obligations
    all_upcoming = obligations.upcoming(days=30)

    reminders = []
    for obl in all_upcoming:
        try:
            due = date.fromisoformat(obl["next_date"])
        except (ValueError, TypeError):
            continue
        days_left = (due - today).days
        if days_left <= 3 and obl.get("status") == "active":
            urgency = "⚠️ СРОЧНО" if days_left <= 0 else f"через {days_left} дн."
            reminders.append({
                "title": obl["title"],
                "due_date": obl["next_date"],
                "days_left": days_left,
                "amount": obl.get("amount"),
                "currency": obl.get("currency", "RUB"),
                "urgency": urgency,
            })
    reminders.sort(key=lambda r: r["days_left"])
    return reminders
