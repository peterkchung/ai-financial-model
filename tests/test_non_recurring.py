# About: Tests for the non_recurring_items LLM ingester. Mocked unit tests
# run in CI without burning tokens; an opt-in integration test makes a real
# API call against the AMZN press release.

from __future__ import annotations
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from ai_financial_model.ingestion.non_recurring import NonRecurringItemsIngester


REPO = Path(__file__).resolve().parents[1]
PRESS_RELEASE = REPO / "coverage" / "amzn" / "inputs" / "ir" / "latest_press_release.htm"


needs_press_release = pytest.mark.skipif(
    not PRESS_RELEASE.exists(),
    reason="press release not present; run `make seed-data COMPANY=amzn`",
)


def _fake_response(items: list[dict]) -> SimpleNamespace:
    """Build a fake Anthropic response carrying a single tool_use block."""
    block = SimpleNamespace(
        type="tool_use",
        name="record_non_recurring_items",
        input={"items": items},
    )
    return SimpleNamespace(content=[block], stop_reason="tool_use")


@needs_press_release
def test_extracts_anthropic_gain_via_mocked_llm():
    """Happy path: LLM returns one item → it lands in non_recurring_items."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response([
        {
            "description": "Anthropic convertible note conversion gain",
            "amount": 15229,
            "period": "FY2025",
            "line_item": "Other income (expense), net",
            "source_quote": "Gain on the portions of our convertible notes "
                           "investments in Anthropic that were converted to "
                           "nonvoting preferred stock during 2025.",
        },
    ])

    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = NonRecurringItemsIngester(PRESS_RELEASE).extract()

    assert len(out.non_recurring_items) == 1
    item = out.non_recurring_items[0]
    assert "Anthropic" in (item.description or "")
    assert item.amount == 15229
    assert item.period == "FY2025"
    assert item.line_item == "Other income (expense), net"
    assert "convertible" in (item.source_quote or "").lower()

    # Verify the LLM was called with the right tool + caching
    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["cache_control"] == {"type": "ephemeral"}
    assert kwargs["tool_choice"] == {"type": "tool", "name": "record_non_recurring_items"}
    tool = kwargs["tools"][0]
    assert tool["strict"] is True
    assert "items" in tool["input_schema"]["properties"]


@needs_press_release
def test_empty_items_list_is_handled():
    """Release with no one-timers → empty list, not an error."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response([])

    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = NonRecurringItemsIngester(PRESS_RELEASE).extract()

    assert out.non_recurring_items == []
    # meta.source still records that the ingester ran
    assert (out.meta.source or "").startswith("non_recurring:")


@needs_press_release
def test_multiple_items_all_captured():
    """Multi-item case: gain + restructuring → both land in the list."""
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response([
        {"description": "Gain A", "amount": 1000, "period": "FY2025",
         "line_item": "Other income", "source_quote": "..."},
        {"description": "Restructuring", "amount": -500, "period": "FY2025",
         "line_item": "Restructuring charges", "source_quote": "..."},
    ])

    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = NonRecurringItemsIngester(PRESS_RELEASE).extract()

    assert len(out.non_recurring_items) == 2
    assert out.non_recurring_items[0].amount == 1000
    assert out.non_recurring_items[1].amount == -500


@needs_press_release
def test_falls_back_gracefully_on_api_error():
    """Network / API errors → empty list, pipeline carries on."""
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = ConnectionError("network down")

    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = NonRecurringItemsIngester(PRESS_RELEASE).extract()

    assert out.non_recurring_items == []


def test_missing_html_file_returns_empty():
    """Missing input file → empty list, no LLM call."""
    fake_client = MagicMock()
    with patch("ai_financial_model.llm._get_client", return_value=fake_client):
        out = NonRecurringItemsIngester(REPO / "nonexistent.htm").extract()

    assert out.non_recurring_items == []
    fake_client.messages.create.assert_not_called()


# ---- Integration test (real API call, opt-in) ----

@pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("RUN_LLM_INTEGRATION")),
    reason="Integration test; set ANTHROPIC_API_KEY and RUN_LLM_INTEGRATION=1.",
)
@needs_press_release
def test_amzn_press_release_real_api():
    """Real LLM extraction on the AMZN Q1 2026 press release. Costs ~$0.10.

    Q1 2026 release explicitly mentions a $16.8B Anthropic-related gain;
    the ingester should pick it up.
    """
    out = NonRecurringItemsIngester(PRESS_RELEASE).extract()
    assert len(out.non_recurring_items) >= 1

    # At least one item should reference Anthropic
    descriptions = " ".join(
        (item.description or "") for item in out.non_recurring_items
    ).lower()
    quotes = " ".join(
        (item.source_quote or "") for item in out.non_recurring_items
    ).lower()
    assert "anthropic" in descriptions or "anthropic" in quotes, (
        f"expected an Anthropic-related item, got: "
        f"{[i.description for i in out.non_recurring_items]}"
    )

    # Anthropic gain should be material (multi-billion-dollar magnitude)
    amounts = [i.amount for i in out.non_recurring_items if i.amount is not None]
    assert any(abs(a) > 1000 for a in amounts), (
        f"expected at least one item over $1B, got: {amounts}"
    )
