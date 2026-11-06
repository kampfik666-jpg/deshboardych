/* Р”Р­РЁР‘РћР Р”Р«Р§Р¬ вЂ” Р»РѕРіРёРєР° РІРµР±-РґР°С€Р±РѕСЂРґР° */

// РўРѕРєРµРЅ РјРёРЅРё-Р°РїРїР°: СЃРѕС…СЂР°РЅСЏРµРј РёР· URL Рё РІРѕСЃСЃС‚Р°РЅР°РІР»РёРІР°РµРј РїСЂРё РїРµСЂРµР·Р°РіСЂСѓР·РєРµ
(function persistToken() {
  try {
    const params = new URLSearchParams(location.search);
    const t = params.get("token");
    if (t) {
      localStorage.setItem("lh_token", t);
      // РЈР±РёСЂР°РµРј С‚РѕРєРµРЅ РёР· Р°РґСЂРµСЃРЅРѕР№ СЃС‚СЂРѕРєРё, С‡С‚РѕР±С‹ РЅРµ СЃРІРµС‚РёР»СЃСЏ
      params.delete("token");
      const q = params.toString();
      history.replaceState(null, "", location.pathname + (q ? "?" + q : ""));
    }
  } catch (e) { /* РїСЂРёРІР°С‚РЅС‹Р№ СЂРµР¶РёРј вЂ” РЅРµ РєСЂРёС‚РёС‡РЅРѕ */ }
})();

// Р•СЃР»Рё РїСЂРёС€С‘Р» 403 (РЅРµС‚ С‚РѕРєРµРЅР°) вЂ” РїСЂРѕР±СѓРµРј РІРѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ РёР· localStorage
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

const MONTHS_GEN = ["СЏРЅРІР°СЂСЏ","С„РµРІСЂР°Р»СЏ","РјР°СЂС‚Р°","Р°РїСЂРµР»СЏ","РјР°СЏ","РёСЋРЅСЏ","РёСЋР»СЏ","Р°РІРіСѓСЃС‚Р°","СЃРµРЅС‚СЏР±СЂСЏ","РѕРєС‚СЏР±СЂСЏ","РЅРѕСЏР±СЂСЏ","РґРµРєР°Р±СЂСЏ"];
const WEEKDAYS = ["РІРѕСЃРєСЂРµСЃРµРЅСЊРµ","РїРѕРЅРµРґРµР»СЊРЅРёРє","РІС‚РѕСЂРЅРёРє","СЃСЂРµРґР°","С‡РµС‚РІРµСЂРі","РїСЏС‚РЅРёС†Р°","СЃСѓР±Р±РѕС‚Р°"];

const CAT_META = {
  inbox: ["рџ“Ґ", "Р’С…РѕРґСЏС‰РёРµ"], work: ["рџ’ј", "Р Р°Р±РѕС‚Р°"], health: ["рџ’Љ", "Р—РґРѕСЂРѕРІСЊРµ"],
  nastya: ["рџЋЂ", "РќР°СЃС‚СЋС€Р°"], shopping: ["рџ›’", "РџРѕРєСѓРїРєРё"], movies: ["рџЋ¬", "Р¤РёР»СЊРјС‹ Рё СЃРµСЂРёР°Р»С‹"],
  games: ["рџЋ®", "РРіСЂС‹"], ideas: ["рџ’Ў", "РРґРµРё"], notes: ["рџ“ќ", "Р—Р°РјРµС‚РєРё"], payments: ["рџ’і", "РџР»Р°С‚РµР¶Рё"],
};
const catLabel = (c) => CAT_META[c] ? `${CAT_META[c][0]} ${CAT_META[c][1]}` : c;

function localTodayISO() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}
let TODAY_ISO = localTodayISO();

// ==================== РќРђР’РР“РђР¦РРЇ ====================
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

