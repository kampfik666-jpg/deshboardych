/* ДЭШБОРДЫЧЬ — логика веб-дашборда */

// Токен мини-аппа: сохраняем из URL и восстанавливаем при перезагрузке
(function persistToken() {
  try {
    const params = new URLSearchParams(location.search);
    const t = params.get("token");
    if (t) {
      localStorage.setItem("lh_token", t);
      // Убираем токен из адресной строки, чтобы не светился
      params.delete("token");
      const q = params.toString();
      history.replaceState(null, "", location.pathname + (q ? "?" + q : ""));
    }
  } catch (e) { /* приватный режим — не критично */ }
})();

// Если пришёл 403 (нет токена) — пробуем восстановить из localStorage
function withToken(path) {
  try {
    const saved = localStorage.getItem("lh_token");
    if (!saved) return path;
    return path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(saved);
  } catch (e) { return path; }
}

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

async function api(path, opts = {}) {
  const url = withToken(path);
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const j = await res.json(); if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const MONTHS_GEN = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"];
const WEEKDAYS = ["воскресенье","понедельник","вторник","среда","четверг","пятница","суббота"];

const CAT_META = {
  inbox: ["📥", "Входящие"], work: ["💼", "Работа"], health: ["💊", "Здоровье"],
  nastya: ["🎀", "Настюша"], shopping: ["🛒", "Покупки"], movies: ["🎬", "Фильмы и сериалы"],
  games: ["🎮", "Игры"], ideas: ["💡", "Идеи"], notes: ["📝", "Заметки"], payments: ["💳", "Платежи"],
};
const catLabel = (c) => CAT_META[c] ? `${CAT_META[c][0]} ${CAT_META[c][1]}` : c;

function localTodayISO() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}
let TODAY_ISO = localTodayISO();

// ==================== НАВИГАЦИЯ ====================
function goto(view) {
  $$(".nav-ico").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.remove("active"));
  const el = $(`#view-${view}`);
  if (el) el.classList.add("active");
  loadView(view);
  window.scrollTo({ top: 0 });
}

function loadView(name) {
  if (name === "today") loadToday();
  else if (name === "calendar") loadCalendar();
  else if (name === "mail") loadMail();
  else if (name === "tasks") loadTasks();
  else if (name === "payments") loadPayments();
  else if (name === "docs") loadDocs();
  else if (name === "habits") loadHabits();
  else if (name === "finance") loadFinance();
  else if (name === "settings") loadStatus();
}

$$(".nav-ico").forEach((btn) => btn.addEventListener("click", () => goto(btn.dataset.view)));
document.addEventListener("click", (ev) => {
  const link = ev.target.closest("[data-goto]");
  if (link) goto(link.dataset.goto);
});

