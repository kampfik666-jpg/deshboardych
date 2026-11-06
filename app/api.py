"""FastAPI: JSON API + статика веб-дашборда."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import bank_parser, brain, briefing, db, documents, finance, habits, mail_filter, obligations, sync as sync_mod, triage
from .config import settings
from .integrations import caldav_sync, imap_sync

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

api = FastAPI(title="Life Hub", version="0.1.0")


class TaskIn(BaseModel):
    title: str
    category: str = "inbox"
    due_date: str | None = None


class ObligationIn(BaseModel):
    title: str
    category: str = "прочее"
    amount: float | None = None
    currency: str = "RUB"
    kind: str = "once"
    due_date: str | None = None
    day_of_month: int | None = None
    month_of_year: int | None = None
    note: str = ""


class AskIn(BaseModel):
    question: str


class CaptureIn(BaseModel):
    text: str


@api.get("/api/status")
async def get_status():
    sources = settings.enabled_sources()
    counts = db.query_one(
        "SELECT (SELECT COUNT(*) FROM documents) AS docs, "
        "(SELECT COUNT(*) FROM obligations WHERE status='active') AS obligations, "
        "(SELECT COUNT(*) FROM tasks WHERE status='open') AS tasks, "
        "(SELECT COUNT(*) FROM events) AS events, "
        "(SELECT COUNT(*) FROM mails) AS mails"
    )
    return {
        "llm": {
            "available": settings.llm_available,
            "model": settings.llm_model if settings.llm_available else None,
        },
        "telegram_bot": settings.bot_available,
        "briefing_time": settings.briefing_time,
        "timezone": settings.timezone,
        "sources": [
            {"name": k, "label": v["label"], "login": v["login"]} for k, v in sources.items()
        ],
        "last_sync": sync_mod.last_sync_info(),
        "counts": counts or {},
    }


@api.get("/api/today")
async def get_today():
    today = datetime.now().astimezone().date()
    facts = briefing.collect_facts(today)
    weather = await briefing.fetch_weather()
    latest = briefing.latest_briefing()
    return {
        "date": today.isoformat(),
        "owner_name": db.get_setting("owner_name", ""),
        "weather": weather,
        "events": facts["events"],
        "tomorrow_events": facts["tomorrow_events"],
        "payments": facts["payments"],
        "due_tasks": facts["due_today"],
        "open_tasks": facts["without_date"],
        "next_tasks": facts["next_tasks"],
        "mails": facts["mails"],
        "unread": facts["unread"],
        "last_briefing": latest,
    }


@api.get("/api/events")
async def get_events(days: int = 14):
    events = caldav_sync.upcoming_events(days=min(days, 90))
    # группируем по дням
    grouped: dict[str, list] = {}
    for e in events:
        day = e["start_at"][:10]
        grouped.setdefault(day, []).append(e)
    return {"days": [{"date": d, "events": evs} for d, evs in sorted(grouped.items())]}


@api.get("/api/mails")
async def get_mails(limit: int = 50, unread_only: bool = False, show_spam: bool = False):
    raw = imap_sync.recent_mails(limit=min(limit, 200), unread_only=unread_only)
    result = mail_filter.filter_mails(raw, show_spam=show_spam)
    return {
        "mails": result["clean"],
        "spam_count": result["spam_count"],
        "total": result["total"],
        "spam": result.get("spam", []),
    }


@api.get("/api/mail-filters")
async def get_mail_filters():
    return {"filters": mail_filter.get_all_filters()}


class MailFilterIn(BaseModel):
    kind: str = "sender"
    pattern: str
    action: str = "hide"
    label: str = ""


@api.post("/api/mail-filters")
async def add_mail_filter(data: MailFilterIn):
    fid = mail_filter.add_filter(data.kind, data.pattern, data.action, data.label)
    return {"id": fid}


@api.delete("/api/mail-filters/{filter_id}")
async def delete_mail_filter(filter_id: int):
    mail_filter.remove_filter(filter_id)
    return {"ok": True}


# ==================== ФИНАНСЫ ====================

@api.get("/api/finance/stats")
async def finance_stats(months: int = 6):
    """Статистика расходов за N месяцев."""
    return finance.get_stats(months=months)


@api.get("/api/finance/reminders")
async def finance_reminders():
    """Напоминания о ближайших платежах (за 3 дня и каждый день до оплаты)."""
    return {"reminders": finance.upcoming_payment_reminders()}


class ExpenseIn(BaseModel):
    date: str | None = None
    amount: float
    description: str
    category: str | None = None


@api.post("/api/finance/expenses")
async def add_expense(data: ExpenseIn):
    """Ручное добавление расхода."""
    exp_date = data.date or datetime.now().astimezone().date().isoformat()
    eid = finance.add_expense(
        expense_date=exp_date,
        amount=data.amount,
        description=data.description,
        category=data.category,
        source="manual",
    )
    return {"id": eid}


@api.post("/api/finance/scan-mails")
async def scan_bank_emails():
    """Сканирует почту на предмет банковских уведомлений и извлекает расходы."""
    mails = imap_sync.recent_mails(limit=200, unread_only=False)
    found = bank_parser.scan_mails_for_expenses(mails)
    return {"found": len(found), "expenses": found}


@api.post("/api/finance/upload-csv")
async def upload_bank_csv(file: UploadFile = File(...)):
    """Загрузка CSV-выписки банка с автокатегоризацией через LLM."""
    data = await file.read()
    expenses = finance.parse_sber_csv(data)
    added = 0
    for exp in expenses:
        existing = db.query_one(
            "SELECT id FROM expenses WHERE date = ? AND amount = ? LIMIT 1",
            (exp["date"], exp["amount"]),
        )
        if not existing:
            # Автокатегоризация через LLM для точности
            category = await finance.classify_expense_llm(exp["description"])
            finance.add_expense(
                expense_date=exp["date"],
                amount=exp["amount"],
                description=exp["description"],
                category=category,
                source="csv_import",
            )
            added += 1
    return {"parsed": len(expenses), "added": added, "duplicates_skipped": len(expenses) - added}


# ==================== ПРИВЫЧКИ ====================

@api.get("/api/habits")
async def get_habits(days: int = 7):
    return habits.get_dashboard(days=days)


class HabitIn(BaseModel):
    name: str
    type: str = "good"
    emoji: str = "⭐"


@api.post("/api/habits")
async def add_habit(data: HabitIn):
    hid = habits.add_habit(data.name, data.type, data.emoji)
    return {"id": hid}


@api.delete("/api/habits/{habit_id}")
async def delete_habit(habit_id: int):
    habits.delete_habit(habit_id)
    return {"ok": True}


class HabitRename(BaseModel):
    name: str
    emoji: str | None = None


@api.put("/api/habits/{habit_id}")
async def rename_habit(habit_id: int, data: HabitRename):
    habits.rename_habit(habit_id, data.name, data.emoji)
    return {"ok": True}


class HabitMarkIn(BaseModel):
    day: str
    done: bool


@api.post("/api/habits/{habit_id}/mark")
async def set_habit_mark(habit_id: int, data: HabitMarkIn):
    habits.set_mark(habit_id, data.day, data.done)
    return {"ok": True}


@api.post("/api/habits/{habit_id}/toggle")
async def toggle_habit_mark(habit_id: int, day: str = Body(..., embed=True)):
    new_val = habits.toggle_mark(habit_id, day)
    return {"done": new_val}


@api.get("/api/habits/weekly-stats")
async def weekly_habit_stats():
    return habits.weekly_stats()


@api.get("/api/tasks")
async def get_tasks(show_done: bool = False):
    where = "" if show_done else "WHERE status = 'open'"
    tasks = db.query(
        f"SELECT * FROM tasks {where} "
        "ORDER BY status, due_date IS NULL, due_date, id LIMIT 300"
    )
    # Добавляем edit_url для каждой задачи чтобы фронтенд мог рендерить кнопки
    for t in tasks:
        t["edit_url"] = f"/api/tasks/{t['id']}"
    return {"tasks": tasks}


@api.get("/api/tasks/{task_id}/edit-page")
async def task_edit_page(task_id: int):
    """Возвращает HTML-страницу редактирования задачи (не кэшируется)."""
    from fastapi.responses import HTMLResponse
    row = db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not row:
        raise HTTPException(404, "Задача не найдена")
    cats = ["inbox","work","health","nastya","shopping","movies","games","ideas","notes"]
    cat_options = "".join(
        f'<option value="{c}" {"selected" if c == row["category"] else ""}>{c}</option>'
        for c in cats
    )
    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Редактировать задачу #{task_id}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f4f5f8;padding:40px;margin:0}}
.card{{background:#fff;border-radius:16px;padding:24px;max-width:500px;margin:0 auto;box-shadow:0 4px 20px rgba(0,0,0,.04)}}
h2{{margin:0 0 20px;font-size:18px}}
label{{display:block;font-size:13px;color:#6b7280;margin:12px 0 4px}}
input,select{{width:100%;padding:10px 13px;border:1px solid #eceef2;border-radius:10px;font-size:14px;box-sizing:border-box}}
input:focus,select:focus{{outline:none;border-color:#5850ec;box-shadow:0 0 0 3px #eef2ff}}
.btns{{display:flex;gap:10px;margin-top:20px}}
button{{padding:10px 20px;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer}}
.save{{background:#5850ec;color:#fff}} .save:hover{{filter:brightness(1.1)}}
.cancel{{background:#eef2ff;color:#5850ec}} .cancel:hover{{background:#e0e5ff}}
.delete{{background:#fdeaea;color:#ef4444;margin-left:auto}} .delete:hover{{background:#fbdada}}
.msg{{margin-top:12px;font-size:13px;padding:8px 12px;border-radius:8px;display:none}}
.ok{{background:#e3f7ef;color:#047857;display:block}} .err{{background:#fdeaea;color:#ef4444;display:block}}
</style></head><body>
<div class="card">
<h2>✏️ Редактировать задачу #{task_id}</h2>
<label>Заголовок</label>
<input type="text" id="title" value="{row['title'].replace('"','&quot;')}">
<label>Категория</label>
<select id="category">{cat_options}</select>
<label>Дата (необязательно)</label>
<input type="date" id="due_date" value="{row['due_date'] or ''}">
<label>Время (необязательно)</label>
<input type="time" id="due_time" value="{row['due_time'] or ''}">
<div class="btns">
<button class="save" onclick="doSave()">💾 Сохранить</button>
<button class="cancel" onclick="window.close();history.back()">Отмена</button>
<button class="delete" onclick="doDelete()">🗑 Удалить</button>
</div>
<div id="msg" class="msg"></div>
</div>
<script>
function doSave(){{
  var d={{title:document.getElementById('title').value,category:document.getElementById('category').value,
    due_date:document.getElementById('due_date').value||null,due_time:document.getElementById('due_time').value||null}};
  fetch('/api/tasks/{task_id}',{{method:'PUT',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(d)}})
  .then(function(r){{if(r.ok){{var m=document.getElementById('msg');m.className='msg ok';m.textContent='✅ Сохранено!';
    setTimeout(function(){{window.close();location.href='/';}},800)}}else{{r.json().then(function(j){{
    var m=document.getElementById('msg');m.className='msg err';m.textContent='❌ '+j.detail}})}}}});
}}
function doDelete(){{
  if(!confirm('Удалить задачу?'))return;
  fetch('/api/tasks/{task_id}',{{method:'DELETE'}}).then(function(r){{if(r.ok){{location.href='/'}}}});
}}
</script></body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store"})


@api.post("/api/tasks")
async def add_task(task: TaskIn):
    if not task.title.strip():
        raise HTTPException(400, "Пустая задача")
    task_id = db.execute(
        "INSERT INTO tasks(title, category, due_date, source, created_at) VALUES(?,?,?,?,?)",
        (task.title.strip()[:300], task.category or "inbox", task.due_date, "web", db.utcnow()),
    )
    return {"id": task_id}


@api.post("/api/tasks/{task_id}/toggle")
async def toggle_task(task_id: int):
    row = db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not row:
        raise HTTPException(404, "Задача не найдена")
    if row["status"] == "open":
        db.execute(
            "UPDATE tasks SET status='done', completed_at=? WHERE id=?", (db.utcnow(), task_id)
        )
    else:
        db.execute(
            "UPDATE tasks SET status='open', completed_at=NULL WHERE id=?", (task_id,)
        )
    return {"ok": True}


@api.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int):
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return {"ok": True}


class TaskUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    due_date: str | None = None


@api.put("/api/tasks/{task_id}")
async def update_task(task_id: int, data: TaskUpdate):
    row = db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not row:
        raise HTTPException(404, "Задача не найдена")
    sets = []
    params = []
    if data.title is not None:
        sets.append("title = ?")
        params.append(data.title.strip()[:300])
    if data.category is not None:
        sets.append("category = ?")
        params.append(data.category)
    if data.due_date is not None:
        sets.append("due_date = ?")
        params.append(data.due_date or None)
    if sets:
        params.append(task_id)
        db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
    return {"ok": True}


@api.get("/api/obligations")
async def get_obligations(days: int = 60):
    return {
        "upcoming": obligations.upcoming(days=days),
        "all": obligations.list_all(),
    }


@api.post("/api/obligations")
async def add_obligation(data: ObligationIn):
    if not data.title.strip():
        raise HTTPException(400, "Пустое название")
    oid = obligations.add_manual(data.model_dump())
    return {"id": oid}


@api.post("/api/obligations/{obligation_id}/status")
async def set_obligation_status(obligation_id: int, status: str = Body(..., embed=True)):
    obligations.set_status(obligation_id, status)
    return {"ok": True}


@api.delete("/api/obligations/{obligation_id}")
async def delete_obligation(obligation_id: int):
    db.execute("DELETE FROM obligations WHERE id = ?", (obligation_id,))
    return {"ok": True}


@api.get("/api/documents")
async def get_documents():
    return {"documents": documents.list_documents()}


@api.post("/api/documents")
async def upload_document(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "Файл больше 50 МБ")
    try:
        result = await documents.add_document(file.filename or "document", data, source="web")
    except documents.UnsupportedDocument as exc:
        raise HTTPException(415, str(exc)) from exc
    return result


@api.get("/api/documents/{doc_id}")
async def get_document(doc_id: int):
    doc = documents.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    return {"document": doc, "text": documents.get_document_text(doc_id)[:50000]}


@api.get("/api/documents/{doc_id}/download")
async def download_document(doc_id: int):
    """Скачивание оригинала документа (из БД: работает и на сервере с эфемерным диском)."""
    from fastapi.responses import Response
    import urllib.parse

    row = db.query_one(
        "SELECT filename, mime, file_data FROM documents WHERE id = ?", (doc_id,)
    )
    if not row:
        raise HTTPException(404, "Документ не найден")
    if not row["file_data"]:
        raise HTTPException(404, "Оригинальный файл не сохранён (загружен до обновления системы)")
    filename = row["filename"] or f"document-{doc_id}"
    encoded = urllib.parse.quote(filename)
    return Response(
        content=row["file_data"],
        media_type=row["mime"] or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(row["file_data"])),
        },
    )


@api.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int):
    documents.delete_document(doc_id)
    return {"ok": True}


@api.get("/api/search")
async def search_documents(q: str, limit: int = 20):
    return {"results": documents.search(q, limit=min(limit, 50))}


@api.post("/api/ask")
async def ask(data: AskIn):
    return await brain.ask(data.question)


@api.post("/api/inbox")
async def inbox(data: CaptureIn):
    """Умный захват: нейросеть понимает смысл и раскладывает по категориям (или отвечает)."""
    return await triage.capture(data.text)


@api.get("/api/categories")
async def categories():
    """Список категорий с количеством открытых элементов и недавними записями."""
    result = []
    for code, (emoji, label) in triage.CATEGORIES.items():
        if code == "payments":
            continue  # платежи живут в отдельном виджете
        count = db.query_one(
            "SELECT COUNT(*) AS n FROM tasks WHERE category = ? AND status = 'open'", (code,)
        )["n"]
        recent = db.query(
            "SELECT id, title, due_date, created_at FROM tasks "
            "WHERE category = ? AND status = 'open' ORDER BY id DESC LIMIT 6",
            (code,),
        )
        result.append({"code": code, "emoji": emoji, "label": label, "count": count, "recent": recent})
    return {"categories": result}


@api.post("/api/sync")
async def do_sync():
    return await sync_mod.sync_all()


@api.post("/api/briefing/send")
async def do_briefing():
    text = await briefing.send_briefing()
    return {"text": text}


@api.get("/api/briefing/preview")
async def preview_briefing():
    text = await briefing.build_briefing()
    return {"text": text}


@api.get("/")
async def index():
    from fastapi.responses import FileResponse
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


api.mount("/static", StaticFiles(directory=STATIC_DIR, html=False), name="static")


@api.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


def get_web_token() -> str:
    """Токен доступа для внешнего (туннельного) трафика. Генерируется один раз."""
    if settings.web_app_token:
        return settings.web_app_token
    token = db.get_setting("web_app_token", "")
    if not token:
        import uuid
        token = uuid.uuid4().hex
        db.set_setting("web_app_token", token)
    return token


@api.middleware("http")
async def token_auth(request, call_next):
    """Локальный трафик — без ограничений. Render health-check (/api/status) — без токена.
    Внешний (мини-апп через туннель) — только с токеном."""
    if not settings.miniapp_enabled:
        return await call_next(request)
    client_ip = request.client.host if request.client else ""
    if client_ip in ("127.0.0.1", "::1", "localhost"):
        return await call_next(request)
    # Render healthcheck / пингеры — пропускаем (безопасно, только status)
    if request.url.path in ("/api/status", "/healthz"):
        return await call_next(request)

    expected = get_web_token()
    token = request.query_params.get("token") or request.cookies.get("lh_token") or ""
    if token != expected:
        return JSONResponse({"detail": "forbidden"}, status_code=403)

    response = await call_next(request)
    if request.query_params.get("token") == expected and "lh_token" not in request.cookies:
        response.set_cookie("lh_token", expected, max_age=30 * 86400, httponly=True, samesite="lax")
    return response
