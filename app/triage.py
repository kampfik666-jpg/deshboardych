"""Умный диспетчер сообщений: понимает смысл (даже с опечатками/сленгом)
и раскладывает по категориям или отвечает на вопрос.

Пример: «посмотреть фильм Бронская история» → категория «Фильмы и сериалы».
"""
from __future__ import annotations

import logging

from . import brain, db, obligations
from .llm import llm

log = logging.getLogger(__name__)

# code -> (эмодзи, человекочитаемое название)
CATEGORIES: dict[str, tuple[str, str]] = {
    "inbox": ("📥", "Входящие"),
    "work": ("💼", "Работа"),
    "health": ("💊", "Здоровье"),
    "nastya": ("🎀", "Настюша"),
    "shopping": ("🛒", "Покупки"),
    "movies": ("🎬", "Фильмы и сериалы"),
    "games": ("🎮", "Игры"),
    "ideas": ("💡", "Идеи"),
    "notes": ("📝", "Заметки"),
    "payments": ("💳", "Платежи"),
}


def category_label(code: str) -> str:
    emoji, name = CATEGORIES.get(code, ("📥", code.title()))
    return f"{emoji} {name}"


TRIAGE_SYSTEM = (
    "Ты — диспетчер личного ассистента. Определяешь смысл сообщения пользователя "
    "и раскладываешь его по категориям. В одном сообщении может быть НЕСКОЛЬКО элементов — "
    "извлеки ВСЕ по отдельности. Учитывай расписание работы пользователя для планирования времени. "
    "Отвечай только валидным JSON."
)

TRIAGE_PROMPT = """Пойми смысл сообщения пользователя. Оно может быть с опечатками, сокращениями, \
сленгом, без знаков препинания, на смеси языков — всё равно определи суть.

ВАЖНО: в одном сообщении может быть НЕСКОЛЬКО фильмов/задач/покупок. Извлеки ВСЕ по отдельности!

РАСПИСАНИЕ РАБОТЫ ПОЛЬЗОВАТЕЛЯ:
{schedule}
Сегодня: {today} ({weekday})

Используй расписание чтобы определить КОНКРЕТНОЕ время задачи:
- «после работы» → если завтра работает до 20:00, поставь due_time="21:00"
- «утром перед работой» → если работает с 8:00, поставь due_time="07:00"
- «в обед» → поставь due_time="13:00"
- «вечером» → поставь due_time="19:00"
- «завтра» → due_date=завтрашний день, due_time определяется из контекста
- Если время не указано и нет привязки к расписанию → due_time=null

Реши, что это (поле intent):
- "question" — пользователь о чём-то СПРАШИВАЕТ и ждёт ответа.
- "capture" — пользователь хочет ЧТО-ТО ЗАПОМНИТЬ / записать. Может быть ОДИН элемент или НЕСКОЛЬКО.

Если intent="capture", для КАЖДОГО элемента определи категорию (category):
ПРИОРИТЕТ: если сообщение ЛЮБЫМ образом упоминает Настю/Настюшу/Анастасию (в любом падеже и написании: «настя», «настюша», «настюше», «настей», «настю», «анастасия», «анастасии») — ВЕСЬ элемент отправляется в категорию "nastya", даже если он похож на покупку, фильм, задачу или идею. Сначала проверяй упоминание имени, и только потом выбирай другую категорию.
- "inbox" — обычная задача/напоминание
- "work" — работа, проекты, встречи
- "health" — здоровье: врачи, лекарства, анализы
- "nastya" — всё, что касается Насти / Настюши (прогулки, подарки, дела, покупки, планы, здоровье)
- "shopping" — покупки: что купить/заказать
- "movies" — фильмы и сериалы
- "games" — игры
- "ideas" — идеи
- "payments" — платёж/обязательство с суммой или сроком
- "notes" — заметка/факт

Для каждого элемента извлеки:
- category: категория из списка выше
- title: чистый заголовок без вводных слов
- due_date: дата в формате ГГГГ-ММ-ДД (или null если не указана)
- due_time: время в формате ЧЧ:ММ (определи из контекста и расписания, или null)

Примеры:
- «завтра после работы купить гель для посуды» (завтра=2026-11-05, среда, работает до 20:00) → items:[{{"category":"shopping","title":"Купить гель для посуды","due_date":"2026-11-05","due_time":"21:00"}}]
- «сводить Настю в кафе где делают блинчики» → items:[{{"category":"nastya","title":"Сводить Настю в кафе с блинчиками","due_date":null,"due_time":null}}]
- «купить Насте подарок на день рождения» → items:[{{"category":"nastya","title":"Купить подарок на день рождения","due_date":null,"due_time":null}}]
- «посмотреть фильм Бронская история» → items:[{{"category":"movies","title":"Бронская история","due_date":null,"due_time":null}}]
- «когда платить за свет?» → intent:"question", items:[]

Верни ТОЛЬКО JSON:
{{"intent":"question" или "capture","items":[{{"category":"...","title":"...","due_date":"..." или null,"due_time":"..." или null}},...],"question_text":"..."}}

Если question — items пустой массив, вопрос в question_text.

СООБЩЕНИЕ: {text}"""


