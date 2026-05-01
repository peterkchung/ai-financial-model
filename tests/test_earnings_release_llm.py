# About: Tests for the LLM-driven earnings_release ingester. Mocked unit
# tests run in CI without burning tokens. The integration test makes a real
# API call and is gated on both ANTHROPIC_API_KEY and RUN_LLM_INTEGRATION
# being set, so it never runs by default.

from __future__ import annotations
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from ai_financial_model.ingestion.earnings_release import EarningsReleaseIngester


REPO = Path(__file__).resolve().parents[1]
PRESS_RELEASE = REPO / "coverage" / "amzn" / "inputs" / "ir" / "latest_press_release.htm"


needs_press_release = pytest.mark.skipif(
    not PRESS_RELEASE.exists(),
    reason="press release not present; run `make seed-data COMPANY=amzn`",
)


def _fake_response(tool_input: dict) -> SimpleNamespace:
    """Build a fake Anthropic Message response with a single tool_use block."""
    block = SimpleNamespace(
        type="tool_use",
        name="record_guidance",
        input=tool_input,
    )
    return SimpleNamespace(content=[block], stop_reason="tool_use")


@needs_press_release
def test_extracts_via_mocked_llm():
    """Happy path: LLM returns guidance → ForwardGuidance is populated."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response({
        "period": "Q2 2026",
        "revenue_low": 194000,
        "revenue_high": 199000,
        "operating_income_low": 20000,
        "operating_income_high": 24000,
        "notes": "Net sales of $194 to $199 billion.",
    })

    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = EarningsReleaseIngester(PRESS_RELEASE).extract()

    assert out.forward_guidance is not None
    g = out.forward_guidance
    assert g.period == "Q2 2026"
    assert g.revenue_low == 194000
    assert g.revenue_high == 199000
    assert g.operating_income_low == 20000

    # Verify how the LLM was called
    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["cache_control"] == {"type": "ephemeral"}
    assert kwargs["tool_choice"] == {"type": "tool", "name": "record_guidance"}
    assert kwargs["model"] == "claude-sonnet-4-6"  # default
    assert "forward financial guidance" in kwargs["system"]
    # Strict-mode tool with the ForwardGuidance schema
    tool = kwargs["tools"][0]
    assert tool["strict"] is True
    assert tool["name"] == "record_guidance"
    assert "revenue_low" in tool["input_schema"]["properties"]


@needs_press_release
def test_falls_back_gracefully_on_api_error():
    """Network / API errors → empty ForwardGuidance, pipeline continues."""
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = ConnectionError("network down")

    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = EarningsReleaseIngester(PRESS_RELEASE).extract()

    assert out.forward_guidance is None
    # meta.source still records the ingester ran
    assert (out.meta.source or "").startswith("earnings:")


@needs_press_release
def test_falls_back_when_no_tool_use_block_returned():
    """Refusal / empty response → empty ForwardGuidance."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I cannot help with that.")],
        stop_reason="end_turn",
    )

    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = EarningsReleaseIngester(PRESS_RELEASE).extract()

    assert out.forward_guidance is None


@needs_press_release
def test_html_is_stripped_before_send():
    """User content sent to the LLM is plain text, not raw HTML."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response({
        "period": None, "revenue_low": None, "revenue_high": None,
        "operating_income_low": None, "operating_income_high": None,
        "notes": None,
    })

    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        EarningsReleaseIngester(PRESS_RELEASE).extract()

    user_content = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    raw_html_size = PRESS_RELEASE.stat().st_size
    assert len(user_content) < raw_html_size, "should be stripped to text"
    assert "<html" not in user_content.lower()
    assert "<div" not in user_content.lower()


def test_missing_html_file_returns_empty():
    """Missing source file → empty ExtractedFinancials, no LLM call."""
    fake_client = MagicMock()
    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = EarningsReleaseIngester(REPO / "nonexistent.htm").extract()

    assert out.forward_guidance is None
    fake_client.messages.create.assert_not_called()


# ---- Integration test (real API call, opt-in) ----

@pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("RUN_LLM_INTEGRATION")),
    reason="Integration test; set ANTHROPIC_API_KEY and RUN_LLM_INTEGRATION=1.",
)
@needs_press_release
def test_amzn_press_release_real_api():
    """Real LLM extraction on the AMZN Q1 2026 press release. Costs ~$0.10."""
    out = EarningsReleaseIngester(PRESS_RELEASE).extract()
    assert out.forward_guidance is not None
    g = out.forward_guidance
    assert g.period and "2026" in g.period, f"unexpected period: {g.period!r}"
    # AMZN Q2 2026 guide is in the $190-200B range, expressed as millions
    assert g.revenue_low and g.revenue_low > 100_000, f"revenue_low={g.revenue_low!r}"
    assert g.revenue_high and g.revenue_high >= g.revenue_low
    # Operating income guide is in the $20-25B range
    assert g.operating_income_low and g.operating_income_low > 10_000
    assert isinstance(g.notes, str) and len(g.notes) > 0
