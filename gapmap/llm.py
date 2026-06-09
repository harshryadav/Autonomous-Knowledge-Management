"""Optional LLM polish for `ask` and `generate`.

Mirrors the design of `src/qa.py`: the LLM is strictly optional. With
no `openai` package or no API key, callers fall back to deterministic
template output, so every command works offline and in CI.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

MODEL = os.environ.get("GAPMAP_LLM_MODEL", "gpt-4o-mini")


def maybe_complete(system: str, user: str) -> Optional[str]:
    """Return an LLM completion, or None if unavailable / failed."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI  # noqa: WPS433 (optional dependency)
    except ImportError:
        return None
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=900,
            timeout=30.0,
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception as exc:  # any runtime failure -> deterministic fallback
        log.warning("LLM call failed, using template output: %s", exc)
        return None
