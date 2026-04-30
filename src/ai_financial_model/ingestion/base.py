# About: Abstract Ingester. Concrete subclasses implement extract() to parse
# their source format into the shared ExtractedFinancials schema.
#
# Ingester instances are constructed by the orchestrator from a company-config
# YAML (config/companies/<ticker>.yaml). The constructor signature is
# ingester-specific; `extract()` returns a partial ExtractedFinancials.

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ai_financial_model.schema import ExtractedFinancials


class Ingester(ABC):
    """Convert a source into a partial ExtractedFinancials."""

    @abstractmethod
    def extract(self, source: Optional[Path] = None) -> ExtractedFinancials:
        """Return a populated ExtractedFinancials. Unknown fields stay None —
        the populator treats absent fields as empty cells with reason codes,
        never as zeros."""
        raise NotImplementedError