// ==================== ВЕРХНЯЯ ПАНЕЛЬ ====================
function setHeaderDate() {
  const d = new Date();
  $("#today-date").textContent = `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

function setGreeting(name) {
  const h = new Date().getHours();
  let g = "Добрый вечер";
  if (h >= 5 && h < 12) g = "Доброе утро";
  else if (h >= 12 && h < 18) g = "Добрый день";
  else if (h < 5) g = "Доброй ночи";
  $("#greeting-title").textContent = name ? `${g}, ${name}! ☀️` : `${g}! ☀️`;
}

$("#bell-btn").addEventListener("click", () => {
  $("#mail-unread-only").checked = true;
  goto("mail");
});

$("#global-search").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    const q = ev.target.value.trim();
    if (!q) return;
    // Умный поиск по всем данным сразу с главной
    goto("docs");
    const docsBox = $("#doc-list");
    const resultsBox = $("#doc-search-results");
    if (resultsBox) resultsBox.innerHTML = '<div class="muted">Ищу по документам, задачам, платежам и письмам…</div>';
    doSmartSearch(q, resultsBox);
  }
});

// цитата дня в сайдбаре
const QUOTES = [
  "«Дисциплина — это решение делать то, чего очень хочется» — Авраам Линкольн",
  "«Сделай сегодня то, что другие не хотят, — завтра будешь жить так, как другие не могут»",
  "«Лучшее время посадить дерево было 20 лет назад. Второе лучшее — сейчас»",
  "«Не бойся идти медленно, бойся стоять на месте»",
  "«Порядок в делах — свобода в голове»",
  "«Маленькие шаги каждый день — большие результаты через год»",
  "«Фокус — это искусство говорить „нет“ хорошему ради лучшего»",
];
$("#side-quote").title = QUOTES[new Date().getDate() % QUOTES.length];

// ==================== ГЛАВНЫЙ ЭКРАН ====================
async function loadToday() {
  try {
    const [data, status] = await Promise.all([api("/api/today"), api("/api/status")]);
    TODAY_ISO = data.date;
    setGreeting(data.owner_name || "");
    // колокольчик
    const totalUnread = Object.values(data.unread || {}).reduce((a, b) => a + b, 0);
    const badge = $("#bell-badge");
    badge.textContent = totalUnread > 99 ? "99+" : totalUnread;
    badge.classList.toggle("show", totalUnread > 0);

    renderEventsWidget(data.events);
    renderPrioWidget(data.due_tasks, data.open_tasks);
    renderMailWidget(data.mails, data.unread);
    renderTasksTomorrowWidget(data.next_tasks);
    renderPayWidget(data.payments);
    renderWeatherTop(data.weather);
    renderScheduleWidget();
    renderRemindersWidget();
    renderServicesWidget(status);
    renderBriefWidget(data.last_briefing);
  } catch (e) {
    $("#w-calendar").innerHTML = `<div class="empty-note bad-text">${esc(e.message)}</div>`;
  }
}

function updateFocus(data) {
  // Баннер «Фокус на главном» заменён на погодную карточку — функция оставлена пустой для совместимости
}

const DOT_COLORS = ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444", "#0ea5e9"];

function renderEventsWidget(events) {
  const box = $("#w-calendar");
  if (!events || !events.length) {
    box.innerHTML = `<div class="empty-note">Сегодня событий нет 🎉</div>`;
    return;
  }
  box.innerHTML = events.slice(0, 6).map((e, i) => {
    const when = e.all_day ? "весь день" : (e.start_at || "").slice(11, 16);
    return `<div class="row">
      <span class="dot" style="background:${DOT_COLORS[i % DOT_COLORS.length]}"></span>
      <span class="time">${when}</span>
      <span class="r-main"><span class="r-title">${esc(e.title)}</span>
      ${e.location ? `<span class="r-sub">📍 ${esc(e.location)}</span>` : ""}</span>
    </div>`;
  }).join("");
}

function renderPrioWidget(dueTasks, openTasks) {
  const box = $("#w-prio");
  const items = [...(dueTasks || []), ...(openTasks || [])].slice(0, 6);
  if (!items.length) {
    box.innerHTML = `<div class="empty-note">Приоритетов нет — добавь первый ✨</div>`;
    return;
  }
  box.innerHTML = items.map((t) => `
    <div class="row ${t.status === "done" ? "done" : ""}">
      <button class="cbox ${t.status === "done" ? "checked" : ""}" data-toggle-today="${t.id}"></button>
      <span class="r-main"><span class="r-title">${esc(t.title)}</span>
      ${t.due_date ? `<span class="r-sub">до ${t.due_date}</span>` : ""}</span>
    </div>`).join("");
}

function avaGradient(source) {
  return source === "google"
    ? "linear-gradient(135deg,#ea4335,#fbbc05)"
    : "linear-gradient(135deg,#fc3f1d,#ff8a65)";
}

function renderMailWidget(mails, unread) {
  const total = Object.values(unread || {}).reduce((a, b) => a + b, 0);
  $("#mail-all-count").textContent = total ? `(${total})` : "";
  const box = $("#w-mail");
  if (!mails || !mails.length) {
    box.innerHTML = `<div class="empty-note">Свежих писем нет ✉️</div>`;
    return;
  }
  box.innerHTML = mails.slice(0, 5).map((m, i) => {
    const from = (m.sender || "").replace(/<.*>/, "").replace(/"/g, "").trim() || m.source;
    const t = (m.date || "").slice(11, 16);
    return `<div class="row" style="cursor:pointer" onclick='openMailModal(${JSON.stringify(m).replace(/'/g,"&#39;")})'>
      <span class="mail-ava" style="background:${avaGradient(m.source)};width:30px;height:30px;font-size:12.5px">${esc((from[0] || "?").toUpperCase())}</span>
      <span class="r-main"><span class="r-title">${esc(m.subject || "(без темы)")}</span>
      <span class="r-sub">${esc(from.slice(0, 42))}</span></span>
      <span class="r-right">${t}</span>
    </div>`;
  }).join("");
}
$("#mail-all-btn").addEventListener("click", () => {
  $("#mail-unread-only").checked = false;
  goto("mail");
});

function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  // Локальное форматирование (toISOString сдвигает в UTC и ломает даты)
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function formatShort(iso) {
  if (!iso) return "";
  return `${parseInt(iso.slice(8, 10), 10)} ${MONTHS_GEN[parseInt(iso.slice(5, 7), 10) - 1]}`;
}
function dueBadge(due) {
  if (!due) return `<span class="badge later">без срока</span>`;
  if (due <= TODAY_ISO) return `<span class="badge today">Сегодня</span>`;
  if (due === addDays(TODAY_ISO, 1)) return `<span class="badge tomorrow">Завтра</span>`;
  return `<span class="badge soon">${formatShort(due)}</span>`;
}

function renderTasksTomorrowWidget(nextTasks) {
  const box = $("#w-tasks-tomorrow");
  const tomorrow = addDays(TODAY_ISO, 1);
  // Фильтруем только задачи на завтра
  const items = (nextTasks || []).filter(t => t.due_date === tomorrow);
  if (!items.length) {
    box.innerHTML = `<div class="empty-note">На завтра задач нет 🎉</div>`;
    return;
  }
  box.innerHTML = items.map((t) => `
    <div class="row">
      <button class="cbox" data-toggle-today="${t.id}"></button>
      <span class="r-main"><span class="r-title">${esc(t.title)}</span>
      ${t.due_time ? `<span class="r-sub">⏰ ${t.due_time}</span>` : ""}</span>
    </div>`).join("");
}

function renderPayWidget(payments) {
  const box = $("#w-pay");
  const items = (payments || []).slice(0, 6);
  if (!items.length) {
    box.innerHTML = `<div class="empty-note">Ближайших платежей нет 💸</div>`;
    return;
  }
  box.innerHTML = items.map((p) => {
    const amt = p.amount ? `${Number(p.amount).toLocaleString("ru-RU")} ${p.currency || "₽"}` : "";
    const over = p.overdue;
    return `<div class="row">
      <span class="badge ${over ? "over" : "later"}">${formatShort(p.next_date)}</span>
      <span class="r-main"><span class="r-title">${esc(p.title)}</span></span>
      <span class="r-right">${esc(amt)}</span>
    </div>`;
  }).join("");
}

function renderWeatherTop(w) {
  const el = document.getElementById("weather-short");
  if (!el) return;
  if (!w) { el.textContent = "Погода недоступна"; return; }
  // Убираем префикс "🌤 Погода в г. Екатеринбург: " для компактности
  const short = w.replace(/^🌤\s*Погода в г\.\s*\S+:\s*/, "");
  el.textContent = short;
}

function renderWeatherWidget(w) {
  const box = $("#w-weather");
  if (!w) {
    box.innerHTML = `<div class="empty-note">Погода не настроена (WEATHER_CITY в .env)</div>`;
    return;
  }
  const m = w.match(/Погода в г\. (.+?):\s*(.+?),\s*([+-]?\d+)…([+-]?\d+)°C(?:,\s*(.+))?/);
  if (m) {
    box.innerHTML = `<div class="weather-big">
      <div class="weather-temp">${m[3]}…${m[4]}°</div>
      <div><div class="weather-desc">${esc(m[2])}${m[5] ? " · " + esc(m[5]) : ""}</div>
      <div class="weather-city">${esc(m[1])}</div></div>
    </div>`;
  } else {
    box.innerHTML = `<div class="weather-big"><div class="weather-desc">${esc(w)}</div></div>`;
  }
}

function renderServicesWidget(status) {
  const srcs = status.sources || [];
  const has = (n) => srcs.some((s) => s.name === n);
  const tiles = [
    { letter: "Я", bg: "linear-gradient(135deg,#fc3f1d,#ff8a65)", name: "Яндекс 360", on: has("yandex") },
    { letter: "M", bg: "linear-gradient(135deg,#ea4335,#fbbc05)", name: "Gmail", on: has("google") },
    { letter: "📅", bg: "linear-gradient(135deg,#4285f4,#34a853)", name: "Google Календарь", on: has("google") },
    { letter: "✈", bg: "linear-gradient(135deg,#2aabee,#229ed9)", name: "Telegram-бот", on: !!status.telegram_bot },
    { letter: "AI", bg: "linear-gradient(135deg,#8b5cf6,#5850ec)", name: "Нейросеть", on: !!(status.llm && status.llm.available) },
  ];
  $("#w-services").innerHTML = tiles.map((t) => `
    <div class="svc ${t.on ? "on" : "off"}">
      <div class="svc-logo" style="background:${t.bg}">${t.letter}</div>
      <div class="svc-name">${t.name}</div>
      <div class="svc-status">${t.on ? "работает" : "выключен"}</div>
    </div>`).join("");
}

function renderBriefWidget(lb) {
  const box = $("#w-brief");
  if (!lb || !lb.text) {
    box.innerHTML = `<div class="empty-note">Брифинг ещё не отправлялся — нажми «Прислать в Telegram»</div>`;
    return;
  }
  box.innerHTML = `<div class="brief-date">Последний брифинг: ${lb.day}${lb.sent ? " · доставлен в Telegram ✅" : ""}</div>
    <div class="brief-text">${esc(lb.text)}</div>`;
}

$("#btn-send-briefing").addEventListener("click", async (ev) => {
  ev.target.disabled = true;
  ev.target.textContent = "Отправляю…";
  try {
    await api("/api/briefing/send", { method: "POST" });
    loadToday();
  } catch (e) { alert("Ошибка: " + e.message); }
  finally { ev.target.disabled = false; ev.target.textContent = "Прислать в Telegram ➔"; }
});

$("#btn-sync").addEventListener("click", async (ev) => {
  ev.target.disabled = true;
  const old = ev.target.textContent;
  ev.target.textContent = "🔄 Синхронизирую…";
  try { await api("/api/sync", { method: "POST" }); loadToday(); }
  catch (e) { alert("Ошибка: " + e.message); }
  finally { ev.target.disabled = false; ev.target.textContent = old; }
});

// ==================== УМНЫЙ ЗАХВАТ ====================
async function doCapture() {
  const input = $("#capture-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  const box = $("#capture-result");
  box.innerHTML = `<div class="cap-card"><div class="cap-head">✨ Понимаю смысл…</div></div>`;
  try {
    const r = await api("/api/inbox", { method: "POST", body: JSON.stringify({ text }) });
    if (r.intent === "question") {
      box.innerHTML = `<div class="cap-card answer">
        <div class="cap-head">❓ Ответ «второго мозга»</div>
        <div class="cap-body">${esc(r.answer)}</div>
        ${r.sources && r.sources.length ? `<div class="cap-src">📚 Источники: ${r.sources.map(esc).join(", ")}</div>` : ""}
      </div>`;
    } else if (r.intent === "capture") {
      const items = r.items || [];
      const engineNote = r.engine !== "llm" ? " · распознано без нейросети" : "";
      if (items.length <= 1) {
        const it = items[0] || {};
        box.innerHTML = `<div class="cap-card">
          <div class="cap-head">${it.emoji || "📥"} Сохранил в «${esc(it.label || "")}»${engineNote}</div>
          <div class="cap-body">${esc(it.title || "")}${esc(it.when || "")}</div>
        </div>`;
      } else {
        const list = items.map((it) =>
          `<div style="padding:3px 0">${it.emoji || "📥"} <b>${esc(it.title)}</b> → ${esc(it.label)}${esc(it.when || "")}</div>`
        ).join("");
        box.innerHTML = `<div class="cap-card">
          <div class="cap-head">✅ Добавил <b>${items.length}</b> записей${engineNote}</div>
          <div class="cap-body">${list}</div>
        </div>`;
      }
      loadToday();
    } else {
      box.innerHTML = `<div class="cap-card"><div class="cap-body">${esc(r.message || "Не понял — переформулируй 🙂")}</div></div>`;
    }
  } catch (e) {
    box.innerHTML = `<div class="cap-card"><div class="cap-body bad-text">Ошибка: ${esc(e.message)}</div></div>`;
  }
}
$("#capture-send").addEventListener("click", doCapture);
$("#capture-input").addEventListener("keydown", (ev) => { if (ev.key === "Enter") doCapture(); });

// ==================== КАЛЕНДАРЬ (полный) ====================
let calCurrentDate = localTodayISO();

function formatDateRu(iso) {
  const d = new Date(iso + "T00:00:00");
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()}`;
}

