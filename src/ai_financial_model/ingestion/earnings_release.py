# About: Earnings press release ingester. Uses Claude (default: Sonnet 4.6)
# to extract forward guidance from 8-K Ex 99.1 prose via tool use with a
# strict-mode schema. Falls back to empty ForwardGuidance if the LLM call
# fails — the pipeline never fail-stops on an extraction hiccup.

from __future__ import annotations
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.schema import ExtractedFinancials, ForwardGuidance
from ai_financial_model.llm import extract_via_tool


SYSTEM_PROMPT = """You extract forward financial guidance from earnings press releases.

Locate the section where the company states its expectations for the next
fiscal period — typically labeled "Financial Guidance", "Guidance", or
"Outlook". Then call the `record_guidance` tool with the extracted figures.

Conventions:
- `period`: the next fiscal period being guided. Format examples: "Q2 2026",
  "FY2026", "first half 2026". Null if no period is named.
- `revenue_low` / `revenue_high`: the lower and upper bounds of revenue or
  net-sales guidance, IN MILLIONS USD. Convert as needed: a guide of "$194
  billion to $199 billion" becomes 194000 / 199000. Null if not disclosed.
- `operating_income_low` / `operating_income_high`: same units, for operating
  income guidance. Null if not disclosed.
- `notes`: 1-2 short sentences quoting the verbatim guidance language. Null
  if no guidance found.

Do not infer or extrapolate figures that aren't explicitly stated in the
release. If the release contains no forward guidance, call the tool with
all fields null.
"""

GUIDANCE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "period": {
            "type": ["string", "null"],
            "description": "Period the guidance is for, e.g. 'Q2 2026'.",
        },
        "revenue_low": {
            "type": ["number", "null"],
            "description": "Lower bound of revenue / net-sales guidance, in $-millions.",
        },
        "revenue_high": {
            "type": ["number", "null"],
            "description": "Upper bound of revenue / net-sales guidance, in $-millions.",
        },
        "operating_income_low": {
            "type": ["number", "null"],
            "description": "Lower bound of operating-income guidance, in $-millions.",
        },
        "operating_income_high": {
            "type": ["number", "null"],
            "description": "Upper bound of operating-income guidance, in $-millions.",
        },
        "notes": {
            "type": ["string", "null"],
            "description": "Short verbatim summary of the guidance language.",
        },
    },
    "required": [
        "period", "revenue_low", "revenue_high",
        "operating_income_low", "operating_income_high", "notes",
    ],
    "additionalProperties": False,
}


class EarningsReleaseIngester(Ingester):
    """Parse one earnings press release HTML and extract forward guidance."""

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
            tool_name="record_guidance",
            tool_description="Record forward guidance extracted from the press release.",
            input_schema=GUIDANCE_TOOL_SCHEMA,
        )
        if result:
            try:
                out.forward_guidance = ForwardGuidance(**result)
            except Exception:
                # Schema-strict mode should prevent this; defense in depth.
                pass

        out.meta.source = f"earnings:{self.path.name}"
        return out

    @staticmethod
    def _html_to_text(path: Path) -> str:
        html = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")
        return soup.get_text(" ", strip=True)
