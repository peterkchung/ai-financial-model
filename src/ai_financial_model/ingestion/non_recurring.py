# About: Non-recurring items ingester. Identifies one-time gains/losses
# the company explicitly footnotes in earnings press releases — gains on
# convertible-note conversions, restructuring charges, goodwill impairments,
# litigation settlements, etc. These don't get separate XBRL tags, so we
# read prose with Claude.
#
# Output goes into ExtractedFinancials.non_recurring_items[]. The Cover
# sheet shows them in a memo block; the validator flags when the sum
# exceeds a material % of pre-tax income (RED) so the analyst doesn't
# silently capitalize a one-timer into terminal value.

from __future__ import annotations
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.schema import ExtractedFinancials, NonRecurringItem
from ai_financial_model.llm import extract_via_tool


SYSTEM_PROMPT = """You identify non-recurring items in earnings press releases.

Find any one-time gains or losses the company explicitly calls out in the
release. Examples include:
- Gains/losses on equity investments converted, sold, or remeasured
  (e.g. convertible notes converting to preferred stock, IPO mark-ups,
  fair-value adjustments on equity-method investments)
- Restructuring charges
- Goodwill or asset impairments
- Litigation settlements
- One-time tax benefits or charges
- Insurance recoveries
- Gains/losses on business disposals or acquisitions

Use the `record_non_recurring_items` tool. Provide a list (possibly empty).
For each item, provide:
- `description`: a short label (e.g. "Anthropic convertible note conversion gain")
- `amount`: signed $-millions; positive = gain to pre-tax income, negative = loss
- `period`: which fiscal period the item pertains to (e.g. "FY2025", "Q1 2026")
- `line_item`: which P&L line it sits within
  (e.g. "Other income (expense), net", "Restructuring charges")
- `source_quote`: ONE verbatim sentence from the release that describes the item

Only include items the release EXPLICITLY identifies as non-recurring,
one-time, or otherwise distinguishable from ongoing operations — typically
called out in dedicated sentences in MD&A or the financial highlights. If
the release contains no such items, return an empty list.

Do not infer items the release doesn't explicitly call out.
"""

ITEMS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "description": "List of non-recurring items found in the release.",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": ["string", "null"]},
                    "amount": {"type": ["number", "null"]},
                    "period": {"type": ["string", "null"]},
                    "line_item": {"type": ["string", "null"]},
                    "source_quote": {"type": ["string", "null"]},
                },
                "required": [
                    "description", "amount", "period", "line_item", "source_quote"
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class NonRecurringItemsIngester(Ingester):
    """Parse a press release for non-recurring items via Claude."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def extract(self, source: Optional[Path] = None) -> ExtractedFinancials:
        out = ExtractedFinancials()
        if not self.path.exists():
            return out

        text = self._html_to_text(self.path)
        if not text:
            return out

        result = extract_via_tool(
            system=SYSTEM_PROMPT,
            user_content=text,
            tool_name="record_non_recurring_items",
            tool_description="Record non-recurring items the press release calls out.",
            input_schema=ITEMS_TOOL_SCHEMA,
        )
        if result and isinstance(result.get("items"), list):
            for item_dict in result["items"]:
                try:
                    out.non_recurring_items.append(NonRecurringItem(**item_dict))
                except Exception:
                    # strict mode should prevent this; defense in depth
                    continue

        out.meta.source = f"non_recurring:{self.path.name}"
        return out

    @staticmethod
    def _html_to_text(path: Path) -> str:
        html = path.read_text(encoding="utf-8", errors="ignore")
        return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
