"""One place that talks to the AI model, so the rest of the app never depends on it.

Every caller gets `None` back when there's no API key or the call fails, and falls back to
a rule-based method. The model is asked to answer through a tool with a JSON schema, so the
reply is structured data, not free text to parse.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

log = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(get_settings().anthropic_api_key)


@lru_cache
def _client():
    import anthropic

    s = get_settings()
    return anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.ai_timeout_seconds, max_retries=1)


def structured(
    system: str, content: list[dict[str, Any]], tool: dict[str, Any], max_tokens: int = 1024
) -> dict | None:
    """Ask the model to fill in `tool`'s input schema. Returns the filled-in dict, or None."""
    if not enabled():
        return None
    try:
        msg = _client().messages.create(
            model=get_settings().ai_model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": content}],
        )
        for block in msg.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        log.warning("ai: no tool_use block in the reply")
    except Exception as e:  # network, auth, rate limit, timeout: never break the request
        log.warning("ai: call failed (%s), using the fallback", type(e).__name__)
    return None