async function loadCalendar() {
  const box = $("#calendar-list");
  const title = $("#cal-date-title");
  if (title) title.textContent = "📅 " + formatDateRu(calCurrentDate);
  box.innerHTML = `<div class="muted">загрузка…</div>`;
  try {
    // Параллельная загрузка всех данных
    const [eventsData, tasksData, payData] = await Promise.all([
      api("/api/events?days=21"),
      api("/api/tasks"),
      api("/api/obligations?days=1").catch(() => ({ upcoming: [] }))
    ]);

    // Фильтруем события для выбранного дня
    const dayEvents = (eventsData.days || [])
      .filter(d => d.date === calCurrentDate)
      .flatMap(d => d.events);

    // Задачи на этот день
    const dayTasks = (tasksData.tasks || []).filter(t => t.due_date === calCurrentDate && t.status === "open");

    // Платежи на этот день
    const dayPayments = (payData.upcoming || []).filter(p => p.next_date === calCurrentDate);

    let html = "";

    if (dayEvents.length) {
      html += `<h3 class="sub-title">📅 События</h3>`;
      html += dayEvents.map((e, i) => {
        const when = e.all_day ? "весь день" : (e.start_at || "").slice(11, 16);
        const loc = e.location ? ` · ${esc(e.location)}` : "";
        return `<div class="row">
          <span class="dot" style="background:${DOT_COLORS[i % DOT_COLORS.length]}"></span>
          <span class="time">${when}</span>
          <span class="r-main"><span class="r-title">${esc(e.title)}${loc}</span>
          <span class="r-sub">${esc(e.source || "")}${e.cal_name ? " · " + esc(e.cal_name) : ""}</span></span>
        </div>`;
      }).join("");
    }

    if (dayTasks.length) {
      html += `<h3 class="sub-title">✅ Задачи на этот день</h3>`;
      html += dayTasks.map(t => `
        <div class="row">
          <button class="cbox ${t.status === 'done' ? 'checked' : ''}" data-toggle-today="${t.id}"></button>
          <span class="r-main"><span class="r-title">${esc(t.title)}</span>
          <span class="r-sub">${catLabel(t.category)}</span></span>
          ${t.due_time ? `<span class="r-right">⏰ ${t.due_time}</span>` : ""}
        </div>`).join("");
    }

    if (dayPayments.length) {
      html += `<h3 class="sub-title">💳 Платежи</h3>`;
      html += dayPayments.map(p => {
        const amt = p.amount ? ` · ${Number(p.amount).toLocaleString("ru-RU")} ${p.currency || "₽"}` : "";
        return `<div class="row">
          <span class="badge later">${formatShort(p.next_date)}</span>
          <span class="r-main"><span class="r-title">${esc(p.title)}${amt}</span></span>
        </div>`;
      }).join("");
    }

    if (!html) {
      html = `<div class="empty-note">На этот день ничего не запланировано 🎉<br><br>Напиши в умную строку на главной чтобы добавить задачу или событие</div>`;
    }

    box.innerHTML = html;
  } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}

