# About: Vendor adapter — converts NYU Stern (Damodaran) monthly industry
# datasets into the generic data/industry/<key>.yaml format that the pipeline
# reads. Run manually whenever you want fresh industry priors. The pipeline
# itself is not coupled to this script; swap to any other source by writing a
# different adapter that produces the same yaml.
#
# Run: uv run python3 scripts/refresh_industry_damodaran.py \
#         --industry "Retail (General)" --key retail_general
#
# Source files (download via curl into data/macro/damodaran/):
#   totalbeta.xls, margin.xls, roc.xls, wacc.xls, histimpl.xls

from __future__ import annotations
import argparse
import sys
import warnings
from pathlib import Path
from typing import Optional

import yaml
import xlrd

REPO = Path(__file__).resolve().parents[1]
DAM_DIR = REPO / "data" / "macro" / "damodaran"
OUT_DIR = REPO / "data" / "industry"


# Each entry: (filename, {schema_field: header_substring_to_find_in_columns})
FILE_FIELD_MAP: dict[str, dict[str, str]] = {
    "totalbeta.xls": {
        "levered_beta":   "Levered Beta",
        "unlevered_beta": "Unlevered Beta",
    },
    "margin.xls": {
        "pretax_operating_margin": "Pre-tax",
    },
    "roc.xls": {
        "return_on_invested_capital": "ROIC",
    },
    "wacc.xls": {
        "cost_of_capital": "Cost of Capital",
    },
}


def _iter_xls_rows(path: Path) -> list[list]:
    """Read the data sheet from a Damodaran .xls file.

    Damodaran files have a "Variables & FAQ" sheet at index 0; data lives on
    a sheet usually named "Industry Averages". Pick that one if present, else
    the largest-by-rows non-FAQ sheet."""
    if not path.exists():
        return []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = xlrd.open_workbook(str(path))
    candidates = [n for n in wb.sheet_names() if "FAQ" not in n.upper()]
    if not candidates:
        return []
    preferred = next((n for n in candidates if "industry" in n.lower()), candidates[0])
    ws = wb.sheet_by_name(preferred)
    return [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]


def _find_industry_row(rows: list[list], industry_name: str) -> Optional[tuple[list, list]]:
    if not rows:
        return None
    header_idx = None
    for i, r in enumerate(rows[:20]):
        a = str(r[0]).strip().lower() if r else ""
        if a.startswith("industry"):
            header_idx = i
            break
    if header_idx is None:
        return None
    headers = [str(c).strip() for c in rows[header_idx]]
    target = industry_name.lower().strip()
    for r in rows[header_idx + 1:]:
        if not r:
            continue
        a = str(r[0]).strip().lower()
        if a == target or target in a or a in target:
            return headers, list(r)
    return None


def _pick_value(headers: list[str], values: list, header_substr: str) -> Optional[float]:
    target = header_substr.lower()
    for i, h in enumerate(headers):
        if h and target in h.lower():
            v = values[i] if i < len(values) else None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def _latest_implied_erp(path: Path) -> Optional[float]:
    rows = _iter_xls_rows(path)
    for i, r in enumerate(rows[:15]):
        cells = [str(c).strip() for c in r]
        if any(c.lower() == "year" for c in cells):
            erp_idx = next((j for j, c in enumerate(cells)
                            if "implied" in c.lower() and "premium" in c.lower()), None)
            if erp_idx is None:
                return None
            latest: Optional[tuple[int, float]] = None
            for r2 in rows[i + 1:]:
                try:
                    yr = int(float(r2[0]))
                    val = float(r2[erp_idx])
                except (TypeError, ValueError, IndexError):
                    continue
                if latest is None or yr > latest[0]:
                    latest = (yr, val)
            return latest[1] if latest else None
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--industry", required=True,
                   help='Damodaran industry name (e.g. "Retail (General)").')
    p.add_argument("--key", required=True,
                   help="Output file key (e.g. retail_general). Output: data/industry/<key>.yaml")
    p.add_argument("--dam-dir", type=Path, default=DAM_DIR,
                   help="Directory containing Damodaran .xls files.")
    p.add_argument("--as-of",
                   help="As-of date for the snapshot (YYYY-MM-DD); defaults to file mtime.")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    fields: dict[str, object] = {
        "industry_name": args.industry,
    }
    for filename, mapping in FILE_FIELD_MAP.items():
        path = args.dam_dir / filename
        rows = _iter_xls_rows(path)
        row = _find_industry_row(rows, args.industry)
        if not row:
            print(f"  ! no row for '{args.industry}' in {filename}", file=sys.stderr)
            continue
        headers, values = row
        for schema_field, header_substr in mapping.items():
            v = _pick_value(headers, values, header_substr)
            if v is not None:
                fields[schema_field] = v

    erp = _latest_implied_erp(args.dam_dir / "histimpl.xls")
    if erp is not None:
        fields["equity_risk_premium"] = erp

    if args.as_of:
        fields["as_of_date"] = args.as_of
    else:
        # use the most recent mtime among the inputs
        mtimes = [(args.dam_dir / fn).stat().st_mtime
                  for fn in FILE_FIELD_MAP if (args.dam_dir / fn).exists()]
        if mtimes:
            from datetime import date as _date
            fields["as_of_date"] = _date.fromtimestamp(max(mtimes)).isoformat()

    out_path = OUT_DIR / f"{args.key}.yaml"
    out_path.write_text(yaml.safe_dump(fields, sort_keys=False))
    print(f"Wrote {out_path}")
    print(yaml.safe_dump(fields, sort_keys=False))


if __name__ == "__main__":
    main()
