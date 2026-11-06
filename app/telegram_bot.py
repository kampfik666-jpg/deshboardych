"""Telegram-бот Life Hub: документы, вопросы, брифинг, задачи."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import brain, briefing, db, documents, obligations, sync as sync_mod, triage
from .config import settings

log = logging.getLogger(__name__)

MAX_FILE_SIZE = 19 * 1024 * 1024  # лимит Bot API на скачивание — 20 МБ


def is_allowed(update: Update) -> bool:
    owners = db.owner_ids()
    if not owners:
        return True  # режим первичной настройки — пускаем всех, /id покажет номер
    user = update.effective_user
    return bool(user and user.id in owners)


async def _auto_register_owner(update: Update) -> None:
    """Если владельцев нет — запоминает первого написавшего."""
    user = update.effective_user
    if not user:
        return
    if not db.owner_ids():
        db.add_owner(user.id)
        await update.effective_message.reply_text(
            f"✅ Запомнил тебя как владельца (ID {user.id}). "
            "Теперь только ты можешь управлять ботом и получать брифинги."
        )
    # Запоминаем имя для приветствий в дашборде и брифингах
    name = (user.first_name or "").strip()[:60]
    if name and db.get_setting("owner_name") != name:
        db.set_setting("owner_name", name)


async def _remember_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Фоновый обработчик (group=100): обновляет имя владельца на любом сообщении."""
    user = update.effective_user
    if not user:
        return
    if user.id in db.owner_ids():
        name = (user.first_name or "").strip()[:60]
        if name and db.get_setting("owner_name") != name:
            db.set_setting("owner_name", name)


async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "⛔ Доступ запрещён. Если это твой бот — добавь свой ID в TELEGRAM_CHAT_ID в .env."
    )