// Навигация календаря
$("#cal-prev")?.addEventListener("click", () => {
  calCurrentDate = addDays(calCurrentDate, -1);
  loadCalendar();
});
$("#cal-next")?.addEventListener("click", () => {
  calCurrentDate = addDays(calCurrentDate, 1);
  loadCalendar();
});
$("#cal-today-btn")?.addEventListener("click", () => {
  calCurrentDate = new Date().toISOString().slice(0, 10);
  loadCalendar();
});

// Добавление события/задачи на выбранный день
$("#cal-add-event")?.addEventListener("click", () => {
  $("#cal-event-form").classList.toggle("hidden");
  $("#cal-event-title").focus();
});
$("#cal-event-form")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const title = $("#cal-event-title").value.trim();
  if (!title) return;
  const time = $("#cal-event-time").value || null;
  await api("/api/tasks", { method: "POST", body: JSON.stringify({
    title, category: "inbox", due_date: calCurrentDate, due_time: time,
  })});
  $("#cal-event-title").value = "";
  $("#cal-event-time").value = "";
  $("#cal-event-location").value = "";
  $("#cal-event-form").classList.add("hidden");
  loadCalendar();
});

// ==================== ПОЧТА (полная) ====================
async function loadMail() {
  const onlyUnread = $("#mail-unread-only").checked;
  const box = $("#mail-list");
  box.innerHTML = `<div class="muted">загрузка…</div>`;
  try {
    const data = await api(`/api/mails?limit=80&unread_only=${onlyUnread}`);
    const spamNote = data.spam_count > 0
      ? `<div style="padding:10px 16px;font-size:13px;color:var(--text-4)">🛡️ Автоматически скрыто ${data.spam_count} спам-писем</div>` : "";
    if (!data.mails.length) {
      box.innerHTML = spamNote + `<div class="empty-note">Писем нет${data.spam_count > 0 ? " (весь мусор отфильтрован ✨)" : ""}</div>`;
      return;
    }
    box.innerHTML = spamNote + data.mails.map((m) => {
      const from = (m.sender || "").replace(/<.*>/, "").replace(/"/g, "").trim();
      const d = (m.date || "").slice(0, 16).replace("T", " ");
      return `<div class="list-item mail-item ${m.unread ? "unread" : ""}" style="cursor:pointer" onclick='openMailModal(${JSON.stringify(m).replace(/'/g,"&#39;")})'>
        <span class="mail-ava" style="background:${avaGradient(m.source)}">${esc((from[0] || "?").toUpperCase())}</span>
        <span class="li-main">
          <div class="li-title">${esc(m.subject || "(без темы)")}${m.unread ? ' <span class="badge today" style="background:#eef2ff;color:#5850ec">новое</span>' : ""}</div>
          <div class="li-sub">${esc(from)} · ${d} · ${esc(m.source || "")}</div>
        </span>
      </div>`;
    }).join("");
  } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}
$("#mail-unread-only").addEventListener("change", loadMail);

// ==================== ЗАДАЧИ / СПИСКИ ====================
async function loadTasks() {
  var box = document.getElementById("task-list");
  if (!box) return;
  box.innerHTML = '<div class="muted">загрузка…</div>';
  try {
    var data = await api("/api/tasks");
    if (!data.tasks || !data.tasks.length) {
      box.innerHTML = '<div class="empty-note">Пусто. Напиши что-нибудь в умную строку на главной ✨</div>';
      return;
    }
    var byCat = {};
    data.tasks.forEach(function(t) {
      if (!byCat[t.category]) byCat[t.category] = [];
      byCat[t.category].push(t);
    });
    var html = "";
    Object.keys(byCat).forEach(function(cat) {
      html += '<h3 class="sub-title">' + catLabel(cat) + ' <span class="muted">(' + byCat[cat].length + ')</span></h3>';
      byCat[cat].forEach(function(t) {
        var doneClass = t.status === "done" ? " done" : "";
        var checkedClass = t.status === "done" ? " checked" : "";
        var dueHtml = t.due_date ? '<div class="li-sub">до ' + esc(t.due_date) + '</div>' : "";
        var safeTitle = t.title.replace(/'/g, "\\'").replace(/"/g, "&quot;");
        html += '<div class="list-item' + doneClass + '">' +
          '<button class="cbox' + checkedClass + '" onclick="toggleTask(' + t.id + ',\'tasks\')"></button>' +
          '<span class="li-main"><div class="li-title">' + esc(t.title) + '</div>' + dueHtml + '</span>' +
          '<button class="mini" onclick="editTask(' + t.id + ')">✏️</button>' +
          '<button class="mini danger" onclick="deleteTask(' + t.id + ')">✕</button>' +
          '</div>';
      });
    });
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = '<div class="bad-text">' + esc(e.message) + '</div>';
  }
}

$("#task-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const title = $("#task-title").value.trim();
  if (!title) return;
  await api("/api/tasks", { method: "POST", body: JSON.stringify({
    title, category: $("#task-category").value, due_date: $("#task-due").value || null,
  })});
  $("#task-title").value = "";
  $("#task-due").value = "";
  loadTasks();
});

$("#prio-add-btn").addEventListener("click", () => {
  $("#prio-form").classList.toggle("hidden");
  $("#prio-input").focus();
});
$("#prio-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const title = $("#prio-input").value.trim();
  if (!title) return;
  await api("/api/tasks", { method: "POST", body: JSON.stringify({
    title, category: "inbox", due_date: TODAY_ISO,
  })});
  $("#prio-input").value = "";
  $("#prio-form").classList.add("hidden");
  loadToday();
});

window.toggleTask = async (id, refresh) => {
  await api(`/api/tasks/${id}/toggle`, { method: "POST" });
  if (refresh === "today") loadToday(); else loadTasks();
};
window.deleteTask = async (id) => {
  if (!confirm("Удалить запись?")) return;
  await api(`/api/tasks/${id}`, { method: "DELETE" });
  loadTasks();
};

// ==================== ПЛАТЕЖИ ====================
function renderMonthlyTotal(all) {
  const el = $("#monthly-total-amount");
  let total = 0;
  (all || []).forEach(o => {
    if (o.status !== "active") return;
    const amt = Number(o.amount) || 0;
    if (!amt) return;
    if (o.kind === "monthly") total += amt;
    else if (o.kind === "yearly") total += amt / 12;
  });
  if (el) el.textContent = total.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " ₽";
}

