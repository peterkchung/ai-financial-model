# About: Earnings press release ingester. Pulls forward guidance from the
# 8-K Ex 99.1 HTML (and Ex 99.2 if present). Press-release prose varies a lot
# in structure; we use targeted regex on the "Financial Guidance" section.
# Quarterly current-period numbers are already in the 10-Q via XBRL, so this
# ingester focuses on what's *only* in the press release: forward guidance.

from __future__ import annotations
from pathlib import Path
from typing import Optional
import re

from bs4 import BeautifulSoup

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.schema import ExtractedFinancials, ForwardGuidance


# Match e.g. "$155.0 billion and $160.5 billion" or "$155 billion to $160 billion"
RANGE_BILLIONS = re.compile(
    r"\$?\s*([\d,.]+)\s*(?:billion|B)\b[^.$]{0,80}?\$?\s*([\d,.]+)\s*(?:billion|B)\b",
    re.IGNORECASE,
)


class EarningsReleaseIngester(Ingester):
    """Parse a single press release HTML and extract forward guidance."""

    def __init__(self, html_path: Path):
        self.html_path = Path(html_path)

    def extract(self, source: Optional[Path] = None) -> ExtractedFinancials:
        out = ExtractedFinancials()
        if not self.html_path.exists():
            return out

        text = self._normalize(self.html_path.read_text(encoding="utf-8", errors="ignore"))
        guidance = self._find_guidance(text)
        if guidance:
            out.forward_guidance = guidance

        out.meta.source = f"earnings:{self.html_path.name}"
        return out

    @staticmethod
    def _normalize(html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        return soup.get_text(" ", strip=True)

    def _find_guidance(self, text: str) -> Optional[ForwardGuidance]:
        # Locate the guidance section
        m = re.search(r"financial guidance|guidance\s+for\s+the\s+(?:second|third|fourth|first)",
                      text, re.IGNORECASE)
        if not m:
            return None
        # Look at the ~2K chars after the heading
        window = text[m.start(): m.start() + 2000]

        period = self._period_from_window(window)
        rev_lo, rev_hi = self._first_revenue_range(window)
        oi_lo, oi_hi = self._first_op_income_range(window)

        if rev_lo is None and oi_lo is None:
            return None
        return ForwardGuidance(
            period=period, revenue_low=rev_lo, revenue_high=rev_hi,
            operating_income_low=oi_lo, operating_income_high=oi_hi,
            notes=window[:400],
        )

    @staticmethod
    def _period_from_window(text: str) -> Optional[str]:
        m = re.search(r"(first|second|third|fourth)\s+quarter\s+(\d{4})", text, re.IGNORECASE)
        if m:
            qmap = {"first": "Q1", "second": "Q2", "third": "Q3", "fourth": "Q4"}
            return f"{qmap[m.group(1).lower()]} {m.group(2)}"
        m = re.search(r"full year\s+(\d{4})", text, re.IGNORECASE)
        if m:
            return f"FY{m.group(1)}"
        return None

    @staticmethod
    def _first_revenue_range(text: str) -> tuple[Optional[float], Optional[float]]:
        # Search near "Net sales"
        m = re.search(r"Net sales.{0,200}", text)
        if not m:
            return (None, None)
        rng = RANGE_BILLIONS.search(m.group(0))
        if not rng:
            return (None, None)
        try:
            return (float(rng.group(1).replace(",", "")) * 1_000,
                    float(rng.group(2).replace(",", "")) * 1_000)
        except ValueError:
            return (None, None)

    @staticmethod
    def _first_op_income_range(text: str) -> tuple[Optional[float], Optional[float]]:
        m = re.search(r"Operating income.{0,200}", text)
        if not m:
            return (None, None)
        rng = RANGE_BILLIONS.search(m.group(0))
        if not rng:
            return (None, None)
        try:
            return (float(rng.group(1).replace(",", "")) * 1_000,
                    float(rng.group(2).replace(",", "")) * 1_000)
        except ValueError:
            return (None, None)