// ==================== Р’Р•Р РҐРќРЇРЇ РџРђРќР•Р›Р¬ ====================
function setHeaderDate() {
  const d = new Date();
  $("#today-date").textContent = `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

function setGreeting(name) {
  const h = new Date().getHours();
  let g = "Р”РѕР±СЂС‹Р№ РІРµС‡РµСЂ";
  if (h >= 5 && h < 12) g = "Р”РѕР±СЂРѕРµ СѓС‚СЂРѕ";
  else if (h >= 12 && h < 18) g = "Р”РѕР±СЂС‹Р№ РґРµРЅСЊ";
  else if (h < 5) g = "Р”РѕР±СЂРѕР№ РЅРѕС‡Рё";
  $("#greeting-title").textContent = name ? `${g}, ${name}! вЂпёЏ` : `${g}! вЂпёЏ`;
}

$("#bell-btn").addEventListener("click", () => {
  $("#mail-unread-only").checked = true;
  goto("mail");
});

$("#global-search").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    const q = ev.target.value.trim();
    if (!q) return;
    // РЈРјРЅС‹Р№ РїРѕРёСЃРє РїРѕ РІСЃРµРј РґР°РЅРЅС‹Рј СЃСЂР°Р·Сѓ СЃ РіР»Р°РІРЅРѕР№
    goto("docs");
    const docsBox = $("#doc-list");
    const resultsBox = $("#doc-search-results");
    if (resultsBox) resultsBox.innerHTML = '<div class="muted">РС‰Сѓ РїРѕ РґРѕРєСѓРјРµРЅС‚Р°Рј, Р·Р°РґР°С‡Р°Рј, РїР»Р°С‚РµР¶Р°Рј Рё РїРёСЃСЊРјР°РјвЂ¦</div>';
    doSmartSearch(q, resultsBox);
  }
});

// С†РёС‚Р°С‚Р° РґРЅСЏ РІ СЃР°Р№РґР±Р°СЂРµ
const QUOTES = [
  "В«Р”РёСЃС†РёРїР»РёРЅР° вЂ” СЌС‚Рѕ СЂРµС€РµРЅРёРµ РґРµР»Р°С‚СЊ С‚Рѕ, С‡РµРіРѕ РѕС‡РµРЅСЊ С…РѕС‡РµС‚СЃСЏВ» вЂ” РђРІСЂР°Р°Рј Р›РёРЅРєРѕР»СЊРЅ",
  "В«РЎРґРµР»Р°Р№ СЃРµРіРѕРґРЅСЏ С‚Рѕ, С‡С‚Рѕ РґСЂСѓРіРёРµ РЅРµ С…РѕС‚СЏС‚, вЂ” Р·Р°РІС‚СЂР° Р±СѓРґРµС€СЊ Р¶РёС‚СЊ С‚Р°Рє, РєР°Рє РґСЂСѓРіРёРµ РЅРµ РјРѕРіСѓС‚В»",
  "В«Р›СѓС‡С€РµРµ РІСЂРµРјСЏ РїРѕСЃР°РґРёС‚СЊ РґРµСЂРµРІРѕ Р±С‹Р»Рѕ 20 Р»РµС‚ РЅР°Р·Р°Рґ. Р’С‚РѕСЂРѕРµ Р»СѓС‡С€РµРµ вЂ” СЃРµР№С‡Р°СЃВ»",
  "В«РќРµ Р±РѕР№СЃСЏ РёРґС‚Рё РјРµРґР»РµРЅРЅРѕ, Р±РѕР№СЃСЏ СЃС‚РѕСЏС‚СЊ РЅР° РјРµСЃС‚РµВ»",
  "В«РџРѕСЂСЏРґРѕРє РІ РґРµР»Р°С… вЂ” СЃРІРѕР±РѕРґР° РІ РіРѕР»РѕРІРµВ»",
  "В«РњР°Р»РµРЅСЊРєРёРµ С€Р°РіРё РєР°Р¶РґС‹Р№ РґРµРЅСЊ вЂ” Р±РѕР»СЊС€РёРµ СЂРµР·СѓР»СЊС‚Р°С‚С‹ С‡РµСЂРµР· РіРѕРґВ»",
  "В«Р¤РѕРєСѓСЃ вЂ” СЌС‚Рѕ РёСЃРєСѓСЃСЃС‚РІРѕ РіРѕРІРѕСЂРёС‚СЊ вЂћРЅРµС‚вЂњ С…РѕСЂРѕС€РµРјСѓ СЂР°РґРё Р»СѓС‡С€РµРіРѕВ»",
];
$("#side-quote").title = QUOTES[new Date().getDate() % QUOTES.length];

// ==================== Р“Р›РђР’РќР«Р™ Р­РљР РђРќ ====================
async function loadToday() {
  try {
    const [data, status] = await Promise.all([api("/api/today"), api("/api/status")]);
    TODAY_ISO = data.date;
    setGreeting(data.owner_name || "");
    // РєРѕР»РѕРєРѕР»СЊС‡РёРє
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
  // Р‘Р°РЅРЅРµСЂ В«Р¤РѕРєСѓСЃ РЅР° РіР»Р°РІРЅРѕРјВ» Р·Р°РјРµРЅС‘РЅ РЅР° РїРѕРіРѕРґРЅСѓСЋ РєР°СЂС‚РѕС‡РєСѓ вЂ” С„СѓРЅРєС†РёСЏ РѕСЃС‚Р°РІР»РµРЅР° РїСѓСЃС‚РѕР№ РґР»СЏ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё
}

const DOT_COLORS = ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444", "#0ea5e9"];

function renderEventsWidget(events) {
  const box = $("#w-calendar");
  if (!events || !events.length) {
    box.innerHTML = `<div class="empty-note">РЎРµРіРѕРґРЅСЏ СЃРѕР±С‹С‚РёР№ РЅРµС‚ рџЋ‰</div>`;
    return;
  }
  box.innerHTML = events.slice(0, 6).map((e, i) => {
    const when = e.all_day ? "РІРµСЃСЊ РґРµРЅСЊ" : (e.start_at || "").slice(11, 16);
    return `<div class="row">
      <span class="dot" style="background:${DOT_COLORS[i % DOT_COLORS.length]}"></span>
      <span class="time">${when}</span>
      <span class="r-main"><span class="r-title">${esc(e.title)}</span>
      ${e.location ? `<span class="r-sub">рџ“Ќ ${esc(e.location)}</span>` : ""}</span>
    </div>`;
  }).join("");
}

function renderPrioWidget(dueTasks, openTasks) {
  const box = $("#w-prio");
  const items = [...(dueTasks || []), ...(openTasks || [])].slice(0, 6);
  if (!items.length) {
    box.innerHTML = `<div class="empty-note">РџСЂРёРѕСЂРёС‚РµС‚РѕРІ РЅРµС‚ вЂ” РґРѕР±Р°РІСЊ РїРµСЂРІС‹Р№ вњЁ</div>`;
    return;
  }
  box.innerHTML = items.map((t) => `
    <div class="row ${t.status === "done" ? "done" : ""}">
      <button class="cbox ${t.status === "done" ? "checked" : ""}" data-toggle-today="${t.id}"></button>
      <span class="r-main"><span class="r-title">${esc(t.title)}</span>
      ${t.due_date ? `<span class="r-sub">РґРѕ ${t.due_date}</span>` : ""}</span>
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
    box.innerHTML = `<div class="empty-note">РЎРІРµР¶РёС… РїРёСЃРµРј РЅРµС‚ вњ‰пёЏ</div>`;
    return;
  }
  box.innerHTML = mails.slice(0, 5).map((m, i) => {
    const from = (m.sender || "").replace(/<.*>/, "").replace(/"/g, "").trim() || m.source;
    const t = (m.date || "").slice(11, 16);
    return `<div class="row" style="cursor:pointer" onclick='openMailModal(${JSON.stringify(m).replace(/'/g,"&#39;")})'>
      <span class="mail-ava" style="background:${avaGradient(m.source)};width:30px;height:30px;font-size:12.5px">${esc((from[0] || "?").toUpperCase())}</span>
      <span class="r-main"><span class="r-title">${esc(m.subject || "(Р±РµР· С‚РµРјС‹)")}</span>
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
  // Р›РѕРєР°Р»СЊРЅРѕРµ С„РѕСЂРјР°С‚РёСЂРѕРІР°РЅРёРµ (toISOString СЃРґРІРёРіР°РµС‚ РІ UTC Рё Р»РѕРјР°РµС‚ РґР°С‚С‹)
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
  if (!due) return `<span class="badge later">Р±РµР· СЃСЂРѕРєР°</span>`;
  if (due <= TODAY_ISO) return `<span class="badge today">РЎРµРіРѕРґРЅСЏ</span>`;
  if (due === addDays(TODAY_ISO, 1)) return `<span class="badge tomorrow">Р—Р°РІС‚СЂР°</span>`;
  return `<span class="badge soon">${formatShort(due)}</span>`;
}

function renderTasksTomorrowWidget(nextTasks) {
  const box = $("#w-tasks-tomorrow");
  const tomorrow = addDays(TODAY_ISO, 1);
  // Р¤РёР»СЊС‚СЂСѓРµРј С‚РѕР»СЊРєРѕ Р·Р°РґР°С‡Рё РЅР° Р·Р°РІС‚СЂР°
  const items = (nextTasks || []).filter(t => t.due_date === tomorrow);
  if (!items.length) {
    box.innerHTML = `<div class="empty-note">РќР° Р·Р°РІС‚СЂР° Р·Р°РґР°С‡ РЅРµС‚ рџЋ‰</div>`;
    return;
  }
  box.innerHTML = items.map((t) => `
    <div class="row">
      <button class="cbox" data-toggle-today="${t.id}"></button>
      <span class="r-main"><span class="r-title">${esc(t.title)}</span>
      ${t.due_time ? `<span class="r-sub">вЏ° ${t.due_time}</span>` : ""}</span>
    </div>`).join("");
}

function renderPayWidget(payments) {
  const box = $("#w-pay");
  const items = (payments || []).slice(0, 6);
  if (!items.length) {
    box.innerHTML = `<div class="empty-note">Р‘Р»РёР¶Р°Р№С€РёС… РїР»Р°С‚РµР¶РµР№ РЅРµС‚ рџ’ё</div>`;
    return;
  }
  box.innerHTML = items.map((p) => {
    const amt = p.amount ? `${Number(p.amount).toLocaleString("ru-RU")} ${p.currency || "в‚Ѕ"}` : "";
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
  if (!w) { el.textContent = "РџРѕРіРѕРґР° РЅРµРґРѕСЃС‚СѓРїРЅР°"; return; }
  // РЈР±РёСЂР°РµРј РїСЂРµС„РёРєСЃ "рџЊ¤ РџРѕРіРѕРґР° РІ Рі. Р•РєР°С‚РµСЂРёРЅР±СѓСЂРі: " РґР»СЏ РєРѕРјРїР°РєС‚РЅРѕСЃС‚Рё
  const short = w.replace(/^рџЊ¤\s*РџРѕРіРѕРґР° РІ Рі\.\s*\S+:\s*/, "");
  el.textContent = short;
}

function renderWeatherWidget(w) {
  const box = $("#w-weather");
  if (!w) {
    box.innerHTML = `<div class="empty-note">РџРѕРіРѕРґР° РЅРµ РЅР°СЃС‚СЂРѕРµРЅР° (WEATHER_CITY РІ .env)</div>`;
    return;
  }
  const m = w.match(/РџРѕРіРѕРґР° РІ Рі\. (.+?):\s*(.+?),\s*([+-]?\d+)вЂ¦([+-]?\d+)В°C(?:,\s*(.+))?/);
  if (m) {
    box.innerHTML = `<div class="weather-big">
      <div class="weather-temp">${m[3]}вЂ¦${m[4]}В°</div>
      <div><div class="weather-desc">${esc(m[2])}${m[5] ? " В· " + esc(m[5]) : ""}</div>
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
    { letter: "РЇ", bg: "linear-gradient(135deg,#fc3f1d,#ff8a65)", name: "РЇРЅРґРµРєСЃ 360", on: has("yandex") },
    { letter: "M", bg: "linear-gradient(135deg,#ea4335,#fbbc05)", name: "Gmail", on: has("google") },
    { letter: "рџ“…", bg: "linear-gradient(135deg,#4285f4,#34a853)", name: "Google РљР°Р»РµРЅРґР°СЂСЊ", on: has("google") },
    { letter: "вњ€", bg: "linear-gradient(135deg,#2aabee,#229ed9)", name: "Telegram-Р±РѕС‚", on: !!status.telegram_bot },
    { letter: "AI", bg: "linear-gradient(135deg,#8b5cf6,#5850ec)", name: "РќРµР№СЂРѕСЃРµС‚СЊ", on: !!(status.llm && status.llm.available) },
  ];
  $("#w-services").innerHTML = tiles.map((t) => `
    <div class="svc ${t.on ? "on" : "off"}">
      <div class="svc-logo" style="background:${t.bg}">${t.letter}</div>
      <div class="svc-name">${t.name}</div>
      <div class="svc-status">${t.on ? "СЂР°Р±РѕС‚Р°РµС‚" : "РІС‹РєР»СЋС‡РµРЅ"}</div>
    </div>`).join("");
}

function renderBriefWidget(lb) {
  const box = $("#w-brief");
  if (!lb || !lb.text) {
    box.innerHTML = `<div class="empty-note">Р‘СЂРёС„РёРЅРі РµС‰С‘ РЅРµ РѕС‚РїСЂР°РІР»СЏР»СЃСЏ вЂ” РЅР°Р¶РјРё В«РџСЂРёСЃР»Р°С‚СЊ РІ TelegramВ»</div>`;
    return;
  }
  box.innerHTML = `<div class="brief-date">РџРѕСЃР»РµРґРЅРёР№ Р±СЂРёС„РёРЅРі: ${lb.day}${lb.sent ? " В· РґРѕСЃС‚Р°РІР»РµРЅ РІ Telegram вњ…" : ""}</div>
    <div class="brief-text">${esc(lb.text)}</div>`;
}

$("#btn-send-briefing").addEventListener("click", async (ev) => {
  ev.target.disabled = true;
  ev.target.textContent = "РћС‚РїСЂР°РІР»СЏСЋвЂ¦";
  try {
    await api("/api/briefing/send", { method: "POST" });
    loadToday();
  } catch (e) { alert("РћС€РёР±РєР°: " + e.message); }
  finally { ev.target.disabled = false; ev.target.textContent = "РџСЂРёСЃР»Р°С‚СЊ РІ Telegram вћ”"; }
});

$("#btn-sync").addEventListener("click", async (ev) => {
  ev.target.disabled = true;
  const old = ev.target.textContent;
  ev.target.textContent = "рџ”„ РЎРёРЅС…СЂРѕРЅРёР·РёСЂСѓСЋвЂ¦";
  try { await api("/api/sync", { method: "POST" }); loadToday(); }
  catch (e) { alert("РћС€РёР±РєР°: " + e.message); }
  finally { ev.target.disabled = false; ev.target.textContent = old; }
});

// ==================== РЈРњРќР«Р™ Р—РђРҐР’РђРў ====================
async function doCapture() {
  const input = $("#capture-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  const box = $("#capture-result");
  box.innerHTML = `<div class="cap-card"><div class="cap-head">вњЁ РџРѕРЅРёРјР°СЋ СЃРјС‹СЃР»вЂ¦</div></div>`;
  try {
    const r = await api("/api/inbox", { method: "POST", body: JSON.stringify({ text }) });
    if (r.intent === "question") {
      box.innerHTML = `<div class="cap-card answer">
        <div class="cap-head">вќ“ РћС‚РІРµС‚ В«РІС‚РѕСЂРѕРіРѕ РјРѕР·РіР°В»</div>
        <div class="cap-body">${esc(r.answer)}</div>
        ${r.sources && r.sources.length ? `<div class="cap-src">рџ“љ РСЃС‚РѕС‡РЅРёРєРё: ${r.sources.map(esc).join(", ")}</div>` : ""}
      </div>`;
    } else if (r.intent === "capture") {
      const items = r.items || [];
      const engineNote = r.engine !== "llm" ? " В· СЂР°СЃРїРѕР·РЅР°РЅРѕ Р±РµР· РЅРµР№СЂРѕСЃРµС‚Рё" : "";
      if (items.length <= 1) {
        const it = items[0] || {};
        box.innerHTML = `<div class="cap-card">
          <div class="cap-head">${it.emoji || "рџ“Ґ"} РЎРѕС…СЂР°РЅРёР» РІ В«${esc(it.label || "")}В»${engineNote}</div>
          <div class="cap-body">${esc(it.title || "")}${esc(it.when || "")}</div>
        </div>`;
      } else {
        const list = items.map((it) =>
          `<div style="padding:3px 0">${it.emoji || "рџ“Ґ"} <b>${esc(it.title)}</b> в†’ ${esc(it.label)}${esc(it.when || "")}</div>`
        ).join("");
        box.innerHTML = `<div class="cap-card">
          <div class="cap-head">вњ… Р”РѕР±Р°РІРёР» <b>${items.length}</b> Р·Р°РїРёСЃРµР№${engineNote}</div>
          <div class="cap-body">${list}</div>
        </div>`;
      }
      loadToday();
    } else {
      box.innerHTML = `<div class="cap-card"><div class="cap-body">${esc(r.message || "РќРµ РїРѕРЅСЏР» вЂ” РїРµСЂРµС„РѕСЂРјСѓР»РёСЂСѓР№ рџ™‚")}</div></div>`;
    }
  } catch (e) {
    box.innerHTML = `<div class="cap-card"><div class="cap-body bad-text">РћС€РёР±РєР°: ${esc(e.message)}</div></div>`;
  }
}
$("#capture-send").addEventListener("click", doCapture);
$("#capture-input").addEventListener("keydown", (ev) => { if (ev.key === "Enter") doCapture(); });

// ==================== РљРђР›Р•РќР”РђР Р¬ (РїРѕР»РЅС‹Р№) ====================
let calCurrentDate = localTodayISO();

function formatDateRu(iso) {
  const d = new Date(iso + "T00:00:00");
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()}`;
}

async function loadCalendar() {
  const box = $("#calendar-list");
  const title = $("#cal-date-title");
  if (title) title.textContent = "рџ“… " + formatDateRu(calCurrentDate);
  box.innerHTML = `<div class="muted">Р·Р°РіСЂСѓР·РєР°вЂ¦</div>`;
  try {
    // РџР°СЂР°Р»Р»РµР»СЊРЅР°СЏ Р·Р°РіСЂСѓР·РєР° РІСЃРµС… РґР°РЅРЅС‹С…
    const [eventsData, tasksData, payData] = await Promise.all([
      api("/api/events?days=21"),
      api("/api/tasks"),
      api("/api/obligations?days=1").catch(() => ({ upcoming: [] }))
    ]);

    // Р¤РёР»СЊС‚СЂСѓРµРј СЃРѕР±С‹С‚РёСЏ РґР»СЏ РІС‹Р±СЂР°РЅРЅРѕРіРѕ РґРЅСЏ
    const dayEvents = (eventsData.days || [])
      .filter(d => d.date === calCurrentDate)
      .flatMap(d => d.events);

    // Р—Р°РґР°С‡Рё РЅР° СЌС‚РѕС‚ РґРµРЅСЊ
    const dayTasks = (tasksData.tasks || []).filter(t => t.due_date === calCurrentDate && t.status === "open");

    // РџР»Р°С‚РµР¶Рё РЅР° СЌС‚РѕС‚ РґРµРЅСЊ
    const dayPayments = (payData.upcoming || []).filter(p => p.next_date === calCurrentDate);

    let html = "";

    if (dayEvents.length) {
      html += `<h3 class="sub-title">рџ“… РЎРѕР±С‹С‚РёСЏ</h3>`;
      html += dayEvents.map((e, i) => {
        const when = e.all_day ? "РІРµСЃСЊ РґРµРЅСЊ" : (e.start_at || "").slice(11, 16);
        const loc = e.location ? ` В· ${esc(e.location)}` : "";
        return `<div class="row">
          <span class="dot" style="background:${DOT_COLORS[i % DOT_COLORS.length]}"></span>
          <span class="time">${when}</span>
          <span class="r-main"><span class="r-title">${esc(e.title)}${loc}</span>
          <span class="r-sub">${esc(e.source || "")}${e.cal_name ? " В· " + esc(e.cal_name) : ""}</span></span>
        </div>`;
      }).join("");
    }

    if (dayTasks.length) {
      html += `<h3 class="sub-title">вњ… Р—Р°РґР°С‡Рё РЅР° СЌС‚РѕС‚ РґРµРЅСЊ</h3>`;
      html += dayTasks.map(t => `
        <div class="row">
          <button class="cbox ${t.status === 'done' ? 'checked' : ''}" data-toggle-today="${t.id}"></button>
          <span class="r-main"><span class="r-title">${esc(t.title)}</span>
          <span class="r-sub">${catLabel(t.category)}</span></span>
          ${t.due_time ? `<span class="r-right">вЏ° ${t.due_time}</span>` : ""}
        </div>`).join("");
    }

    if (dayPayments.length) {
      html += `<h3 class="sub-title">рџ’і РџР»Р°С‚РµР¶Рё</h3>`;
      html += dayPayments.map(p => {
        const amt = p.amount ? ` В· ${Number(p.amount).toLocaleString("ru-RU")} ${p.currency || "в‚Ѕ"}` : "";
        return `<div class="row">
          <span class="badge later">${formatShort(p.next_date)}</span>
          <span class="r-main"><span class="r-title">${esc(p.title)}${amt}</span></span>
        </div>`;
      }).join("");
    }

    if (!html) {
      html = `<div class="empty-note">РќР° СЌС‚РѕС‚ РґРµРЅСЊ РЅРёС‡РµРіРѕ РЅРµ Р·Р°РїР»Р°РЅРёСЂРѕРІР°РЅРѕ рџЋ‰<br><br>РќР°РїРёС€Рё РІ СѓРјРЅСѓСЋ СЃС‚СЂРѕРєСѓ РЅР° РіР»Р°РІРЅРѕР№ С‡С‚РѕР±С‹ РґРѕР±Р°РІРёС‚СЊ Р·Р°РґР°С‡Сѓ РёР»Рё СЃРѕР±С‹С‚РёРµ</div>`;
    }

    box.innerHTML = html;
  } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}

// РќР°РІРёРіР°С†РёСЏ РєР°Р»РµРЅРґР°СЂСЏ
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

// Р”РѕР±Р°РІР»РµРЅРёРµ СЃРѕР±С‹С‚РёСЏ/Р·Р°РґР°С‡Рё РЅР° РІС‹Р±СЂР°РЅРЅС‹Р№ РґРµРЅСЊ
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

// ==================== РџРћР§РўРђ (РїРѕР»РЅР°СЏ) ====================
async function loadMail() {
  const onlyUnread = $("#mail-unread-only").checked;
  const box = $("#mail-list");
  box.innerHTML = `<div class="muted">Р·Р°РіСЂСѓР·РєР°вЂ¦</div>`;
  try {
    const data = await api(`/api/mails?limit=80&unread_only=${onlyUnread}`);
    const spamNote = data.spam_count > 0
      ? `<div style="padding:10px 16px;font-size:13px;color:var(--text-4)">рџ›ЎпёЏ РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРё СЃРєСЂС‹С‚Рѕ ${data.spam_count} СЃРїР°Рј-РїРёСЃРµРј</div>` : "";
    if (!data.mails.length) {
      box.innerHTML = spamNote + `<div class="empty-note">РџРёСЃРµРј РЅРµС‚${data.spam_count > 0 ? " (РІРµСЃСЊ РјСѓСЃРѕСЂ РѕС‚С„РёР»СЊС‚СЂРѕРІР°РЅ вњЁ)" : ""}</div>`;
      return;
    }
    box.innerHTML = spamNote + data.mails.map((m) => {
      const from = (m.sender || "").replace(/<.*>/, "").replace(/"/g, "").trim();
      const d = (m.date || "").slice(0, 16).replace("T", " ");
      return `<div class="list-item mail-item ${m.unread ? "unread" : ""}" style="cursor:pointer" onclick='openMailModal(${JSON.stringify(m).replace(/'/g,"&#39;")})'>
        <span class="mail-ava" style="background:${avaGradient(m.source)}">${esc((from[0] || "?").toUpperCase())}</span>
        <span class="li-main">
          <div class="li-title">${esc(m.subject || "(Р±РµР· С‚РµРјС‹)")}${m.unread ? ' <span class="badge today" style="background:#eef2ff;color:#5850ec">РЅРѕРІРѕРµ</span>' : ""}</div>
          <div class="li-sub">${esc(from)} В· ${d} В· ${esc(m.source || "")}</div>
        </span>
      </div>`;
    }).join("");
  } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}
$("#mail-unread-only").addEventListener("change", loadMail);

// ==================== Р—РђР”РђР§Р / РЎРџРРЎРљР ====================
async function loadTasks() {
  var box = document.getElementById("task-list");
  if (!box) return;
  box.innerHTML = '<div class="muted">Р·Р°РіСЂСѓР·РєР°вЂ¦</div>';
  try {
    var data = await api("/api/tasks");
    if (!data.tasks || !data.tasks.length) {
      box.innerHTML = '<div class="empty-note">РџСѓСЃС‚Рѕ. РќР°РїРёС€Рё С‡С‚Рѕ-РЅРёР±СѓРґСЊ РІ СѓРјРЅСѓСЋ СЃС‚СЂРѕРєСѓ РЅР° РіР»Р°РІРЅРѕР№ вњЁ</div>';
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
        var dueHtml = t.due_date ? '<div class="li-sub">РґРѕ ' + esc(t.due_date) + '</div>' : "";
        var safeTitle = t.title.replace(/'/g, "\\'").replace(/"/g, "&quot;");
        html += '<div class="list-item' + doneClass + '">' +
          '<button class="cbox' + checkedClass + '" onclick="toggleTask(' + t.id + ',\'tasks\')"></button>' +
          '<span class="li-main"><div class="li-title">' + esc(t.title) + '</div>' + dueHtml + '</span>' +
          '<button class="mini" onclick="editTask(' + t.id + ')">вњЏпёЏ</button>' +
          '<button class="mini danger" onclick="deleteTask(' + t.id + ')">вњ•</button>' +
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
  if (!confirm("РЈРґР°Р»РёС‚СЊ Р·Р°РїРёСЃСЊ?")) return;
  await api(`/api/tasks/${id}`, { method: "DELETE" });
  loadTasks();
};

// ==================== РџР›РђРўР•Р–Р ====================
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
  if (el) el.textContent = total.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " в‚Ѕ";
}

async function loadPayments() {
  const allBox = $("#obl-all");
  allBox.innerHTML = `<div class="muted">Р·Р°РіСЂСѓР·РєР°вЂ¦</div>`;
  try {
    const data = await api("/api/obligations?days=365");
    renderMonthlyTotal(data.all || []);
    // РЎРѕСЂС‚РёСЂСѓРµРј РїРѕ РґРЅСЋ РјРµСЃСЏС†Р°: СЂР°Р·РѕРІС‹Рµ РїРѕ due_date, РµР¶РµРјРµСЃСЏС‡РЅС‹Рµ РїРѕ day_of_month, РµР¶РµРіРѕРґРЅС‹Рµ РїРѕ month+day
    const sorted = (data.all || []).slice().sort((a, b) => {
      const dayA = a.day_of_month || (a.due_date ? parseInt(a.due_date.slice(8, 10)) : 99);
      const dayB = b.day_of_month || (b.due_date ? parseInt(b.due_date.slice(8, 10)) : 99);
      if (dayA !== dayB) return dayA - dayB;
      // Р•СЃР»Рё РґРµРЅСЊ РѕРґРёРЅР°РєРѕРІС‹Р№ вЂ” СЃРѕСЂС‚РёСЂСѓРµРј РїРѕ РјРµСЃСЏС†Сѓ
      const monA = a.month_of_year || (a.due_date ? parseInt(a.due_date.slice(5, 7)) : 99);
      const monB = b.month_of_year || (b.due_date ? parseInt(b.due_date.slice(5, 7)) : 99);
      return monA - monB;
    });
    allBox.innerHTML = sorted.length
      ? sorted.map(renderOblItem).join("")
      : `<div class="empty-note">РћР±СЏР·Р°С‚РµР»СЊСЃС‚РІ РїРѕРєР° РЅРµС‚ вЂ” РґРѕР±Р°РІСЊ С‡РµСЂРµР· С„РѕСЂРјСѓ РІС‹С€Рµ РёР»Рё РЅР°РїРёС€Рё Р±РѕС‚Сѓ</div>`;
  } catch (e) { allBox.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}

function renderOblItem(o) {
  const when = o.next_date
    ? formatShort(o.next_date)
    : (o.kind === "monthly" ? `${o.day_of_month}-РіРѕ С‡РёСЃР»Р°` : o.kind === "yearly" ? "РµР¶РµРіРѕРґРЅРѕ" : "вЂ”");
  const amt = o.amount ? ` В· ${Number(o.amount).toLocaleString("ru-RU")} ${o.currency || "в‚Ѕ"}` : "";
  const cls = o.overdue ? " overdue" : (o.status !== "active" ? " done" : "");
  return `<div class="list-item${cls}">
    <span class="badge ${o.overdue ? "over" : "later"}">${when}</span>
    <span class="li-main">
      <div class="li-title">${esc(o.title)}${amt}</div>
      ${o.note ? `<div class="li-sub">${esc(o.note)}</div>` : ""}
    </span>
    <button class="mini" onclick="setOblStatus(${o.id}, '${o.status === "active" ? "done" : "active"}')">${o.status === "active" ? "РѕРїР»Р°С‡РµРЅРѕ" : "РІРµСЂРЅСѓС‚СЊ"}</button>
    <button class="mini danger" onclick="deleteObl(${o.id}, '${esc(o.title).replace(/'/g, "\\'")}')">вњ•</button>
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
  if (!confirm(`РЈРґР°Р»РёС‚СЊ РїР»Р°С‚С‘Р¶ В«${title}В»?\n\nР­С‚Рѕ РґРµР№СЃС‚РІРёРµ РЅРµР»СЊР·СЏ РѕС‚РјРµРЅРёС‚СЊ.`)) return;
  await api(`/api/obligations/${id}`, { method: "DELETE" });
  loadPayments();
};

