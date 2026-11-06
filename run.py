"""Точка входа ДЭШБОРДЫЧА: веб + бот + планировщик + мини-апп туннель.

С автоматическим перезапуском при сбоях — приложение должно жить всегда.
"""
import time

from app.main import run as _run, log


def main() -> None:
    attempt = 0
    while True:
        try:
            _run()
            # serve() завершился штатно (например, Ctrl+C) — выходим
            break
        except KeyboardInterrupt:
            log.info("Остановка по Ctrl+C")
            break
        except Exception:
            attempt += 1
            log.exception("Сбой приложения (попытка %d) — перезапуск через 5 секунд…", attempt)
            time.sleep(5)


if __name__ == "__main__":
    main()
