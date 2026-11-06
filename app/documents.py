"""Документы «второго мозга»: загрузка, извлечение текста, чанки, поиск."""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import zipfile
from pathlib import Path

from . import db
from .config import settings

log = logging.getLogger(__name__)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
MAX_TEXT_CHARS = 400_000

SUPPORTED = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "html": "text/html",
    "htm": "text/html",
}

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff"}


class UnsupportedDocument(Exception):
    pass


def extract_text(filename: str, data: bytes) -> str:
    """Извлекает текст из PDF/DOCX/TXT/MD/HTML."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED:
        raise UnsupportedDocument(
            f"Формат .{ext or '?'} пока не поддерживается. Пришли PDF, DOCX, TXT, MD или HTML."
        )
    if ext == "pdf":
        return _extract_pdf(data)
    if ext == "docx":
        return _extract_docx(data)
    if ext in ("html", "htm"):
        return _strip_html(_decode(data))
    return _decode(data)


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedDocument(f"Не удалось прочитать PDF: {exc}") from exc
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:  # noqa: BLE001
            raise UnsupportedDocument("PDF защищён паролем — пришли расшифрованную версию.")
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    text = "\n".join(parts).strip()
    if not text:
        # Сканированный PDF — возвращаем пустой текст, документ сохранится.
        # OCR через vision-модель будет выполнен в add_document.
        log.info("PDF без текстового слоя (скан). Будет распознан через vision-модель.")
        return ""
    return text


async def _ocr_pdf_pages(data: bytes, filename: str, max_pages: int = 10) -> str:
    """Распознаёт сканированный PDF через vision-модель (страница за страницей)."""
    import base64
    from .llm import llm
    from .config import settings

    if not llm.available:
        return "[Сканированный PDF сохранён. Подключите LLM для распознавания.]"

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return "[Не удалось прочитать PDF для OCR.]"

    pages_text = []
    for i, page in enumerate(reader.pages[:max_pages]):
        try:
            # Конвертируем страницу в изображение через pdf2image или рендер
            # Простой подход: отправляем первую страницу как base64 JPEG
            # Для полноценного OCR нужен pdf2image + poppler, но это тяжёлая зависимость.
            # Альтернатива: используем pypdf для извлечения embedded images
            images = page.images if hasattr(page, 'images') else []
            if images:
                img_data = images[0].data
                b64 = base64.b64encode(img_data).decode()
                mime = "image/jpeg"

                vision_models = ["ag/gemini-2.5-flash", "qwen/qwen3.8-27b", settings.llm_model]
                seen = set()
                for model in vision_models:
                    if model in seen:
                        continue
                    seen.add(model)
                    try:
                        from openai import AsyncOpenAI
                        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
                        resp = await asyncio.wait_for(
                            client.chat.completions.create(
                                model=model,
                                messages=[{
                                    "role": "user",
                                    "content": [
                                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                                        {"type": "text", "text": "Извлеки ВЕСЬ текст с этой страницы документа. Сохрани форматирование. Отвечай на русском."},
                                    ],
                                }],
                                max_tokens=3000,
                                temperature=0.1,
                            ),
                            timeout=120,
                        )
                        text = (resp.choices[0].message.content or "").strip()
                        if text:
                            pages_text.append(f"--- Страница {i+1} ---\n{text}")
                            log.info("OCR page %d by %s (%d chars)", i+1, model, len(text))
                            break
                    except Exception as exc:  # noqa: BLE001
                        log.debug("Vision OCR page %d failed with %s: %s", i+1, model, exc)
                        continue
        except Exception as exc:  # noqa: BLE001
            log.debug("OCR page %d error: %s", i+1, exc)
            continue

    if pages_text:
        return "\n\n".join(pages_text)
    return "[Сканированный PDF сохранён, но не удалось распознать содержимое. Попробуйте отправить как фото.]"


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except zipfile.BadZipFile as exc:
        raise UnsupportedDocument("Файл повреждён или это не DOCX.") from exc


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def _describe_image(data: bytes, filename: str) -> str:
    """Распознаёт изображение через vision-модель и возвращает текстовое описание."""
    import base64
    from .llm import llm
    from .config import settings

    if not llm.available:
        return "[Изображение сохранено. Подключите LLM для распознавания содержимого.]"

    ext = Path(filename).suffix.lower().lstrip(".")
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp", "tiff": "image/tiff"}
    mime = mime_map.get(ext, "image/jpeg")
    b64 = base64.b64encode(data).decode()

    # Пробуем модели с поддержкой изображений
    vision_models = ["ag/gemini-2.5-flash", "qwen/qwen3.8-27b", settings.llm_model]
    seen = set()
    for model in vision_models:
        if model in seen:
            continue
        seen.add(model)
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                            {"type": "text", "text": (
                                "Опиши подробно что изображено на этой картинке. "
                                "Если это документ/квитанция/договор — извлеки весь текст. "
                                "Если это фото — опиши объекты, людей, текст на фото. "
                                "Отвечай на русском языке."
                            )},
                        ],
                    }],
                    max_tokens=2000,
                    temperature=0.2,
                ),
                timeout=120,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                log.info("Image described by %s (%d chars)", model, len(text))
                return f"[Описание изображения ({filename})]\n\n{text}"
        except Exception as exc:  # noqa: BLE001
            log.debug("Vision model %s failed: %s", model, exc)
            continue

    return f"[Изображение {filename} сохранено, но не удалось распознать содержимое.]"


def normalize(text: str) -> str:
    text = text[:MAX_TEXT_CHARS]
    return re.sub(r"[ \t]+", " ", text).strip()


def chunk_text(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            # стараемся рвать по границе предложения/строки
            cut = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if cut > start + CHUNK_SIZE // 2:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return [c for c in chunks if c]


async def add_document(
    filename: str,
    data: bytes,
    source: str = "upload",
    extract_obligations: bool = True,
) -> dict:
    """Сохраняет документ, индексирует текст и ищет в нём обязательства/платежи.

    Поддерживает: PDF, DOCX, TXT, MD, HTML, а также изображения (JPG/PNG/GIF/WEBP).
    Изображения распознаются через vision-модель.
    Сканированные PDF тоже сохраняются — просто без текстового поиска.
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    is_image = ext in IMAGE_EXTENSIONS

    if is_image:
        text = await _describe_image(data, filename)
    else:
        try:
            text = normalize(extract_text(filename, data))
        except UnsupportedDocument as exc:
            log.warning("Не удалось извлечь текст из %s: %s. Сохраняем без текста.", filename, exc)
            text = ""

    # Если PDF без текста (скан) — пробуем OCR через vision
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext == "pdf" and not text.strip():
        log.info("Запускаю OCR для сканированного PDF: %s", filename)
        text = await _ocr_pdf_pages(data, filename)
    sha = hashlib.sha256(data).hexdigest()
    dup = db.query_one("SELECT id, title FROM documents WHERE sha256 = ?", (sha,))
    if dup:
        return {"id": dup["id"], "title": dup["title"], "duplicate": True, "obligations": []}

    # Локально сохраняем оригинал на диск (на сервере с Postgres — в БД)
    if not db.IS_POSTGRES:
        updir: Path = settings.abs_upload_dir()
        updir.mkdir(parents=True, exist_ok=True)
        stored = updir / f"{sha[:16]}_{Path(filename).name}"
        stored.write_bytes(data)

    title = Path(filename).stem.replace("_", " ").strip() or filename
    doc_id = db.execute(
        "INSERT INTO documents(title, filename, mime, size, sha256, source, char_count, file_data, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            title,
            Path(filename).name,
            SUPPORTED.get(Path(filename).suffix.lower().lstrip("."), ""),
            len(data),
            sha,
            source,
            len(text),
            data,  # сохраняем оригинал в БД (для сервера с эфемерным диском)
            db.utcnow(),
        ),
    )
    chunks = chunk_text(text)
    for idx, chunk in enumerate(chunks):
        chunk_id = db.execute(
            "INSERT INTO doc_chunks(doc_id, idx, text) VALUES(?,?,?)", (doc_id, idx, chunk)
        )
        if db.fts_available():
            db.execute(
                "INSERT INTO doc_fts(chunk_id, doc_id, text) VALUES(?,?,?)",
                (str(chunk_id), str(doc_id), chunk),
            )

    found: list[dict] = []
    if extract_obligations:
        from . import obligations as obl

        found = await obl.extract_from_document(doc_id, text, title)

    return {
        "id": doc_id,
        "title": title,
        "duplicate": False,
        "char_count": len(text),
        "chunks": len(chunks),
        "obligations": found,
    }