async function loadPayments() {
  const allBox = $("#obl-all");
  allBox.innerHTML = `<div class="muted">загрузка…</div>`;
  try {
    const data = await api("/api/obligations?days=365");
    renderMonthlyTotal(data.all || []);
    // Сортируем по дню месяца: разовые по due_date, ежемесячные по day_of_month, ежегодные по month+day
    const sorted = (data.all || []).slice().sort((a, b) => {
      const dayA = a.day_of_month || (a.due_date ? parseInt(a.due_date.slice(8, 10)) : 99);
      const dayB = b.day_of_month || (b.due_date ? parseInt(b.due_date.slice(8, 10)) : 99);
      if (dayA !== dayB) return dayA - dayB;
      // Если день одинаковый — сортируем по месяцу
      const monA = a.month_of_year || (a.due_date ? parseInt(a.due_date.slice(5, 7)) : 99);
      const monB = b.month_of_year || (b.due_date ? parseInt(b.due_date.slice(5, 7)) : 99);
      return monA - monB;
    });
    allBox.innerHTML = sorted.length
      ? sorted.map(renderOblItem).join("")
      : `<div class="empty-note">Обязательств пока нет — добавь через форму выше или напиши боту</div>`;
  } catch (e) { allBox.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}

function renderOblItem(o) {
  const when = o.next_date
    ? formatShort(o.next_date)
    : (o.kind === "monthly" ? `${o.day_of_month}-го числа` : o.kind === "yearly" ? "ежегодно" : "—");
  const amt = o.amount ? ` · ${Number(o.amount).toLocaleString("ru-RU")} ${o.currency || "₽"}` : "";
  const cls = o.overdue ? " overdue" : (o.status !== "active" ? " done" : "");
  return `<div class="list-item${cls}">
    <span class="badge ${o.overdue ? "over" : "later"}">${when}</span>
    <span class="li-main">
      <div class="li-title">${esc(o.title)}${amt}</div>
      ${o.note ? `<div class="li-sub">${esc(o.note)}</div>` : ""}
    </span>
    <button class="mini" onclick="setOblStatus(${o.id}, '${o.status === "active" ? "done" : "active"}')">${o.status === "active" ? "оплачено" : "вернуть"}</button>
    <button class="mini danger" onclick="deleteObl(${o.id}, '${esc(o.title).replace(/'/g, "\\'")}')">✕</button>
  </div>`;
}

$("#obl-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const title = $("#obl-title").value.trim();
  if (!title) return;
  const kind = $("#obl-kind").value;
  await api("/api/obligations", { method: "POST", body: JSON.stringify({
    title, kind,
    due_date: kind === "once" ? ($("#obl-due").value || null) : null,
    day_of_month: kind === "monthly" ? parseInt($("#obl-day").value || "1", 10) : null,
    amount: parseFloat($("#obl-amount").value) || null,
  })});
  $("#obl-title").value = "";
  $("#obl-amount").value = "";
  loadPayments();
});

window.setOblStatus = async (id, status) => {
  await api(`/api/obligations/${id}/status`, { method: "POST", body: JSON.stringify({ status }) });
  loadPayments();
};

window.deleteObl = async (id, title) => {
  if (!confirm(`Удалить платёж «${title}»?\n\nЭто действие нельзя отменить.`)) return;
  await api(`/api/obligations/${id}`, { method: "DELETE" });
  loadPayments();
};

// ==================== ДОКУМЕНТЫ ====================
async function loadDocs() {
  const box = $("#doc-list");
  box.innerHTML = `<div class="muted">загрузка…</div>`;
  try {
    const data = await api("/api/documents");
    if (!data.documents.length) {
      box.innerHTML = `<div class="empty-note">Документов нет — загрузи PDF здесь или пришли боту в Telegram</div>`;
      return;
    }
    box.innerHTML = data.documents.map((d) => {
      const obl = d.obligations_count ? ` · платежей: ${d.obligations_count}` : "";
      return `<div class="list-item">
        <span class="li-main">
          <div class="li-title">📄 ${esc(d.title)}</div>
          <div class="li-sub">${(d.created_at || "").slice(0, 10)} · ${(d.char_count || 0).toLocaleString("ru-RU")} символов${obl}</div>
        </span>
        <button class="mini danger" onclick="deleteDoc(${d.id})">✕</button>
      </div>`;
    }).join("");
  } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}

$("#doc-file").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const status = $("#doc-status");
  status.textContent = "⏳ Загружаю и анализирую документ…";
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(withToken("/api/documents"), { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (data.duplicate) status.textContent = `♻️ Уже сохранён: «${data.title}»`;
    else status.textContent = `✅ «${data.title}» сохранён. Найдено платежей: ${(data.obligations || []).length}.`;
    loadDocs();
  } catch (e) { status.textContent = "❌ " + e.message; }
  finally { ev.target.value = ""; }
});

let searchTimer;
$("#doc-search").addEventListener("input", (ev) => {
  clearTimeout(searchTimer);
  const q = ev.target.value.trim();
  const box = $("#doc-search-results");
  if (!q) { box.innerHTML = ""; return; }
  searchTimer = setTimeout(async () => {
    try {
      const data = await api(`/api/search?q=${encodeURIComponent(q)}&limit=20`);
      box.innerHTML = data.results.length
        ? data.results.map((r) => `<div class="search-hit">
            <div class="src">${esc(r.title)} · фрагмент ${(r.idx || 0) + 1}</div>
            <div class="frag">${esc(r.text || "")}</div>
          </div>`).join("")
        : `<div class="empty-note">Ничего не нашлось</div>`;
    } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
  }, 350);
});

window.deleteDoc = async (id) => {
  if (!confirm("Удалить документ из базы?")) return;
  await api(`/api/documents/${id}`, { method: "DELETE" });
  loadDocs();
};

// ==================== СПРОСИТЬ ====================
$("#ask-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const input = $("#ask-question");
  const q = input.value.trim();
  if (!q) return;
  const log = $("#ask-log");
  log.insertAdjacentHTML("beforeend", `<div class="ask-q">${esc(q)}</div>`);
  input.value = "";
  const ph = document.createElement("div");
  ph.className = "ask-a muted";
  ph.textContent = "думаю…";
  log.appendChild(ph);
  try {
    const data = await api("/api/ask", { method: "POST", body: JSON.stringify({ question: q }) });
    let text = data.answer || "(пусто)";
    if (data.sources && data.sources.length) text += "\n\n📚 Источники: " + data.sources.join(", ");
    ph.classList.remove("muted");
    ph.textContent = text;
  } catch (e) {
    ph.classList.add("bad-text");
    ph.textContent = "Ошибка: " + e.message;
  }
  ph.scrollIntoView({ behavior: "smooth", block: "end" });
});

