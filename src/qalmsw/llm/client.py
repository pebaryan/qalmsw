"""LLM client abstraction.

`LLMClient` is a Protocol so checkers depend on the interface, not the backend.
`LlamaCppClient` talks to a local llama.cpp server via its OpenAI-compatible API.
Tests mock `LLMClient` directly.
"""
from __future__ import annotations

import json
import os
import re
from typing import Protocol

from openai import OpenAI

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _extract_json(text: str) -> str:
    """Strip common wrappers small local models add around JSON output."""
    m = _FENCE_RE.match(text)
    if m:
        return m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        return text[start : end + 1]
    return text


def _parse_lenient_json(text: str) -> dict:
    """Parse LLM JSON output, falling back when bare backslashes appear.

    Small models routinely quote LaTeX commands (``\\cite``, ``\\section``) inside JSON
    strings without doubling the backslash, which breaks strict JSON. On failure we retry
    with all backslashes doubled. Our excerpts are short LaTeX snippets, so legitimate
    ``\\n`` / ``\\t`` escapes would be rare and the tradeoff is worth the robustness.
    """
    extracted = _extract_json(text)
    try:
        return json.loads(extracted)
    except json.JSONDecodeError:
        return json.loads(extracted.replace("\\", "\\\\"))


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


class LlamaCppClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> None:
        self._client = OpenAI(
            base_url=base_url or os.environ.get("QALMSW_BASE_URL", "http://localhost:8080/v1"),
            api_key="not-needed",
        )
        self._model = model or os.environ.get("QALMSW_MODEL", "local-model")
        self._temperature = temperature

    def complete_json(self, system: str, user: str) -> dict:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self._temperature,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        return _parse_lenient_json(content)
