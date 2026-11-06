"""Распознавание голосовых сообщений (офлайн, sherpa-onnx + ffmpeg).

Полностью бесплатно и без интернета: модель скачивается один раз (~60 МБ)
из релизов GitHub (быстро даже из РФ).
"""
from __future__ import annotations

import logging
import subprocess
import tarfile
import threading
import urllib.request
from pathlib import Path

from .config import BASE_DIR

log = logging.getLogger(__name__)

MODEL_NAME = "sherpa-onnx-zipformer-ru-int8-2025-04-20"
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    f"{MODEL_NAME}.tar.bz2"
)
MODEL_DIR = BASE_DIR / "data" / MODEL_NAME

_recognizer = None
_lock = threading.Lock()
_failed = False


def _download_model() -> None:
    """Скачивает и распаковывает русскую модель (один раз, ~60 МБ)."""
    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    archive = MODEL_DIR.parent / f"{MODEL_NAME}.tar.bz2"
    log.info("Скачиваю модель распознавания речи: %s", MODEL_URL)
    urllib.request.urlretrieve(MODEL_URL, archive)
    log.info("Распаковываю модель…")
    with tarfile.open(archive, "r:bz2") as tf:
        tf.extractall(MODEL_DIR.parent)
    archive.unlink(missing_ok=True)
    log.info("Модель готова: %s", MODEL_DIR)


def _find_file(pattern: str) -> Path | None:
    matches = sorted(MODEL_DIR.glob(pattern))
    if not matches:
        return None
    # предпочитаем int8-вариант
    for m in matches:
        if "int8" in m.name:
            return m
    return matches[0]


def _get_recognizer():
    global _recognizer, _failed
    if _recognizer is not None or _failed:
        return _recognizer
    with _lock:
        if _recognizer is not None or _failed:
            return _recognizer
        try:
            if not MODEL_DIR.exists():
                _download_model()

            tokens = MODEL_DIR / "tokens.txt"
            encoder = _find_file("encoder*.onnx")
            decoder = _find_file("decoder*.onnx")
            joiner = _find_file("joiner*.onnx")
            if not (tokens.exists() and encoder and decoder and joiner):
                raise FileNotFoundError(
                    f"Файлы модели не найдены в {MODEL_DIR} "
                    f"(tokens={tokens.exists()}, enc={encoder}, dec={decoder}, join={joiner})"
                )

            import sherpa_onnx

            kwargs = {}
            bpe_model = MODEL_DIR / "bpe.model"
            if bpe_model.exists():
                kwargs["modeling_unit"] = "bpe"
                kwargs["bpe_vocab"] = str(bpe_model)

            _recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                tokens=str(tokens),
                encoder=str(encoder),
                decoder=str(decoder),
                joiner=str(joiner),
                num_threads=2,
                sample_rate=16000,
                feature_dim=80,
                decoding_method="greedy_search",
                **kwargs,
            )
            log.info("Speech recognizer loaded: %s", MODEL_NAME)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось загрузить модель распознавания речи")
            _failed = True
    return _recognizer


def model_status() -> str:
    """Для диагностики."""
    if _recognizer is not None:
        return "loaded"
    if _failed:
        return "failed"
    return "not loaded yet"


def _ogg_to_pcm16(ogg_bytes: bytes) -> bytes:
    """Конвертирует OGG/Opus (формат Telegram) в raw PCM 16 кГц моно через ffmpeg."""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
        input=ogg_bytes,
        capture_output=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {proc.stderr.decode(errors='replace')[:200]}")
    return proc.stdout


def transcribe(ogg_bytes: bytes) -> str:
    """Распознаёт речь из OGG-байтов. Возвращает текст (может быть пустым).

    Синхронная и тяжёлая — вызывать из async через asyncio.to_thread.
    """
    recognizer = _get_recognizer()
    if recognizer is None:
        raise RuntimeError("Модель распознавания недоступна (см. логи)")

    pcm = _ogg_to_pcm16(ogg_bytes)
    return _transcribe_pcm(recognizer, pcm)


def _transcribe_pcm(recognizer, pcm: bytes) -> str:
    """Распознаёт raw PCM s16le 16 кГц моно."""
    import numpy as np

    if not pcm:
        return ""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, samples)
    recognizer.decode_stream(stream)
    return (stream.result.text or "").strip()


def transcribe_wav_bytes(wav_bytes: bytes) -> str:
    """Для тестов: распознаёт WAV напрямую (через ffmpeg для унификации)."""
    recognizer = _get_recognizer()
    if recognizer is None:
        raise RuntimeError("Модель недоступна")
    pcm = _ogg_to_pcm16(wav_bytes)  # ffmpeg сам разберётся с WAV
    return _transcribe_pcm(recognizer, pcm)