// ==================== НАСТРОЙКИ ====================
async function loadStatus() {
  const box = $("#status-box");
  box.innerHTML = `<div class="muted">загрузка…</div>`;
  try {
    const s = await api("/api/status");
    const rows = [
      ["Telegram-бот", s.telegram_bot ? "✅ подключён" : "❌ не задан BOT_TOKEN"],
      ["Брифинг", `каждый день в ${s.briefing_time} (${s.timezone})`],
      ["Нейросеть", s.llm.available ? `✅ ${s.llm.model}` : "❌ не подключена"],
      ["Источники", s.sources.length ? s.sources.map((x) => `${x.label} (${x.login})`).join(", ") : "нет — заполни .env"],
      ["В базе", `документов ${s.counts.docs || 0} · обязательств ${s.counts.obligations || 0} · записей ${s.counts.tasks || 0} · событий ${s.counts.events || 0} · писем ${s.counts.mails || 0}`],
    ];
    let html = `<div class="card widget wide"><div class="w-head"><span class="w-ico indigo">⚙️</span><h3>Состояние системы</h3></div>
      ${rows.map(([k, v]) => `<div class="status-row"><span>${k}</span><span>${v}</span></div>`).join("")}</div>`;
    if (s.last_sync && s.last_sync.length) {
      html += `<div class="card widget wide"><div class="w-head"><span class="w-ico blue">🔄</span><h3>Последняя синхронизация</h3></div>` +
        s.last_sync.map((r) => `<div class="status-row">
          <span>${r.ok ? "✅" : "❌"} ${esc(r.source)}/${esc(r.kind)}</span>
          <span>${esc((r.detail || "").slice(0, 80))}</span></div>`).join("") + "</div>";
    }
    box.innerHTML = html;
  } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}

// ==================== ТРЕКЕР ПРИВЫЧЕК / ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ ====================
async function loadHabits() {
  const grid = document.getElementById("habits-grid");
  const scoreEl = document.getElementById("habits-score");
  if (!grid) return;
  grid.innerHTML = '<div class="muted">загрузка…</div>';
  try {
    const data = await api("/api/habits?days=7");
    if (scoreEl) scoreEl.textContent = `⭐ Ближайшие 30 дней: ${data.score} баллов`;
    if (!data.habits || !data.habits.length) {
      grid.innerHTML = '<div class="empty-note">Привычек нет — добавь первую ⭐<br><br>Отметь выполнение за каждый день: для хороших +, для плохих −</div>';
      return;
    }
    grid.innerHTML = data.habits.map(h => {
      const streakTxt = h.type === "good" ? `🔥 ${h.streak} дней подряд` : `🛡️ ${h.streak} дней без срыва`;
      const daysHtml = h.week.map(d => {
        const cls = d.done ? (h.type === "good" ? "done-good" : "done-bad") : "";
        const isToday = d.day === new Date().toISOString().slice(0, 10);
        return `<button class="habit-day ${cls} ${isToday ? "today" : ""}" data-habit="${h.id}" data-day="${d.day}">${d.label}<br>${d.done ? "✓" : ""}</button>`;
      }).join("");
      return `<div class="habit-card">
        <div class="habit-emoji">${esc(h.emoji)}</div>
        <div class="habit-info">
          <div class="habit-name">${esc(h.name)}</div>
          <div class="habit-meta">${isGoodType(h.type)} · ${streakTxt} · за 30 дней: ${h.total30}</div>
        </div>
        <div class="habit-week">${daysHtml}</div>
        <div class="habit-actions">
          <button class="mini danger" onclick="deleteHabit(${h.id})">✕</button>
        </div>
      </div>`;
    }).join("");
  } catch (e) { grid.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}
function isGoodType(t) { return t === "good" ? "✅ хорошая" : "❌ вредная"; }

$("#habit-form")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const name = $("#habit-name").value.trim();
  if (!name) return;
  await api("/api/habits", { method: "POST", body: JSON.stringify({
    name, type: $("#habit-type").value, emoji: $("#habit-emoji").value.trim() || "⭐",
  })});
  $("#habit-name").value = "";
  loadHabits();
});

// Клик по дню — переключить отметку
document.addEventListener("click", async function(ev) {
  var btn = ev.target.closest(".habit-day");
  if (!btn) return;
  var habitId = parseInt(btn.dataset.habit);
  var day = btn.dataset.day;
  var newVal = await api(`/api/habits/${habitId}/toggle`, { method: "POST", body: JSON.stringify({ day }) });
  // Перекрашиваем кнопку без полного перезапуска
  btn.classList.toggle("done-good", !!newVal.done);
  btn.classList.toggle("done-bad", !!newVal.done && btn.closest(".habit-card")?.querySelector(".habit-meta")?.textContent?.includes("вредная"));
  btn.textContent = (btn.querySelector("br") ? "" : "") + btn.innerHTML; // без пересборки текста, просто класс
  loadHabits();
});

window.deleteHabit = async function(id) {
  if (!confirm("Удалить привычку?")) return;
  await api(`/api/habits/${id}`, { method: "DELETE" });
  loadHabits();
};

// ==================== УМНЫЙ ПОИСК ПО ВСЕМ ДАННЫМ ====================
// Ищет по документам, задачам, платежам и письмам — и отвечает либо через нейросеть, либо списком.
async function smartSearch(query) {
  const q = query.trim();
  if (!q) return null;
  // 1) Документы (FTS)
  const docData = await api(`/api/search?q=${encodeURIComponent(q)}&limit=5`).catch(() => ({ results: [] }));
  // 2) Задачи
  const tasksData = await api("/api/tasks").catch(() => ({ tasks: [] }));
  const qLower = q.toLowerCase();
  const taskHits = (tasksData.tasks || []).filter(t =>
    (t.title && t.title.toLowerCase().includes(qLower)) ||
    (t.category && t.category.toLowerCase().includes(qLower))
  ).slice(0, 5);
  // 3) Платежи
  const payData = await api("/api/obligations?days=365").catch(() => ({ all: [] }));
  const payHits = (payData.all || []).filter(p =>
    (p.title && p.title.toLowerCase().includes(qLower))
  ).slice(0, 5);
  // 4) Письма
  const mailData = await api("/api/mails?limit=30").catch(() => ({ mails: [] }));
  const mailHits = (mailData.mails || []).filter(m =>
    (m.subject && m.subject.toLowerCase().includes(qLower)) ||
    (m.sender && m.sender.toLowerCase().includes(qLower))
  ).slice(0, 5);
  return { docs: docData.results || [], tasks: taskHits, payments: payHits, mails: mailHits };
}