async def classify(text: str) -> dict:
    """Определяет intent + список элементов с учётом расписания. Работает и без LLM."""
    text = text.strip()

    # Строим контекст расписания для промпта
    from datetime import date as _date
    today = _date.today()
    weekday_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    schedule_lines = [
        "Пн: 8:00–14:00 (ЦГКБ №24, поликлиника №1)",
        "Вт: 14:00–20:00 (ЦГКБ №24, поликлиника №1)",
        "Ср: 14:00–20:00 (ЦГКБ №24, поликлиника №1)",
        "Чт: 8:00–14:00 (ЦГКБ №24, поликлиника №1)",
        "Пт: 14:00–20:00 (ЦГКБ №24, поликлиника №1)",
        "Сб: выходной",
        "Вс: выходной",
    ]
    schedule_text = "\n".join(schedule_lines)
    today_str = today.isoformat()
    weekday_str = weekday_names[today.weekday()]

    if llm.available:
        prompt = TRIAGE_PROMPT.format(
            text=text[:3000],
            schedule=schedule_text,
            today=today_str,
            weekday=weekday_str,
        )
        result = await llm.json(prompt, system=TRIAGE_SYSTEM)
        if isinstance(result, dict) and result.get("intent") in ("question", "capture"):
            items = []
            raw_items = result.get("items", [])
            if isinstance(raw_items, list):
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    cat = item.get("category", "inbox")
                    if cat not in CATEGORIES:
                        cat = "inbox"
                    title = str(item.get("title", "")).strip()[:300]
                    due_date = item.get("due_date")  # ГГГГ-ММ-ДД или null
                    due_time = item.get("due_time")  # ЧЧ:ММ или null
                    if title:
                        items.append({
                            "category": cat,
                            "title": title,
                            "due_date": due_date if isinstance(due_date, str) and len(due_date) == 10 else None,
                            "due_time": due_time if isinstance(due_time, str) and ":" in str(due_time) else None,
                        })
            # Fallback на старый формат
            if not items and result.get("category") and result.get("title"):
                cat = result["category"]
                if cat not in CATEGORIES:
                    cat = "inbox"
                items = [{"category": cat, "title": str(result["title"]).strip()[:300], "due_date": None, "due_time": None}]
            return {
                "intent": result["intent"],
                "items": items,
                "question_text": result.get("question_text", text),
                "engine": "llm",
            }
    return _fallback_classify(text)


