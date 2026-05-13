"""
Base agent — wraps the Ollama HTTP API.
All agents inherit from this. Every call enforces JSON output format
and retries on transient failures.
"""

import json
import logging
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from src.config.settings import settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    pass


class BaseAgent:
    def __init__(self, task: str, model: str, system_prompt: str):
        self.task = task
        self.model = model
        self.system_prompt = system_prompt
        self.base_url = settings.ollama.base_url
        self.timeout = settings.ollama.timeout_seconds

    # ── Internal HTTP call ────────────────────────────────────────────

    def _call_ollama(self, user_prompt: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": 0.75,
                "top_p": 0.9,
            },
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama HTTP error [{self.task}]: {exc}") from exc

        raw = resp.json()
        content = raw.get("message", {}).get("content", "")

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("[%s] JSON parse failed, retrying: %s", self.task, content[:200])
            raise OllamaError(f"JSON parse error [{self.task}]: {exc}") from exc

    # ── Public interface ──────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(OllamaError),
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        reraise=True,
    )
    def call(self, user_prompt: str) -> dict[str, Any]:
        """Call the model and return a parsed JSON dict. Retries 3x on failure."""
        logger.debug("[%s] calling model=%s", self.task, self.model)
        result = self._call_ollama(user_prompt)
        logger.debug("[%s] response keys: %s", self.task, list(result.keys()))
        return result
