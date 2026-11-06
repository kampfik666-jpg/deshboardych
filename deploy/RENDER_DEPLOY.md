# 🚀 Деплой на Render (бесплатно)

> ⚠️ **НИКОГДА не коммить реальные пароли/токены в этот файл.** Реальные значения храни только
> в `.env` (локально) и в Environment-панели Render. Здесь — только названия переменных.

## Вариант А — Public Git Repository (работает при входе через Google/GitHub/любой)

1. Открой https://dashboard.render.com
2. **New +** → **Web Service**
3. Внизу страницы найди поле **Public Git repository** и вставь:
   ```
   https://github.com/kampfik666-jpg/deshboardych
   ```
   Нажми **Continue**
4. Заполни настройки:
   - Name: `deshboardych`
   - Region: **Frankfurt**
   - Branch: `master`
   - Root Directory: пусто
   - Runtime: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python render_start.py`
   - Plan: **Free**
5. Раскрой **Advanced** → **Add Environment Variable** и добавь ключи из списка ниже
6. **Create Web Service**

## Вариант Б — Blueprint (нужен подключённый GitHub)

1. Открой: https://dashboard.render.com/blueprint/new?repo=https://github.com/kampfik666-jpg/deshboardych
2. Если попросят подключить Git-провайдер — нажми **Connect GitHub** и авторизуйся
3. Нажми **Apply** → Render прочитает `render.yaml` и создаст сервис
4. В **Environment** добавь те же переменные, что в Варианте А

## Переменные окружения (Environment)

Значения бери из своего локального `.env` — здесь только имена:

```
BOT_TOKEN=<токен от @BotFather>
TELEGRAM_CHAT_ID=<пусто = берётся из /start>
DATABASE_URL=<строка подключения Neon Postgres>
LLM_API_KEY=<ключ AnyModel/OpenAI>
LLM_BASE_URL=https://anymodel.org/v1
LLM_MODEL=ag/gemini-2.5-flash
YANDEX_ENABLED=true
YANDEX_LOGIN=<почта Яндекса>
YANDEX_MAIL_PASSWORD=<пароль приложения Яндекса>
YANDEX_CALDAV_PASSWORD=<пароль приложения Яндекса для CalDAV>
GOOGLE_ENABLED=true
GOOGLE_EMAIL=<почта Gmail>
GOOGLE_MAIL_PASSWORD=<пароль приложения Google>
GOOGLE_CALDAV_PASSWORD=<пароль приложения Google>
TIMEZONE=Asia/Yekaterinburg
BRIEFING_TIME=06:00
BRIEFING_USE_LLM=true
WEATHER_CITY=Екатеринбург
SYNC_EVERY_MINUTES=30
MAIL_SINCE_DAYS=7
MAIL_FETCH_LIMIT=50
MINIAPP_ENABLED=true
WEB_APP_TOKEN=<пусто = сгенерируется сам>
```

## После деплоя

- Дождись статуса **Live** (сборка 3–5 минут)
- В логах должны появиться строки `Telegram bot started` и `Render URL: ... использую его для мини-аппа`
- Кнопка 🧠 ДЭШБОРДЫЧЬ в меню бота обновится автоматически

## Чтобы сервис не засыпал

Бесплатный Render засыпает через 15 минут без запросов. На https://cron-job.org (бесплатно) создай задачу:
- URL: `https://deshboardych.onrender.com/api/status`
- Интервал: каждые 5 минут
- Метод: GET