async def capture(text: str) -> dict:
    """Главная точка входа: понимает сообщение и либо отвечает, либо сохраняет ВСЕ элементы."""
    text = (text or "").strip()
    if not text:
        return {"intent": "error", "message": "Пустое сообщение"}

    decision = await classify(text)

    if decision["intent"] == "question":
        q = decision.get("question_text", text)
        result = await brain.ask(q)
        return {
            "intent": "question",
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "engine": decision.get("engine"),
        }

    items = decision.get("items", [])
    if not items:
        # Fallback: один элемент из текста
        items = [{"category": "inbox", "title": text}]

    saved = []
    for item in items:
        category = item["category"]
        title = item["title"]
        due_date = item.get("due_date")
        due_time = item.get("due_time")
        emoji, label = CATEGORIES.get(category, CATEGORIES["inbox"])

        if category == "payments":
            found = await obligations.extract_from_document(None, text, title)
            if not found:
                obligations.add_manual({"title": title, "category": "платёж"})
            when = ""
            if found:
                first = found[0]
                nxt = first.get("due_date") or (
                    f"{first['day_of_month']}-го числа" if first.get("kind") == "monthly" else ""
                )
                if nxt:
                    when = f" · срок {nxt}"
            saved.append({"emoji": emoji, "label": label, "title": title, "when": when})
        else:
            task_id = db.execute(
                "INSERT INTO tasks(title, category, due_date, due_time, source, created_at) VALUES(?,?,?,?,?,?)",
                (title[:300], category, due_date, due_time, "capture", db.utcnow()),
            )
            time_note = f" · ⏰ {due_time}" if due_time else ""
            date_note = f" · 📅 {due_date}" if due_date else ""
            saved.append({"emoji": emoji, "label": label, "title": title, "saved_id": task_id, "when": f"{date_note}{time_note}"})

    return {
        "intent": "capture",
        "count": len(saved),
        "items": saved,
        "engine": decision.get("engine"),
    }


# ---------- Запасной классификатор без LLM ----------

_QUESTION_STARTS = (
    "когда", "сколько", "какой", "какая", "какое", "какие", "почему", "зачем",
    "где", "кто", "что ", "что?", "как ", "во сколько", "до какого", "до какого числа",
    "чем ", "зачем", "чей", "чья", "можно ли", "есть ли", "нужно ли",
)
_QUESTION_MARKS = ("?", "ли ")

_KEYWORDS = {
    "movies": ["фильм", "сериал", "кино", "мульт", "посмотреть", "погляжу", "глянуть", "аниме"],
    "games": ["игр", "поиграть", "steam", "playstation", "xbox", "гейм", "dota", "кс ", "counter"],
    "shopping": ["купить", "заказ", "покупк", "приобрет", "взять в магазине", "дозакуп"],
    "health": ["врач", "здоров", "лекар", "таблет", "анализ", "больниц", "стомат", "зуб",
               "аптек", "поликлиник", "трениров", "спорт"],
    "work": ["работ", "проект", "дедлайн", "совещан", "встреч", "началь", "офис", "клиент",
             "коллег", "презентац", "отчет", "отчёт"],
    "nastya": ["настя", "настюш", "настю"],
    "payments": ["заплат", "оплат", "платеж", "платёж", "квитанц", "жкх", "налог", "страхов",
                 "осаго", "каско", "ипотек", "кредит", "счет", "счёт", "пошлин", "за свет",
                 "за интернет", "за телефон", "коммунал"],
    "ideas": ["идея", "придум", "а что если", "хочу сделать", "концепт"],
    "notes": ["заметк", "запомни", "информ", "узнал", "на заметку"],
}


def _fallback_classify(text: str) -> dict:
    low = text.lower().strip()
    is_question = low.endswith("?") or low.startswith(_QUESTION_STARTS) or any(
        m in low for m in _QUESTION_MARKS
    )
    if is_question:
        return {"intent": "question", "items": [], "question_text": text, "engine": "fallback"}
    # Пробуем разбить на строки (список через переносы строк или запятые)
    lines = [l.strip().rstrip(",").strip() for l in text.replace(";", "\n").split("\n") if l.strip()]
    items = []
    for line in lines:
        line_low = line.lower()
        # Настя — приоритетная категория: упоминание имени важнее любого другого слова
        if any(w in line_low for w in _KEYWORDS["nastya"]):
            cat = "nastya"
        else:
            cat = "inbox"
            for c, words in _KEYWORDS.items():
                if c == "nastya":
                    continue
                if any(w in line_low for w in words):
                    cat = c
                    break
        # Убираем вводные слова
        title = line
        for prefix in ["посмотреть ", "купить ", "записать ", "добавить ", "надо ", "не забыть "]:
            if title.lower().startswith(prefix):
                title = title[len(prefix):].strip()
        if title:
            items.append({"category": cat, "title": title[:300]})
    if not items:
        items = [{"category": "inbox", "title": text[:300]}]
    return {"intent": "capture", "items": items, "engine": "fallback"}