// ==================== Р”РћРљРЈРњР•РќРўР« ====================
async function loadDocs() {
  const box = $("#doc-list");
  box.innerHTML = `<div class="muted">Р·Р°РіСЂСѓР·РєР°вЂ¦</div>`;
  try {
    const data = await api("/api/documents");
    if (!data.documents.length) {
      box.innerHTML = `<div class="empty-note">Р”РѕРєСѓРјРµРЅС‚РѕРІ РЅРµС‚ вЂ” Р·Р°РіСЂСѓР·Рё PDF Р·РґРµСЃСЊ РёР»Рё РїСЂРёС€Р»Рё Р±РѕС‚Сѓ РІ Telegram</div>`;
      return;
    }
    box.innerHTML = data.documents.map((d) => {
      const obl = d.obligations_count ? ` В· РїР»Р°С‚РµР¶РµР№: ${d.obligations_count}` : "";
      return `<div class="list-item">
        <span class="li-main">
          <div class="li-title">рџ“„ ${esc(d.title)}</div>
          <div class="li-sub">${(d.created_at || "").slice(0, 10)} В· ${(d.char_count || 0).toLocaleString("ru-RU")} СЃРёРјРІРѕР»РѕРІ${obl}</div>
        </span>
        <button class="mini danger" onclick="deleteDoc(${d.id})">вњ•</button>
      </div>`;
    }).join("");
  } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}

