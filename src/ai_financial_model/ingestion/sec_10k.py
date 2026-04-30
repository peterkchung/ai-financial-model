# About: SEC 10-K HTML ingester. STUB — current behavior parses the cover page
# for ticker/shares-outstanding only. The financial-statement table extraction
# is the next milestone (see PRD §6.1 — table reconstructor + footnote linker).
#
# When implementing: walk the consolidated statements, normalize period labels
# (FY-2 / FY-1 / FY latest), populate the IncomeStatement / CashFlow / BalanceSheet
# branches of ExtractedFinancials. Until then, generate-from-handcrafted-JSON
# is the supported path.

from __future__ import annotations
from pathlib import Path
import re

from bs4 import BeautifulSoup

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.schema import ExtractedFinancials


class SEC10KIngester(Ingester):
    def extract(self, source: Path) -> ExtractedFinancials:
        html = source.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)

        out = ExtractedFinancials()
        out.meta.source = source.name

        # Cover-page parses (cheap deterministic wins; LLM-driven extraction
        # will replace this for the body of the filing).
        m = re.search(r"Number of shares of common stock outstanding as of[^0-9]+([0-9,]+)", text)
        if m:
            try:
                out.shares.outstanding_m = float(m.group(1).replace(",", "")) / 1_000_000
            except ValueError:
                pass

        return out
