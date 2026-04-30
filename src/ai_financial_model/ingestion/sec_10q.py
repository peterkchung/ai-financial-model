# About: SEC 10-Q HTML ingester. For 10-Qs that are also in the SEC FSDS
# (most are within 3 months of filing), prefer XBRL via SECXBRLIngester(form="10-Q").
# This module is a thin convenience wrapper that picks the right approach.

from __future__ import annotations
from pathlib import Path
from typing import Optional

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.ingestion.sec_xbrl import SECXBRLIngester
from ai_financial_model.schema import ExtractedFinancials


class SEC10QIngester(Ingester):
    """Wrap SECXBRLIngester(form='10-Q'). HTML-only fallback is TBD."""

    def __init__(self, fsds_dir: Path, cik: int):
        self._inner = SECXBRLIngester(fsds_dir=fsds_dir, cik=cik, form="10-Q")

    def extract(self, source: Optional[Path] = None) -> ExtractedFinancials:
        return self._inner.extract(source)