async function doSmartSearch(query, box) {
  const res = await smartSearch(query);
  if (!res) { box.innerHTML = '<div class="empty-note">Пустой запрос</div>'; return; }
  const { docs, tasks, payments, mails } = res;
  let html = "";
  if (docs.length) {
    html += '<h3 class="sub-title">📄 Документы</h3>';
    html += docs.map(d => `<div class="search-hit"><div class="src">${esc(d.title)} · фрагмент ${(d.idx||0)+1}</div><div class="frag">${esc((d.text||"").slice(0,300))}</div></div>`).join("");
  }
  if (tasks.length) {
    html += '<h3 class="sub-title">✅ Задачи</h3>';
    html += tasks.map(t => `<div class="list-item"><span class="li-main"><div class="li-title">${esc(t.title)}</div><div class="li-sub">${catLabel(t.category)}</div></span></div>`).join("");
  }
  if (payments.length) {
    html += '<h3 class="sub-title">💳 Платежи</h3>';
    html += payments.map(p => `<div class="list-item"><span class="li-main"><div class="li-title">${esc(p.title)}</div><div class="li-sub">${p.next_date || p.due_date || ""}</div></span></div>`).join("");
  }
  if (mails.length) {
    html += '<h3 class="sub-title">📬 Письма</h3>';
    html += mails.map(m => `<div class="list-item"><span class="li-main"><div class="li-title">${esc(m.subject || "(без темы)")}</div><div class="li-sub">${esc((m.sender||"").slice(0,60))}</div></span></div>`).join("");
  }
  if (!html) html = '<div class="empty-note">Ничего не нашёл по «' + esc(query) + '». Попробуй другое слово или отправь документ боту.</div>';
  box.innerHTML = html;
}

// ==================== TELEGRAM MINI APP ====================
(function initMiniApp() {
  var tg = window.Telegram && window.Telegram.WebApp;
  if (!tg || !tg.initData) return;
  try {
    tg.ready();
    tg.expand();
    tg.setHeaderColor && tg.setHeaderColor("#0b0e27");
    tg.setBackgroundColor && tg.setBackgroundColor("#f4f5f8");
    document.body.classList.add("miniapp");
  } catch (e) { /* не критично */ }
})();

// ==================== ГОЛОСОВОЙ ВВОД (Web Speech API) ====================
(function initVoiceInput() {
  var mic = document.getElementById("capture-mic");
  if (!mic) return;
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { mic.style.display = "none"; return; }
  mic.addEventListener("click", function () {
    var rec = new SR();
    rec.lang = "ru-RU";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    mic.classList.add("recording");
    mic.textContent = "🔴";
    rec.onresult = function (e) {
      var t = e.results[0][0].transcript;
      document.getElementById("capture-input").value = t;
      doCapture();
    };
    rec.onerror = function () {};
    rec.onend = function () {
      mic.classList.remove("recording");
      mic.textContent = "🎤";
    };
    try { rec.start(); } catch (e) { mic.textContent = "🎤"; mic.classList.remove("recording"); }
  });
})();

// ==================== СТАРТ ====================
setHeaderDate();
$("#prio-form").classList.add("hidden");

// ==================== ФИНАНСЫ ====================
async function loadFinance() {
  try {
    const stats = await api("/api/finance/stats?months=6");
    renderFinTotal(stats);
    renderFinMonthly(stats);
    renderFinCategories(stats);
    renderFinTop(stats);
  } catch (e) {
    $("#fin-total").innerHTML = `<div class="empty-note bad-text">${esc(e.message)}</div>`;
  }
}

function renderFinTotal(stats) {
  const box = $("#fin-total");
  const total = Number(stats.total || 0).toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  const catCount = (stats.by_category || []).length;
  box.innerHTML = `<div class="fin-big-number">${total} ₽</div>
    <div class="fin-sub">за последние ${stats.period_months} мес. · ${catCount} категорий</div>`;
}

function renderFinMonthly(stats) {
  const box = $("#fin-monthly");
  const months = stats.by_month || [];
  if (!months.length) { box.innerHTML = `<div class="empty-note">Нет данных — загрузите выписку или включите уведомления от банка</div>`; return; }
  const maxVal = Math.max(...months.map(m => m.total), 1);
  const monthNames = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"];
  box.innerHTML = `<div class="bar-chart">${months.map(m => {
    const pct = Math.max((m.total / maxVal) * 100, 2);
    const mName = m.month ? monthNames[parseInt(m.month.slice(5,7))-1] : "?";
    const val = Number(m.total).toLocaleString("ru-RU", {maximumFractionDigits:0});
    return `<div class="bar-col"><div class="bar-value">${val}</div><div class="bar" style="height:${pct}%"></div><div class="bar-label">${mName}</div></div>`;
  }).join("")}</div>`;
}

function renderFinCategories(stats) {
  const box = $("#fin-categories");
  const cats = stats.by_category || [];
  if (!cats.length) { box.innerHTML = `<div class="empty-note">Нет расходов</div>`; return; }
  const maxVal = Math.max(...cats.map(c => c.total), 1);
  const colors = ["#5850ec","#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6","#0ea5e9","#ec4899","#14b8a6","#f97316"];
  box.innerHTML = cats.slice(0, 8).map((c, i) => {
    const pct = Math.max((c.total / maxVal) * 100, 3);
    const val = Number(c.total).toLocaleString("ru-RU", {maximumFractionDigits:0});
    return `<div class="cat-row">
      <span class="cat-name">${esc(c.category)}</span>
      <div class="cat-bar-wrap"><div class="cat-bar-fill" style="width:${pct}%;background:${colors[i%colors.length]}"></div></div>
      <span class="cat-amount">${val} ₽</span>
    </div>`;
  }).join("");
}

function renderFinTop(stats) {
  const box = $("#fin-top");
  const top = stats.top_expenses || [];
  if (!top.length) { box.innerHTML = `<div class="empty-note">Нет крупных расходов</div>`; return; }
  box.innerHTML = top.map(t => {
    const val = Number(t.amount).toLocaleString("ru-RU", {maximumFractionDigits:0});
    return `<div class="row">
      <span class="badge later">${t.date?.slice(5) || ""}</span>
      <span class="r-main"><span class="r-title">${esc(t.description)}</span>
      <span class="r-sub">${esc(t.category)}</span></span>
      <span class="r-right" style="font-weight:600">${val} ₽</span>
    </div>`;
  }).join("");
}