$("#doc-file").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const status = $("#doc-status");
  status.textContent = "вЏі Р—Р°РіСЂСѓР¶Р°СЋ Рё Р°РЅР°Р»РёР·РёСЂСѓСЋ РґРѕРєСѓРјРµРЅС‚вЂ¦";
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(withToken("/api/documents"), { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (data.duplicate) status.textContent = `в™»пёЏ РЈР¶Рµ СЃРѕС…СЂР°РЅС‘РЅ: В«${data.title}В»`;
    else status.textContent = `вњ… В«${data.title}В» СЃРѕС…СЂР°РЅС‘РЅ. РќР°Р№РґРµРЅРѕ РїР»Р°С‚РµР¶РµР№: ${(data.obligations || []).length}.`;
    loadDocs();
  } catch (e) { status.textContent = "вќЊ " + e.message; }
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
            <div class="src">${esc(r.title)} В· С„СЂР°РіРјРµРЅС‚ ${(r.idx || 0) + 1}</div>
            <div class="frag">${esc(r.text || "")}</div>
          </div>`).join("")
        : `<div class="empty-note">РќРёС‡РµРіРѕ РЅРµ РЅР°С€Р»РѕСЃСЊ</div>`;
    } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
  }, 350);
});

window.deleteDoc = async (id) => {
  if (!confirm("РЈРґР°Р»РёС‚СЊ РґРѕРєСѓРјРµРЅС‚ РёР· Р±Р°Р·С‹?")) return;
  await api(`/api/documents/${id}`, { method: "DELETE" });
  loadDocs();
};

// ==================== РЎРџР РћРЎРРўР¬ ====================
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
  ph.textContent = "РґСѓРјР°СЋвЂ¦";
  log.appendChild(ph);
  try {
    const data = await api("/api/ask", { method: "POST", body: JSON.stringify({ question: q }) });
    let text = data.answer || "(РїСѓСЃС‚Рѕ)";
    if (data.sources && data.sources.length) text += "\n\nрџ“љ РСЃС‚РѕС‡РЅРёРєРё: " + data.sources.join(", ");
    ph.classList.remove("muted");
    ph.textContent = text;
  } catch (e) {
    ph.classList.add("bad-text");
    ph.textContent = "РћС€РёР±РєР°: " + e.message;
  }
  ph.scrollIntoView({ behavior: "smooth", block: "end" });
});

// ==================== РќРђРЎРўР РћР™РљР ====================
async function loadStatus() {
  const box = $("#status-box");
  box.innerHTML = `<div class="muted">Р·Р°РіСЂСѓР·РєР°вЂ¦</div>`;
  try {
    const s = await api("/api/status");
    const rows = [
      ["Telegram-Р±РѕС‚", s.telegram_bot ? "вњ… РїРѕРґРєР»СЋС‡С‘РЅ" : "вќЊ РЅРµ Р·Р°РґР°РЅ BOT_TOKEN"],
      ["Р‘СЂРёС„РёРЅРі", `РєР°Р¶РґС‹Р№ РґРµРЅСЊ РІ ${s.briefing_time} (${s.timezone})`],
      ["РќРµР№СЂРѕСЃРµС‚СЊ", s.llm.available ? `вњ… ${s.llm.model}` : "вќЊ РЅРµ РїРѕРґРєР»СЋС‡РµРЅР°"],
      ["РСЃС‚РѕС‡РЅРёРєРё", s.sources.length ? s.sources.map((x) => `${x.label} (${x.login})`).join(", ") : "РЅРµС‚ вЂ” Р·Р°РїРѕР»РЅРё .env"],
      ["Р’ Р±Р°Р·Рµ", `РґРѕРєСѓРјРµРЅС‚РѕРІ ${s.counts.docs || 0} В· РѕР±СЏР·Р°С‚РµР»СЊСЃС‚РІ ${s.counts.obligations || 0} В· Р·Р°РїРёСЃРµР№ ${s.counts.tasks || 0} В· СЃРѕР±С‹С‚РёР№ ${s.counts.events || 0} В· РїРёСЃРµРј ${s.counts.mails || 0}`],
    ];
    let html = `<div class="card widget wide"><div class="w-head"><span class="w-ico indigo">вљ™пёЏ</span><h3>РЎРѕСЃС‚РѕСЏРЅРёРµ СЃРёСЃС‚РµРјС‹</h3></div>
      ${rows.map(([k, v]) => `<div class="status-row"><span>${k}</span><span>${v}</span></div>`).join("")}</div>`;
    if (s.last_sync && s.last_sync.length) {
      html += `<div class="card widget wide"><div class="w-head"><span class="w-ico blue">рџ”„</span><h3>РџРѕСЃР»РµРґРЅСЏСЏ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ</h3></div>` +
        s.last_sync.map((r) => `<div class="status-row">
          <span>${r.ok ? "вњ…" : "вќЊ"} ${esc(r.source)}/${esc(r.kind)}</span>
          <span>${esc((r.detail || "").slice(0, 80))}</span></div>`).join("") + "</div>";
    }
    box.innerHTML = html;
  } catch (e) { box.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}

// ==================== РўР Р•РљР•Р  РџР РР’Р«Р§Р•Рљ / Р•Р–Р•РќР•Р”Р•Р›Р¬РќР«Р™ РћРўР§РЃРў ====================
async function loadHabits() {
  const grid = document.getElementById("habits-grid");
  const scoreEl = document.getElementById("habits-score");
  if (!grid) return;
  grid.innerHTML = '<div class="muted">Р·Р°РіСЂСѓР·РєР°вЂ¦</div>';
  try {
    const data = await api("/api/habits?days=7");
    if (scoreEl) scoreEl.textContent = `в­ђ Р‘Р»РёР¶Р°Р№С€РёРµ 30 РґРЅРµР№: ${data.score} Р±Р°Р»Р»РѕРІ`;
    if (!data.habits || !data.habits.length) {
      grid.innerHTML = '<div class="empty-note">РџСЂРёРІС‹С‡РµРє РЅРµС‚ вЂ” РґРѕР±Р°РІСЊ РїРµСЂРІСѓСЋ в­ђ<br><br>РћС‚РјРµС‚СЊ РІС‹РїРѕР»РЅРµРЅРёРµ Р·Р° РєР°Р¶РґС‹Р№ РґРµРЅСЊ: РґР»СЏ С…РѕСЂРѕС€РёС… +, РґР»СЏ РїР»РѕС…РёС… в€’</div>';
      return;
    }
    grid.innerHTML = data.habits.map(h => {
      const streakTxt = h.type === "good" ? `рџ”Ґ ${h.streak} РґРЅРµР№ РїРѕРґСЂСЏРґ` : `рџ›ЎпёЏ ${h.streak} РґРЅРµР№ Р±РµР· СЃСЂС‹РІР°`;
      const daysHtml = h.week.map(d => {
        const cls = d.done ? (h.type === "good" ? "done-good" : "done-bad") : "";
        const isToday = d.day === new Date().toISOString().slice(0, 10);
        return `<button class="habit-day ${cls} ${isToday ? "today" : ""}" data-habit="${h.id}" data-day="${d.day}">${d.label}<br>${d.done ? "вњ“" : ""}</button>`;
      }).join("");
      return `<div class="habit-card">
        <div class="habit-emoji">${esc(h.emoji)}</div>
        <div class="habit-info">
          <div class="habit-name">${esc(h.name)}</div>
          <div class="habit-meta">${isGoodType(h.type)} В· ${streakTxt} В· Р·Р° 30 РґРЅРµР№: ${h.total30}</div>
        </div>
        <div class="habit-week">${daysHtml}</div>
        <div class="habit-actions">
          <button class="mini danger" onclick="deleteHabit(${h.id})">вњ•</button>
        </div>
      </div>`;
    }).join("");
  } catch (e) { grid.innerHTML = `<div class="bad-text">${esc(e.message)}</div>`; }
}
function isGoodType(t) { return t === "good" ? "вњ… С…РѕСЂРѕС€Р°СЏ" : "вќЊ РІСЂРµРґРЅР°СЏ"; }

$("#habit-form")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const name = $("#habit-name").value.trim();
  if (!name) return;
  await api("/api/habits", { method: "POST", body: JSON.stringify({
    name, type: $("#habit-type").value, emoji: $("#habit-emoji").value.trim() || "в­ђ",
  })});
  $("#habit-name").value = "";
  loadHabits();
});

// РљР»РёРє РїРѕ РґРЅСЋ вЂ” РїРµСЂРµРєР»СЋС‡РёС‚СЊ РѕС‚РјРµС‚РєСѓ
document.addEventListener("click", async function(ev) {
  var btn = ev.target.closest(".habit-day");
  if (!btn) return;
  var habitId = parseInt(btn.dataset.habit);
  var day = btn.dataset.day;
  var newVal = await api(`/api/habits/${habitId}/toggle`, { method: "POST", body: JSON.stringify({ day }) });
  // РџРµСЂРµРєСЂР°С€РёРІР°РµРј РєРЅРѕРїРєСѓ Р±РµР· РїРѕР»РЅРѕРіРѕ РїРµСЂРµР·Р°РїСѓСЃРєР°
  btn.classList.toggle("done-good", !!newVal.done);
  btn.classList.toggle("done-bad", !!newVal.done && btn.closest(".habit-card")?.querySelector(".habit-meta")?.textContent?.includes("РІСЂРµРґРЅР°СЏ"));
  btn.textContent = (btn.querySelector("br") ? "" : "") + btn.innerHTML; // Р±РµР· РїРµСЂРµСЃР±РѕСЂРєРё С‚РµРєСЃС‚Р°, РїСЂРѕСЃС‚Рѕ РєР»Р°СЃСЃ
  loadHabits();
});

window.deleteHabit = async function(id) {
  if (!confirm("РЈРґР°Р»РёС‚СЊ РїСЂРёРІС‹С‡РєСѓ?")) return;
  await api(`/api/habits/${id}`, { method: "DELETE" });
  loadHabits();
};

// ==================== РЈРњРќР«Р™ РџРћРРЎРљ РџРћ Р’РЎР•Рњ Р”РђРќРќР«Рњ ====================
// РС‰РµС‚ РїРѕ РґРѕРєСѓРјРµРЅС‚Р°Рј, Р·Р°РґР°С‡Р°Рј, РїР»Р°С‚РµР¶Р°Рј Рё РїРёСЃСЊРјР°Рј вЂ” Рё РѕС‚РІРµС‡Р°РµС‚ Р»РёР±Рѕ С‡РµСЂРµР· РЅРµР№СЂРѕСЃРµС‚СЊ, Р»РёР±Рѕ СЃРїРёСЃРєРѕРј.
async function smartSearch(query) {
  const q = query.trim();
  if (!q) return null;
  // 1) Р”РѕРєСѓРјРµРЅС‚С‹ (FTS)
  const docData = await api(`/api/search?q=${encodeURIComponent(q)}&limit=5`).catch(() => ({ results: [] }));
  // 2) Р—Р°РґР°С‡Рё
  const tasksData = await api("/api/tasks").catch(() => ({ tasks: [] }));
  const qLower = q.toLowerCase();
  const taskHits = (tasksData.tasks || []).filter(t =>
    (t.title && t.title.toLowerCase().includes(qLower)) ||
    (t.category && t.category.toLowerCase().includes(qLower))
  ).slice(0, 5);
  // 3) РџР»Р°С‚РµР¶Рё
  const payData = await api("/api/obligations?days=365").catch(() => ({ all: [] }));
  const payHits = (payData.all || []).filter(p =>
    (p.title && p.title.toLowerCase().includes(qLower))
  ).slice(0, 5);
  // 4) РџРёСЃСЊРјР°
  const mailData = await api("/api/mails?limit=30").catch(() => ({ mails: [] }));
  const mailHits = (mailData.mails || []).filter(m =>
    (m.subject && m.subject.toLowerCase().includes(qLower)) ||
    (m.sender && m.sender.toLowerCase().includes(qLower))
  ).slice(0, 5);
  return { docs: docData.results || [], tasks: taskHits, payments: payHits, mails: mailHits };
}

async function doSmartSearch(query, box) {
  const res = await smartSearch(query);
  if (!res) { box.innerHTML = '<div class="empty-note">РџСѓСЃС‚РѕР№ Р·Р°РїСЂРѕСЃ</div>'; return; }
  const { docs, tasks, payments, mails } = res;
  let html = "";
  if (docs.length) {
    html += '<h3 class="sub-title">рџ“„ Р”РѕРєСѓРјРµРЅС‚С‹</h3>';
    html += docs.map(d => `<div class="search-hit"><div class="src">${esc(d.title)} В· С„СЂР°РіРјРµРЅС‚ ${(d.idx||0)+1}</div><div class="frag">${esc((d.text||"").slice(0,300))}</div></div>`).join("");
  }
  if (tasks.length) {
    html += '<h3 class="sub-title">вњ… Р—Р°РґР°С‡Рё</h3>';
    html += tasks.map(t => `<div class="list-item"><span class="li-main"><div class="li-title">${esc(t.title)}</div><div class="li-sub">${catLabel(t.category)}</div></span></div>`).join("");
  }
  if (payments.length) {
    html += '<h3 class="sub-title">рџ’і РџР»Р°С‚РµР¶Рё</h3>';
    html += payments.map(p => `<div class="list-item"><span class="li-main"><div class="li-title">${esc(p.title)}</div><div class="li-sub">${p.next_date || p.due_date || ""}</div></span></div>`).join("");
  }
  if (mails.length) {
    html += '<h3 class="sub-title">рџ“¬ РџРёСЃСЊРјР°</h3>';
    html += mails.map(m => `<div class="list-item"><span class="li-main"><div class="li-title">${esc(m.subject || "(Р±РµР· С‚РµРјС‹)")}</div><div class="li-sub">${esc((m.sender||"").slice(0,60))}</div></span></div>`).join("");
  }
  if (!html) html = '<div class="empty-note">РќРёС‡РµРіРѕ РЅРµ РЅР°С€С‘Р» РїРѕ В«' + esc(query) + 'В». РџРѕРїСЂРѕР±СѓР№ РґСЂСѓРіРѕРµ СЃР»РѕРІРѕ РёР»Рё РѕС‚РїСЂР°РІСЊ РґРѕРєСѓРјРµРЅС‚ Р±РѕС‚Сѓ.</div>';
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
  } catch (e) { /* РЅРµ РєСЂРёС‚РёС‡РЅРѕ */ }
})();

// ==================== Р“РћР›РћРЎРћР’РћР™ Р’Р’РћР” (Web Speech API) ====================
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
    mic.textContent = "рџ”ґ";
    rec.onresult = function (e) {
      var t = e.results[0][0].transcript;
      document.getElementById("capture-input").value = t;
      doCapture();
    };
    rec.onerror = function () {};
    rec.onend = function () {
      mic.classList.remove("recording");
      mic.textContent = "рџЋ¤";
    };
    try { rec.start(); } catch (e) { mic.textContent = "рџЋ¤"; mic.classList.remove("recording"); }
  });
})();

// ==================== РЎРўРђР Рў ====================
setHeaderDate();
$("#prio-form").classList.add("hidden");

// ==================== Р¤РРќРђРќРЎР« ====================
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
  box.innerHTML = `<div class="fin-big-number">${total} в‚Ѕ</div>
    <div class="fin-sub">Р·Р° РїРѕСЃР»РµРґРЅРёРµ ${stats.period_months} РјРµСЃ. В· ${catCount} РєР°С‚РµРіРѕСЂРёР№</div>`;
}

function renderFinMonthly(stats) {
  const box = $("#fin-monthly");
  const months = stats.by_month || [];
  if (!months.length) { box.innerHTML = `<div class="empty-note">РќРµС‚ РґР°РЅРЅС‹С… вЂ” Р·Р°РіСЂСѓР·РёС‚Рµ РІС‹РїРёСЃРєСѓ РёР»Рё РІРєР»СЋС‡РёС‚Рµ СѓРІРµРґРѕРјР»РµРЅРёСЏ РѕС‚ Р±Р°РЅРєР°</div>`; return; }
  const maxVal = Math.max(...months.map(m => m.total), 1);
  const monthNames = ["СЏРЅРІ","С„РµРІ","РјР°СЂ","Р°РїСЂ","РјР°СЏ","РёСЋРЅ","РёСЋР»","Р°РІРі","СЃРµРЅ","РѕРєС‚","РЅРѕСЏ","РґРµРє"];
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
  if (!cats.length) { box.innerHTML = `<div class="empty-note">РќРµС‚ СЂР°СЃС…РѕРґРѕРІ</div>`; return; }
  const maxVal = Math.max(...cats.map(c => c.total), 1);
  const colors = ["#5850ec","#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6","#0ea5e9","#ec4899","#14b8a6","#f97316"];
  box.innerHTML = cats.slice(0, 8).map((c, i) => {
    const pct = Math.max((c.total / maxVal) * 100, 3);
    const val = Number(c.total).toLocaleString("ru-RU", {maximumFractionDigits:0});
    return `<div class="cat-row">
      <span class="cat-name">${esc(c.category)}</span>
      <div class="cat-bar-wrap"><div class="cat-bar-fill" style="width:${pct}%;background:${colors[i%colors.length]}"></div></div>
      <span class="cat-amount">${val} в‚Ѕ</span>
    </div>`;
  }).join("");
}

function renderFinTop(stats) {
  const box = $("#fin-top");
  const top = stats.top_expenses || [];
  if (!top.length) { box.innerHTML = `<div class="empty-note">РќРµС‚ РєСЂСѓРїРЅС‹С… СЂР°СЃС…РѕРґРѕРІ</div>`; return; }
  box.innerHTML = top.map(t => {
    const val = Number(t.amount).toLocaleString("ru-RU", {maximumFractionDigits:0});
    return `<div class="row">
      <span class="badge later">${t.date?.slice(5) || ""}</span>
      <span class="r-main"><span class="r-title">${esc(t.description)}</span>
      <span class="r-sub">${esc(t.category)}</span></span>
      <span class="r-right" style="font-weight:600">${val} в‚Ѕ</span>
    </div>`;
  }).join("");
}

// Р—Р°РіСЂСѓР·РєР° CSV
$("#csv-file")?.addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const status = $("#finance-status");
  status.textContent = "вЏі Р—Р°РіСЂСѓР¶Р°СЋ РІС‹РїРёСЃРєСѓвЂ¦";
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(withToken("/api/finance/upload-csv"), { method: "POST", body: form });
    const data = await res.json();
    status.textContent = `вњ… Р—Р°РіСЂСѓР¶РµРЅРѕ: ${data.added} СЂР°СЃС…РѕРґРѕРІ (${data.duplicates_skipped} РґСѓР±Р»РёРєР°С‚РѕРІ РїСЂРѕРїСѓС‰РµРЅРѕ)`;
    loadFinance();
  } catch (e) { status.textContent = "вќЊ " + e.message; }
  finally { ev.target.value = ""; }
});

// РЎРєР°РЅРёСЂРѕРІР°РЅРёРµ РїРѕС‡С‚С‹ РЅР° СЂР°СЃС…РѕРґС‹
$("#scan-bank-mails")?.addEventListener("click", async (ev) => {
  ev.target.disabled = true;
  const status = $("#finance-status");
  status.textContent = "рџ”Ќ РЎРєР°РЅРёСЂСѓСЋ РїРѕС‡С‚СѓвЂ¦";
  try {
    const data = await api("/api/finance/scan-mails", { method: "POST" });
    status.textContent = data.found > 0
      ? `вњ… РќР°Р№РґРµРЅРѕ ${data.found} РЅРѕРІС‹С… СЂР°СЃС…РѕРґРѕРІ РёР· Р±Р°РЅРєРѕРІСЃРєРёС… РїРёСЃРµРј`
      : "в„№пёЏ РќРѕРІС‹С… СЂР°СЃС…РѕРґРѕРІ РІ РїРѕС‡С‚Рµ РЅРµ РЅР°Р№РґРµРЅРѕ";
    loadFinance();
  } catch (e) { status.textContent = "вќЊ " + e.message; }
  finally { ev.target.disabled = false; }
});

// РќР°РїРѕРјРёРЅР°РЅРёСЏ Рѕ РїР»Р°С‚РµР¶Р°С… РЅР° РіР»Р°РІРЅРѕРј СЌРєСЂР°РЅРµ
async function renderRemindersWidget() {
  const box = $("#w-reminders");
  if (!box) return;
  try {
    const data = await api("/api/finance/reminders");
    const items = data.reminders || [];
    if (!items.length) {
      box.innerHTML = `<div class="empty-note">РќРµС‚ СЃСЂРѕС‡РЅС‹С… РїР»Р°С‚РµР¶РµР№ рџЋ‰</div>`;
      return;
    }
    box.innerHTML = items.map(r => {
      const cls = r.days_left <= 0 ? "urgent" : "soon";
      const amt = r.amount ? ` В· ${Number(r.amount).toLocaleString("ru-RU")} ${r.currency || "в‚Ѕ"}` : "";
      return `<div class="reminder-item ${cls}">
        <span class="reminder-days">${r.urgency}</span>
        <span class="r-main"><span class="r-title">${esc(r.title)}${amt}</span>
        <span class="r-sub">РґРѕ ${r.due_date}</span></span>
      </div>`;
    }).join("");
  } catch { box.innerHTML = `<div class="muted">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>`; }
}

// Р Р°СЃРїРёСЃР°РЅРёРµ СЂР°Р±РѕС‚С‹ (СЃС‚Р°С‚РёС‡РЅРѕРµ)
const WORK_SCHEDULE = [
  { day: 1, label: "РџРЅ", time: "8:00вЂ“14:00", place: "Р¦Р“РљР‘ в„–24, РїРѕР»РёРєР»РёРЅРёРєР° в„–1" },
  { day: 2, label: "Р’С‚", time: "14:00вЂ“20:00", place: "Р¦Р“РљР‘ в„–24, РїРѕР»РёРєР»РёРЅРёРєР° в„–1" },
  { day: 3, label: "РЎСЂ", time: "14:00вЂ“20:00", place: "Р¦Р“РљР‘ в„–24, РїРѕР»РёРєР»РёРЅРёРєР° в„–1" },
  { day: 4, label: "Р§С‚", time: "8:00вЂ“14:00", place: "Р¦Р“РљР‘ в„–24, РїРѕР»РёРєР»РёРЅРёРєР° в„–1" },
  { day: 5, label: "РџС‚", time: "14:00вЂ“20:00", place: "Р¦Р“РљР‘ в„–24, РїРѕР»РёРєР»РёРЅРёРєР° в„–1" },
  { day: 6, label: "РЎР±", time: "РІС‹С…РѕРґРЅРѕР№", place: "" },
  { day: 0, label: "Р’СЃ", time: "РІС‹С…РѕРґРЅРѕР№", place: "" },
];

function renderScheduleWidget() {
  const todayDay = new Date().getDay(); // 0=Р’СЃ, 1=РџРЅ...
  const box = $("#w-schedule");
  if (!box) return;
  box.innerHTML = `<div style="font-size:12px;color:var(--text-3);margin-bottom:8px">рџЏҐ Р’СЂР°С‡-С‚РµСЂР°РїРµРІС‚ В· Р РёР¶СЃРєРёР№ 16</div>` +
    WORK_SCHEDULE.map((s) => {
      const isToday = s.day === todayDay;
      return `<div class="schedule-row ${isToday ? "today-schedule" : ""}">
        <span class="schedule-day">${s.label}</span>
        <span class="schedule-time">${s.time}</span>
        ${s.place ? `<span class="schedule-place">${isToday ? "рџ“Ќ " : ""}${s.place}</span>` : ""}
      </div>`;
    }).join("");
}

// Р§С‚РµРЅРёРµ РїРёСЃСЊРјР° РІ РјРѕРґР°Р»РєРµ
let _currentMail = null;
function openMailModal(mail) {
  _currentMail = mail;
  const modal = $("#mail-modal");
  $("#modal-subject").textContent = mail.subject || "(Р±РµР· С‚РµРјС‹)";
  const from = (mail.sender || "").replace(/<.*>/, "").replace(/"/g, "").trim();
  const date = (mail.date || "").slice(0, 19).replace("T", " ");
  $("#modal-meta").textContent = `РћС‚: ${from} В· ${date} В· ${mail.source || ""}`;
  $("#modal-body").textContent = mail.snippet || "(С‚РµР»Рѕ РїРёСЃСЊРјР° РЅРµ Р·Р°РіСЂСѓР¶РµРЅРѕ вЂ” РІС‹РїРѕР»РЅРёС‚Рµ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЋ)";
  modal.classList.add("open");
}
$("#modal-close").addEventListener("click", () => $("#mail-modal").classList.remove("open"));
$("#mail-modal").addEventListener("click", (ev) => {
  if (ev.target === $("#mail-modal")) $("#mail-modal").classList.remove("open");
});

// Р‘Р»РѕРєРёСЂРѕРІРєР° РѕС‚РїСЂР°РІРёС‚РµР»СЏ
$("#modal-block-sender").addEventListener("click", async () => {
  if (!_currentMail) return;
  const sender = (_currentMail.sender || "").replace(/<.*>/, "").replace(/"/g, "").trim();
  const domainMatch = sender.match(/@(.+)$/);
  const domain = domainMatch ? domainMatch[1] : sender;
  if (!confirm(`РЎРєСЂС‹С‚СЊ Р’РЎР• РїРёСЃСЊРјР° РѕС‚ ${domain}?`)) return;
  try {
    await api("/api/mail-filters", {
      method: "POST",
      body: JSON.stringify({ kind: "domain", pattern: domain, action: "hide", label: `Р—Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ: ${domain}` }),
    });
    $("#mail-modal").classList.remove("open");
    alert(`вњ… РџРёСЃСЊРјР° РѕС‚ ${domain} Р±РѕР»СЊС€Рµ РЅРµ Р±СѓРґСѓС‚ РїРѕРєР°Р·С‹РІР°С‚СЊСЃСЏ`);
    // РџРµСЂРµР·Р°РіСЂСѓР·РёС‚СЊ С‚РµРєСѓС‰РёР№ РІРёРґ
    const activeView = $(".nav-ico.active");
    if (activeView) loadView(activeView.dataset.view);
  } catch (e) { alert("РћС€РёР±РєР°: " + e.message); }
});

// Р РµРґР°РєС‚РёСЂРѕРІР°РЅРёРµ Р·Р°РґР°С‡Рё вЂ” РѕС‚РєСЂС‹РІР°РµС‚ РѕС‚РґРµР»СЊРЅСѓСЋ СЃС‚СЂР°РЅРёС†Сѓ
window.editTask = function(id) {
  window.open(withToken("/api/tasks/" + id + "/edit-page"), "_blank", "width=560,height=500");
};

// Event delegation РґР»СЏ РєРЅРѕРїРѕРє Р·Р°РґР°С‡ (toggle/edit/delete)
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
