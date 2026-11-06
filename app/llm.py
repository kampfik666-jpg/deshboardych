"""Клиент к любому OpenAI-совместимому LLM API."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .config import settings

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self._client = None

    @property
    def available(self) -> bool:
        return settings.llm_available

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url or None,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1500,
    ) -> str | None:
        """Возвращает текст ответа или None, если LLM недоступна/ошибка."""
        if not self.available:
            return None
        try:
            resp = await self._get_client().chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM request failed: %s", exc)
            return None

    async def json(self, prompt: str, system: str | None = None) -> Any:
        """Просит модель вернуть JSON и парсит его. None при неудаче."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        raw = await self.chat(messages, temperature=0.1, max_tokens=2000)
        if not raw:
            return None
        return parse_json(raw)


def parse_json(raw: str) -> Any:
    """Достаёт JSON из ответа модели (возможно в ```json ... ``` обёртке)."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Попробуем найти первую {...} или [...] скобку
        for opener, closer in (("[", "]"), ("{", "}")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
    log.warning("Failed to parse JSON from LLM response: %.200s", raw)
    return None


llm = LLMClient()