// Загрузка CSV
$("#csv-file")?.addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const status = $("#finance-status");
  status.textContent = "⏳ Загружаю выписку…";
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(withToken("/api/finance/upload-csv"), { method: "POST", body: form });
    const data = await res.json();
    status.textContent = `✅ Загружено: ${data.added} расходов (${data.duplicates_skipped} дубликатов пропущено)`;
    loadFinance();
  } catch (e) { status.textContent = "❌ " + e.message; }
  finally { ev.target.value = ""; }
});

// Сканирование почты на расходы
$("#scan-bank-mails")?.addEventListener("click", async (ev) => {
  ev.target.disabled = true;
  const status = $("#finance-status");
  status.textContent = "🔍 Сканирую почту…";
  try {
    const data = await api("/api/finance/scan-mails", { method: "POST" });
    status.textContent = data.found > 0
      ? `✅ Найдено ${data.found} новых расходов из банковских писем`
      : "ℹ️ Новых расходов в почте не найдено";
    loadFinance();
  } catch (e) { status.textContent = "❌ " + e.message; }
  finally { ev.target.disabled = false; }
});

// Напоминания о платежах на главном экране
async function renderRemindersWidget() {
  const box = $("#w-reminders");
  if (!box) return;
  try {
    const data = await api("/api/finance/reminders");
    const items = data.reminders || [];
    if (!items.length) {
      box.innerHTML = `<div class="empty-note">Нет срочных платежей 🎉</div>`;
      return;
    }
    box.innerHTML = items.map(r => {
      const cls = r.days_left <= 0 ? "urgent" : "soon";
      const amt = r.amount ? ` · ${Number(r.amount).toLocaleString("ru-RU")} ${r.currency || "₽"}` : "";
      return `<div class="reminder-item ${cls}">
        <span class="reminder-days">${r.urgency}</span>
        <span class="r-main"><span class="r-title">${esc(r.title)}${amt}</span>
        <span class="r-sub">до ${r.due_date}</span></span>
      </div>`;
    }).join("");
  } catch { box.innerHTML = `<div class="muted">Ошибка загрузки</div>`; }
}

// Расписание работы (статичное)
const WORK_SCHEDULE = [
  { day: 1, label: "Пн", time: "8:00–14:00", place: "ЦГКБ №24, поликлиника №1" },
  { day: 2, label: "Вт", time: "14:00–20:00", place: "ЦГКБ №24, поликлиника №1" },
  { day: 3, label: "Ср", time: "14:00–20:00", place: "ЦГКБ №24, поликлиника №1" },
  { day: 4, label: "Чт", time: "8:00–14:00", place: "ЦГКБ №24, поликлиника №1" },
  { day: 5, label: "Пт", time: "14:00–20:00", place: "ЦГКБ №24, поликлиника №1" },
  { day: 6, label: "Сб", time: "выходной", place: "" },
  { day: 0, label: "Вс", time: "выходной", place: "" },
];

function renderScheduleWidget() {
  const todayDay = new Date().getDay(); // 0=Вс, 1=Пн...
  const box = $("#w-schedule");
  if (!box) return;
  box.innerHTML = `<div style="font-size:12px;color:var(--text-3);margin-bottom:8px">🏥 Врач-терапевт · Рижский 16</div>` +
    WORK_SCHEDULE.map((s) => {
      const isToday = s.day === todayDay;
      return `<div class="schedule-row ${isToday ? "today-schedule" : ""}">
        <span class="schedule-day">${s.label}</span>
        <span class="schedule-time">${s.time}</span>
        ${s.place ? `<span class="schedule-place">${isToday ? "📍 " : ""}${s.place}</span>` : ""}
      </div>`;
    }).join("");
}

// Чтение письма в модалке
let _currentMail = null;
function openMailModal(mail) {
  _currentMail = mail;
  const modal = $("#mail-modal");
  $("#modal-subject").textContent = mail.subject || "(без темы)";
  const from = (mail.sender || "").replace(/<.*>/, "").replace(/"/g, "").trim();
  const date = (mail.date || "").slice(0, 19).replace("T", " ");
  $("#modal-meta").textContent = `От: ${from} · ${date} · ${mail.source || ""}`;
  $("#modal-body").textContent = mail.snippet || "(тело письма не загружено — выполните синхронизацию)";
  modal.classList.add("open");
}
$("#modal-close").addEventListener("click", () => $("#mail-modal").classList.remove("open"));
$("#mail-modal").addEventListener("click", (ev) => {
  if (ev.target === $("#mail-modal")) $("#mail-modal").classList.remove("open");
});

// Блокировка отправителя
$("#modal-block-sender").addEventListener("click", async () => {
  if (!_currentMail) return;
  const sender = (_currentMail.sender || "").replace(/<.*>/, "").replace(/"/g, "").trim();
  const domainMatch = sender.match(/@(.+)$/);
  const domain = domainMatch ? domainMatch[1] : sender;
  if (!confirm(`Скрыть ВСЕ письма от ${domain}?`)) return;
  try {
    await api("/api/mail-filters", {
      method: "POST",
      body: JSON.stringify({ kind: "domain", pattern: domain, action: "hide", label: `Заблокирован: ${domain}` }),
    });
    $("#mail-modal").classList.remove("open");
    alert(`✅ Письма от ${domain} больше не будут показываться`);
    // Перезагрузить текущий вид
    const activeView = $(".nav-ico.active");
    if (activeView) loadView(activeView.dataset.view);
  } catch (e) { alert("Ошибка: " + e.message); }
});

// Редактирование задачи — открывает отдельную страницу
window.editTask = function(id) {
  window.open(withToken("/api/tasks/" + id + "/edit-page"), "_blank", "width=560,height=500");
};

// Event delegation для кнопок задач (toggle/edit/delete)
document.addEventListener("click", function(ev) {
  var btn = ev.target.closest("[data-toggle]");
  if (btn) { toggleTask(parseInt(btn.dataset.toggle), "tasks"); return; }
  btn = ev.target.closest("[data-toggle-today]");
  if (btn) { toggleTask(parseInt(btn.dataset.toggleToday), "today"); return; }
  btn = ev.target.closest("[data-edit]");
  if (btn) { editTask(parseInt(btn.dataset.edit), decodeURIComponent(btn.dataset.title), decodeURIComponent(btn.dataset.cat)); return; }
  btn = ev.target.closest("[data-delete]");
  if (btn) { deleteTask(parseInt(btn.dataset.delete)); return; }
});

goto("today");
