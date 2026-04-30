# About: Generic MacroInputs ingester. Reads a YAML or CSV file describing
# macro/market inputs (rf, credit spread, FX, etc.) into the `macro` section
# of ExtractedFinancials. Vendor-agnostic — populate the file from FRED,
# Bloomberg, an internal feed, or by hand. Refresh adapters live in scripts/.

from __future__ import annotations
from pathlib import Path
from typing import Optional, Any
import csv

import yaml

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.schema import ExtractedFinancials, MacroInputs

KNOWN_FIELDS = set(MacroInputs.model_fields.keys())


class MacroInputsIngester(Ingester):
    """Load macro inputs from a YAML/CSV the user maintains.

    YAML format: top-level keys map to MacroInputs fields. Values are decimals
    (4.2% → 0.042). CSV format: two-column key,value rows.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def extract(self, source: Optional[Path] = None) -> ExtractedFinancials:
        out = ExtractedFinancials()
        if not self.path.exists():
            raise FileNotFoundError(f"Macro inputs file not found: {self.path}")

        data = self._read(self.path)
        coerced: dict[str, Any] = {}
        for k, v in data.items():
            if k not in KNOWN_FIELDS:
                continue
            if k == "as_of_date" and v is not None:
                coerced[k] = str(v)
            elif v is None or v == "":
                coerced[k] = None
            else:
                try:
                    coerced[k] = float(v)
                except (TypeError, ValueError):
                    pass
        out.macro = MacroInputs(**coerced)
        out.meta.source = f"macro:{self.path.name}"
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
        raise ValueError(f"Unsupported macro inputs file format: {suffix} ({path})")
