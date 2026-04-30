# About: Abstract Ingester. Concrete subclasses implement extract() to parse
# their source format into the shared ExtractedFinancials schema.

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path

from ai_financial_model.schema import ExtractedFinancials


class Ingester(ABC):
    """Convert a source document into the shared ExtractedFinancials schema."""

    @abstractmethod
    def extract(self, source: Path) -> ExtractedFinancials:
        """Read `source` and return populated ExtractedFinancials. Unknown
        fields should remain None — the populator treats absent fields as
        empty cells with reason codes, not as zeros."""
        raise NotImplementedError


def detect_ingester(source: Path) -> Ingester:
    """Dispatch on file extension / contents. For now: SEC 10-K HTML only."""
    from ai_financial_model.ingestion.sec_10k import SEC10KIngester
    suffix = source.suffix.lower()
    if suffix in {".htm", ".html"}:
        return SEC10KIngester()
    raise NotImplementedError(
        f"No ingester registered for {suffix}. Add one in "
        f"ai_financial_model/ingestion/ and register it in detect_ingester()."
    )