# ---------- команды ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    await _auto_register_owner(update)
    user = update.effective_user
    text = (
        f"Привет, {user.first_name}! Я — ДЭШБОРДЫЧЬ 🧠\n\n"
        "Что я умею:\n"
        "• ✨ Просто напиши мне что угодно — задачу, фильм, покупку, идею, платёж. "
        "Я пойму смысл (даже с опечатками) и сам положу в нужную категорию. "
        "Например: «посмотреть фильм Бронская история» → сохраню в «Фильмы и сериалы» 🎬\n"
        "• ❓ Или задай вопрос («когда платить за свет?») — отвечу по твоим документам\n"
        "• 📄 Пришли PDF/DOCX — найду в нём платежи и сроки\n"
        f"• ☀️ Каждое утро в {settings.briefing_time} присылаю брифинг на день\n\n"
        "Команды:\n"
        "/brief — брифинг сейчас\n"
        "/today — что на сегодня\n"
        "/tasks — все открытые записи\n"
        "/pay — ближайшие платежи\n"
        "/docs — последние документы\n"
        "/sync — обновить почту и календари\n"
        "/status — что подключено\n"
        "/help — эта справка"
    )
    await update.effective_message.reply_text(text)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await _auto_register_owner(update)
    owners = db.owner_ids()
    if user.id in owners:
        await update.effective_message.reply_text(
            f"Твой ID: {user.id} ✅ (уже запомнен как владелец)"
        )
    else:
        await update.effective_message.reply_text(
            f"Твой ID: {user.id}\nВпиши его в TELEGRAM_CHAT_ID в .env и перезапусти приложение."
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    sources = settings.enabled_sources()
    lines = ["📡 Статус подключений:", ""]
    lines.append(f"• LLM (второй мозг): {'✅ ' + settings.llm_model if settings.llm_available else '❌ не задан LLM_API_KEY — ответы только поиском'}")
    for name, cfg in sources.items():
        lines.append(f"• {cfg['label']}: ✅ {cfg['login']}")
    if not sources:
        lines.append("• Яндекс/Google: ❌ не подключены (см. .env)")
    counts = db.query_one(
        "SELECT (SELECT COUNT(*) FROM documents) AS docs, "
        "(SELECT COUNT(*) FROM obligations WHERE status='active') AS obl, "
        "(SELECT COUNT(*) FROM tasks WHERE status='open') AS tasks, "
        "(SELECT COUNT(*) FROM events) AS events, "
        "(SELECT COUNT(*) FROM mails) AS mails"
    )
    if counts:
        lines.append("")
        lines.append(
            f"📦 В базе: документов {counts['docs']}, обязательств {counts['obl']}, "
            f"задач {counts['tasks']}, событий {counts['events']}, писем {counts['mails']}"
        )
    last = sync_mod.last_sync_info()
    if last:
        lines.append("")
        lines.append("🔄 Последняя синхронизация:")
        for row in last:
            mark = "✅" if row["ok"] else "❌"
            lines.append(f"  {mark} {row['source']}/{row['kind']}: {(row['detail'] or '')[:60]}")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    msg = await update.effective_message.reply_text("☀️ Собираю брифинг…")
    try:
        text = await briefing.send_briefing()
    except Exception as exc:  # noqa: BLE001
        await msg.edit_text(f"Ошибка брифинга: {exc}")
        return
    # send_briefing уже отправил сообщение в чат(ы); если чат не в списке — просто ответим
    owners = db.owner_ids()
    if update.effective_chat.id not in owners:
        await msg.edit_text(text[:4000])
    else:
        await msg.delete()


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    today = datetime.now().astimezone().date()
    lines = [f"📆 Сегодня, {today.strftime('%d.%m.%Y')}:"]
    from .integrations import caldav_sync

    events = caldav_sync.events_for_day(today)
    if events:
        lines.append("\n📅 События:")
        for e in events:
            when = "весь день" if e["all_day"] else e["start_at"][11:16]
            lines.append(f"  • {when} — {e['title']}")
    due = obligations.upcoming(days=3)
    if due:
        lines.append("\n💰 Платежи:")
        for o in due[:10]:
            lines.append(f"  • {o['next_date']}: {o['title']}")
    tasks = db.query(
        "SELECT * FROM tasks WHERE status='open' AND due_date IS NOT NULL AND due_date <= ? "
        "ORDER BY due_date LIMIT 10",
        (today.isoformat(),),
    )
    if tasks:
        lines.append("\n✅ Задачи:")
        for t in tasks:
            lines.append(f"  • {t['title']} (до {t['due_date']})")
    if len(lines) == 1:
        lines.append("Ничего не запланировано — свободный день 🎉")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_pay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    items = obligations.upcoming(days=45)
    if not items:
        await update.effective_message.reply_text(
            "Платежей не знаю. Загрузи квитанции и договоры — найду сроки сам."
        )
        return
    lines = ["💳 Ближайшие платежи:"]
    for o in items[:20]:
        amount = f" — {o['amount']:g} {o.get('currency') or 'RUB'}" if o.get("amount") else ""
        mark = "⚠️ " if o.get("overdue") else ""
        lines.append(f"  • {mark}{o['next_date']}: {o['title']}{amount}")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    tasks = db.query(
        "SELECT * FROM tasks WHERE status='open' ORDER BY category, due_date IS NULL, due_date, id LIMIT 60"
    )
    if not tasks:
        await update.effective_message.reply_text("Открытых записей нет.")
        return
    lines = ["📋 Твои записи по категориям:"]
    current_cat = None
    for t in tasks:
        if t["category"] != current_cat:
            current_cat = t["category"]
            lines.append(f"\n{triage.category_label(current_cat)}:")
        due = f" (до {t['due_date']})" if t.get("due_date") else ""
        lines.append(f"  • #{t['id']} {t['title']}{due}")
    lines.append("\nОтметь выполнение: /done <номер>")
    await update.effective_message.reply_text("\n".join(lines)[:4000])


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    text = " ".join(context.args or []).strip()
    if not text:
        await update.effective_message.reply_text("Использование: /add Купить лампочку 2026-11-10")
        return
    due = None
    parts = text.rsplit(" ", 1)
    if len(parts) == 2:
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                due = datetime.strptime(parts[1], fmt).date().isoformat()
                text = parts[0]
                break
            except ValueError:
                continue
    word = text.split(" ", 1)[0].lower().rstrip(":")
    category = "inbox"
    mapping = {"задача": "inbox", "работа": "work", "здоровье": "health", "настя": "nastya"}
    if word in mapping and " " in text:
        category = mapping[word]
        text = text.split(" ", 1)[1]
    db.execute(
        "INSERT INTO tasks(title, category, due_date, source, created_at) VALUES(?,?,?,?,?)",
        (text[:300], category, due, "telegram", db.utcnow()),
    )
    when = f" до {due}" if due else ""
    await update.effective_message.reply_text(f"➕ Задача добавлена{when}: {text}")


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    if not context.args or not context.args[0].lstrip("#").isdigit():
        await update.effective_message.reply_text("Использование: /done 12")
        return
    task_id = int(context.args[0].lstrip("#"))
    row = db.query_one("SELECT * FROM tasks WHERE id = ? AND status='open'", (task_id,))
    if not row:
        await update.effective_message.reply_text(f"Открытая задача #{task_id} не найдена.")
        return
    db.execute(
        "UPDATE tasks SET status='done', completed_at=? WHERE id=?", (db.utcnow(), task_id)
    )
    await update.effective_message.reply_text(f"🎉 Готово: {row['title']}")


async def cmd_docs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    docs = documents.list_documents(limit=10)
    if not docs:
        await update.effective_message.reply_text(
            "Документов пока нет. Просто пришли мне PDF — я его запомню."
        )
        return
    lines = ["📄 Последние документы:"]
    for d in docs:
        obl = f", платежей: {d['obligations_count']}" if d["obligations_count"] else ""
        created = d["created_at"][:10]
        lines.append(f"  • {d['title']} ({created}{obl})")
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    msg = await update.effective_message.reply_text("🔄 Синхронизирую сервисы…")
    result = await sync_mod.sync_all()
    lines = []
    if isinstance(result, dict) and "message" in result:
        lines.append(result["message"])
    else:
        sources = settings.enabled_sources()
        for name, entry in result.items():
            label = sources.get(name, {}).get("label", name)
            ev = entry.get("events", 0)
            ev_err = entry.get("events_error")
            ml = entry.get("mails", 0)
            ml_err = entry.get("mails_error")
            lines.append(f"{label}: календарь {'✅ ' + str(ev) if not ev_err else '❌ ' + ev_err[:60]}")
            lines.append(f"{label}: почта {'✅ ' + str(ml) if not ml_err else '❌ ' + ml_err[:60]}")
    await msg.edit_text("\n".join(lines) or "Готово.")


# ---------- документы ----------

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    doc = update.message.document
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await update.effective_message.reply_text("Файл больше 20 МБ — не скачаю. Раздели или сожми.")
        return
    msg = await update.effective_message.reply_text("📥 Читаю документ…")
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        data = await tg_file.download_as_bytearray()
        result = await documents.add_document(
            doc.file_name or "document", bytes(data), source="telegram"
        )
    except documents.UnsupportedDocument as exc:
        await msg.edit_text(f"⚠️ {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("Document ingestion failed")
        await msg.edit_text(f"Ошибка обработки: {exc}")
        return

    if result.get("duplicate"):
        await msg.edit_text(f"♻️ Этот документ уже сохранён: «{result['title']}».")
        return
    lines = [
        f"✅ Сохранил «{result['title']}» "
        f"({result['char_count']} символов, {result['chunks']} фрагментов)."
    ]
    found = result.get("obligations") or []
    if found:
        lines.append("\nНашёл обязательства:")
        for o in found[:10]:
            when = o.get("due_date") or (
                f"ежемесячно, {o['day_of_month']}-го" if o.get("day_of_month") and o.get("kind") == "monthly"
                else f"ежегодно" if o.get("kind") == "yearly" else "без точной даты"
            )
            amount = f", {o['amount']:g} {o.get('currency') or 'RUB'}" if o.get("amount") else ""
            lines.append(f"  • {o['title']} — {when}{amount}")
        lines.append("\nТеперь можно спросить: «когда платить …?»")
    else:
        lines.append("Платежей и сроков в нём не нашёл, но документ в поиске.")
    await msg.edit_text("\n".join(lines)[:4000])


# ---------- фото — распознавание через vision-модель ----------

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    photo = update.message.photo[-1]  # самое большое разрешение
    if photo.file_size and photo.file_size > MAX_FILE_SIZE:
        await update.effective_message.reply_text("Фото слишком большое — не скачаю.")
        return
    msg = await update.effective_message.reply_text("👁 Распознаю изображение…")
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        data = await tg_file.download_as_bytearray()
        caption = (update.message.caption or "").strip()
        filename = f"фото_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        result = await documents.add_document(filename, bytes(data), source="telegram")
    except Exception as exc:  # noqa: BLE001
        log.exception("Photo ingestion failed")
        await msg.edit_text(f"Ошибка обработки: {exc}")
        return

    if result.get("duplicate"):
        await msg.edit_text(f"♻️ Это фото уже сохранено: «{result['title']}».")
        return

    lines = [f"✅ Фото распознано и сохранено ({result.get('char_count', 0)} символов текста)."]
    if caption:
        lines.append(f"💬 Подпись: {caption}")
    found = result.get("obligations") or []
    if found:
        lines.append("\nНашёл обязательства:")
        for o in found[:10]:
            when = o.get("due_date") or (f"ежемесячно {o['day_of_month']}-го" if o.get("kind") == "monthly" and o.get("day_of_month") else "")
            amount = f", {o['amount']:g} {o.get('currency') or 'RUB'}" if o.get("amount") else ""
            lines.append(f"  • {o['title']} — {when}{amount}")
    lines.append("\nТеперь это фото можно найти через поиск и спросить про него.")
    await msg.edit_text("\n".join(lines)[:4000])


# ---------- свободный текст / голос = умный захват ----------

async def _respond_capture(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, prefix: str = "") -> None:
    """Прогоняет текст через triage.capture и красиво отвечает."""
    try:
        result = await asyncio.wait_for(triage.capture(text), timeout=120)
    except asyncio.TimeoutError:
        await update.effective_message.reply_text("⏳ Думаю слишком долго — попробуй ещё раз.")
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("Capture failed")
        await update.effective_message.reply_text(f"Ошибка: {exc}")
        return

    if result.get("intent") == "question":
        answer = prefix + result.get("answer", "")
        if result.get("sources"):
            answer += "\n\n📚 Источники: " + ", ".join(result["sources"][:5])
        for i in range(0, len(answer), 4000):
            await update.effective_message.reply_text(answer[i : i + 4000])
        return

    if result.get("intent") == "capture":
        items = result.get("items", [])
        engine_note = "" if result.get("engine") == "llm" else " (распознано без нейросети)"
        if len(items) == 1:
            it = items[0]
            when = it.get("when", "")
            await update.effective_message.reply_text(
                f"{prefix}{it['emoji']} Понял! Сохранил в «{it['label']}»:\n<b>{it['title']}</b>{when}{engine_note}",
                parse_mode="HTML",
            )
        else:
            lines = [f"{prefix}✅ Добавил <b>{len(items)}</b> записей:{engine_note}"]
            for it in items:
                when = it.get("when", "")
                lines.append(f"  {it['emoji']} <b>{it['title']}</b> → {it['label']}{when}")
            await update.effective_message.reply_text("\n".join(lines)[:4000], parse_mode="HTML")
        return

    await update.effective_message.reply_text("Не понял — попробуй переформулировать 🙂")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return await deny(update, context)
    text = (update.message.text or "").strip()
    if not text:
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    await _respond_capture(update, context, text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Голосовое сообщение → офлайн-распознавание (Vosk) → умный захват."""
    if not is_allowed(update):
        return await deny(update, context)
    voice = update.message.voice
    if voice.duration and voice.duration > 180:
        await update.effective_message.reply_text("🎙 Слишком длинное голосовое (макс. 3 минуты).")
        return

    msg = await update.effective_message.reply_text("🎙 Слушаю… (распознаю офлайн)")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        tg_file = await context.bot.get_file(voice.file_id)
        data = await tg_file.download_as_bytearray()
    except Exception as exc:  # noqa: BLE001
        await msg.edit_text(f"Не удалось скачать голосовое: {exc}")
        return

    from . import voice as voice_stt

    try:
        text = await asyncio.to_thread(voice_stt.transcribe, bytes(data))
    except Exception as exc:  # noqa: BLE001
        log.exception("Voice transcription failed")
        await msg.edit_text(f"Ошибка распознавания: {exc}")
        return

    if not text:
        await msg.edit_text("🤷 Не разобрал ни слова — попробуй записать чётче или напиши текстом.")
        return

    await msg.edit_text(f"🎙 Услышал: «{text}»\n\nОбрабатываю…")
    await _respond_capture(update, context, text, prefix=f"🎙 «{text}»\n\n")
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001
        pass


def build_application() -> Application | None:
    if not settings.bot_available:
        log.warning("BOT_TOKEN не задан — Telegram-бот не запущен.")
        return None
    app = Application.builder().token(settings.bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("docs", cmd_docs))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # В отдельной группе: запоминает имя владельца на любом сообщении
    app.add_handler(MessageHandler(filters.ALL, _remember_owner), group=100)
    return app
