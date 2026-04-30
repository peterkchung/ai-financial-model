# About: Generic IndustryBenchmarks ingester. Reads a flat YAML or CSV file
# describing one industry's aggregate metrics and populates the `industry`
# section of ExtractedFinancials. The pipeline is vendor-agnostic: any source
# (Damodaran, Bloomberg, FactSet, internal house data, hand-edited) can feed
# this loader as long as the file matches the documented schema.
#
# Refresh adapters that *write* these files live in scripts/ — not in the
# hot pipeline path.

from __future__ import annotations
from pathlib import Path
from typing import Optional, Any
import csv

import yaml

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.schema import ExtractedFinancials, IndustryBenchmarks


# Schema for the file format. Keys must match IndustryBenchmarks fields.
KNOWN_FIELDS = set(IndustryBenchmarks.model_fields.keys())


class IndustryBenchmarksIngester(Ingester):
    """Load industry benchmarks from a YAML or CSV file the user maintains.

    Args:
        path: file path (.yaml, .yml, or .csv).
              YAML format: top-level keys map directly to IndustryBenchmarks fields.
              CSV format: two-column key,value with one row per field.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def extract(self, source: Optional[Path] = None) -> ExtractedFinancials:
        out = ExtractedFinancials()
        if not self.path.exists():
            raise FileNotFoundError(f"Industry benchmark file not found: {self.path}")

        data = self._read(self.path)
        # Coerce values for known numeric fields
        coerced: dict[str, Any] = {}
        for k, v in data.items():
            if k not in KNOWN_FIELDS:
                continue
            if k in ("industry_name", "as_of_date") and v is not None:
                coerced[k] = str(v)
            elif v is None or v == "":
                coerced[k] = None
            else:
                try:
                    coerced[k] = float(v)
                except (TypeError, ValueError):
                    pass  # silently drop non-numeric for numeric fields

        out.industry = IndustryBenchmarks(**coerced)
        out.meta.source = f"industry:{self.path.name}"
        return out

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        suffix = path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(path.read_text()) or {}
        if suffix == ".csv":
            out: dict[str, Any] = {}
            with path.open(newline="") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2 and row[0].strip():
                        out[row[0].strip()] = row[1].strip()
            return out
        raise ValueError(f"Unsupported industry file format: {suffix} ({path})")