def search(query_text: str, limit: int = 12) -> list[dict]:
    """Полнотекстовый поиск по чанкам документов."""
    query_text = query_text.strip()
    if not query_text:
        return []
    if db.fts_available():
        match = " ".join(
            f'"{w}"*' for w in re.findall(r"[\w\-]{2,}", query_text.lower())
        )
        if match:
            rows = db.query(
                "SELECT c.doc_id, c.idx, c.text, d.title, "
                "       bm25(doc_fts) AS rank "
                "FROM doc_fts JOIN doc_chunks c ON c.id = CAST(doc_fts.chunk_id AS INTEGER) "
                "JOIN documents d ON d.id = c.doc_id "
                "WHERE doc_fts MATCH ? ORDER BY rank LIMIT ?",
                (match, limit),
            )
            if rows:
                return rows
    # Fallback: LIKE-поиск по словам
    words = re.findall(r"[\w\-]{3,}", query_text.lower())
    if not words:
        return []
    conds = " OR ".join("LOWER(c.text) LIKE ?" for _ in words)
    params: list = [f"%{w}%" for w in words]
    params.append(limit)
    return db.query(
        f"SELECT c.doc_id, c.idx, c.text, d.title, 0 AS rank "
        f"FROM doc_chunks c JOIN documents d ON d.id = c.doc_id "
        f"WHERE {conds} LIMIT ?",
        params,
    )


def list_documents(limit: int = 100) -> list[dict]:
    return db.query(
        "SELECT d.id, d.title, d.filename, d.source, d.char_count, d.created_at, "
        "       (SELECT COUNT(*) FROM obligations o WHERE o.doc_id = d.id) AS obligations_count "
        "FROM documents d ORDER BY d.created_at DESC LIMIT ?",
        (limit,),
    )


def get_document(doc_id: int) -> dict | None:
    return db.query_one("SELECT * FROM documents WHERE id = ?", (doc_id,))


def get_document_text(doc_id: int) -> str:
    rows = db.query(
        "SELECT text FROM doc_chunks WHERE doc_id = ? ORDER BY idx", (doc_id,)
    )
    return "\n".join(r["text"] for r in rows)


def delete_document(doc_id: int) -> None:
    if db.fts_available():
        db.execute("DELETE FROM doc_fts WHERE CAST(doc_id AS INTEGER) = ?", (doc_id,))
    db.execute("DELETE FROM doc_chunks WHERE doc_id = ?", (doc_id,))
    db.execute("UPDATE obligations SET doc_id = NULL WHERE doc_id = ?", (doc_id,))
    doc = get_document(doc_id)
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    if doc and not db.IS_POSTGRES:
        # удаляем сохранённый файл
        updir = settings.abs_upload_dir()
        for f in updir.glob(f"{(doc['sha256'] or '')[:16]}_*"):
            try:
                f.unlink()
            except OSError:
                pass
