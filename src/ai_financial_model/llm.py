# About: Anthropic SDK wrapper for LLM-driven extraction.
#
# Lazy client init: importing this module does not require ANTHROPIC_API_KEY.
# Calls fall back to None on any error so the pipeline degrades gracefully
# when LLM access isn't available — `forward_guidance.*` cells in the model
# simply land as NO_VALUE_EXTRACTED, the rest of the pipeline carries on.
#
# Caching strategy: top-level `cache_control={"type": "ephemeral"}` auto-caches
# the last cacheable block (system prompt + tool schema). The variable user
# content (the document being extracted) is never cached. After the first
# call, subsequent calls within the 5-minute TTL pay ~10% of input tokens
# for the cached prefix.

from __future__ import annotations
import logging
import os
from typing import Any, Optional

# Default to Sonnet 4.6 — price/performance sweet spot for structured extraction.
# Override via env var CLAUDE_MODEL.
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

logger = logging.getLogger(__name__)
_client = None


def _get_client():
    """Lazy client initialization. Defers Anthropic() construction (which
    requires ANTHROPIC_API_KEY) until the first call so importing this module
    in a test or CI without the key is safe."""
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()
    return _client


def extract_via_tool(
    *,
    system: str,
    user_content: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
) -> Optional[dict[str, Any]]:
    """Force-use a tool with strict schema validation; return its `input` dict.

    The system prompt and tool schema are cached (5-minute TTL); user content
    is never cached. Returns None on:
      - missing ANTHROPIC_API_KEY
      - network / rate-limit / 5xx errors (after SDK auto-retry)
      - the model refusing or returning no tool_use block

    Callers should treat None as a soft failure — log and proceed with empty
    extraction.
    """
    try:
        client = _get_client()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            tools=[{
                "name": tool_name,
                "description": tool_description,
                "strict": True,
                "input_schema": input_schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
            cache_control={"type": "ephemeral"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return dict(block.input)
        logger.warning(
            "LLM extraction returned no tool_use block (model=%s, stop_reason=%s)",
            model, getattr(response, "stop_reason", "unknown"),
        )
        return None
    except Exception as e:
        logger.warning("LLM extraction failed: %s: %s", type(e).__name__, e)
        return None
