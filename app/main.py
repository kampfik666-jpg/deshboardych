from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import sys
import urllib.request
from pathlib import Path

import uvicorn

from app.api import api, get_web_token
from app.config import BASE_DIR, settings
from app import db
from app.scheduler import start_scheduler, stop_scheduler
from app.telegram_bot import build_application

# Логи: на сервере — в stdout, локально — ещё и в файл
_handlers: list[logging.Handler] = []
if os.getenv("RENDER") or os.getenv("PORT"):
    _handlers.append(logging.StreamHandler(sys.stdout if sys.stdout else sys.stderr))
else:
    _handlers.append(
        logging.FileHandler(settings.abs_db_path().parent / "lifehub.log", encoding="utf-8", delay=True)
    )
    if sys.stdout is not None:
        _handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=_handlers,
)
log = logging.getLogger("lifehub")
logging.getLogger("httpx").setLevel(logging.WARNING)

IS_WINDOWS = sys.platform == "win32"
CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if IS_WINDOWS else
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
)
CLOUDFLARED_BIN = "cloudflared.exe" if IS_WINDOWS else "cloudflared"
TUNNEL_URL_RE = re.compile(rb"https://[a-z0-9\-]+\.trycloudflare\.com")


async def ensure_cloudflared() -> Path | None:
    bin_dir = BASE_DIR / "bin"
    exe = bin_dir / CLOUDFLARED_BIN
    if exe.exists():
        return exe
    bin_dir.mkdir(parents=True, exist_ok=True)
    log.info("Скачиваю cloudflared…")
    try:
        await asyncio.to_thread(urllib.request.urlretrieve, CLOUDFLARED_URL, exe)
        if not IS_WINDOWS:
            exe.chmod(0o755)
        log.info("cloudflared скачан: %s", exe)
        return exe
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось скачать cloudflared (%s)", exc)
        exe.unlink(missing_ok=True)
        return None


async def start_tunnel():
    exe = await ensure_cloudflared()
    if exe is None:
        return None, None
    try:
        proc = await asyncio.create_subprocess_exec(
            str(exe), "tunnel", "--url", f"http://127.0.0.1:{_web_port()}",
            "--no-autoupdate",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось запустить cloudflared: %s", exc)
        return None, None

    url = None

    async def drain():
        nonlocal url
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            m = TUNNEL_URL_RE.search(line)
            if m and url is None:
                url = m.group(0).decode()
                log.info("Публичный туннель: %s", url)

    drain_task = asyncio.create_task(drain())
    for _ in range(90):
        if url:
            break
        if proc.returncode is not None:
            return None, None
        await asyncio.sleep(1)
    return (proc, drain_task), url


def _web_port() -> int:
    return int(os.getenv("PORT", settings.web_port))


async def set_miniapp_button(bot, public_url: str) -> None:
    try:
        from telegram import WebAppInfo
        from telegram._menubutton import MenuButtonWebApp

        token = get_web_token()
        app_url = f"{public_url}/?token={token}"
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="🧠 ДЭШБОРДЫЧЬ", web_app=WebAppInfo(url=app_url))
        )
        log.info("Мини-апп установлен: %s/?token=…", public_url)
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось установить кнопку мини-аппа: %s", exc)


async def main() -> None:
    settings.abs_db_path().parent.mkdir(parents=True, exist_ok=True)
    settings.abs_upload_dir().mkdir(parents=True, exist_ok=True)
    db.init_db()
    log.info("Database ready (postgres=%s, FTS5=%s)", db.IS_POSTGRES, db.fts_available())

    tg_app = build_application()
    if tg_app is not None:
        await tg_app.initialize()
        await tg_app.start()
        try:
            await tg_app.updater.start_polling(drop_pending_updates=True)
            log.info("Telegram bot started")
        except Exception as exc:  # noqa: BLE001
            log.error("Telegram polling failed: %s", exc)

    start_scheduler()

    port = _web_port()
    host = "0.0.0.0" if os.getenv("PORT") else settings.web_host
    config = uvicorn.Config(api, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    log.info("Dashboard: http://%s:%d", host, port)

    tunnel = None
    drain_task = None

    async def start_miniapp_when_ready():
        nonlocal tunnel, drain_task
        while not server.started:
            await asyncio.sleep(0.5)
        # На Render — используем встроенный HTTPS URL (без туннеля)
        render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        if render_url:
            log.info("Render URL: %s — использую его для мини-аппа (без туннеля)", render_url)
            if tg_app is not None:
                await set_miniapp_button(tg_app.bot, render_url)
            return
        (tunnel, drain_task), url = await start_tunnel()
        if url and tg_app is not None:
            await set_miniapp_button(tg_app.bot, url)

    miniapp_task = asyncio.create_task(start_miniapp_when_ready()) if settings.miniapp_enabled else None

    try:
        await server.serve()
    finally:
        stop_scheduler()
        if miniapp_task is not None:
            miniapp_task.cancel()
        if drain_task is not None:
            drain_task.cancel()
        if tunnel is not None:
            with contextlib.suppress(Exception):
                tunnel.terminate()
        if tg_app is not None:
            with contextlib.suppress(Exception):
                await tg_app.updater.stop()
            with contextlib.suppress(Exception):
                await tg_app.stop()
            with contextlib.suppress(Exception):
                await tg_app.shutdown()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
