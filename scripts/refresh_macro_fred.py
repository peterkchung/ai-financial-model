# About: Per-company vendor adapter — reads FRED CSV downloads from
# coverage/<company>/inputs/macro/fred/ and writes the canonical
# coverage/<company>/inputs/macro/inputs.yaml that the pipeline consumes.
# The pipeline never depends on FRED specifically; this is just one possible
# source. Each company gets its own copy so an analyst can hold a custom
# macro view per name.
#
# Run: uv run python scripts/refresh_macro_fred.py --company amzn

from __future__ import annotations
import argparse
import csv
from datetime import date as _date
from pathlib import Path
from typing import Optional

import yaml

REPO = Path(__file__).resolve().parents[1]


# series_id → (schema field, scale).
# scale: 0.01 if FRED reports percent and we want decimal; 1.0 otherwise.
SERIES_MAP: dict[str, tuple[str, float]] = {
    "DGS10":     ("risk_free_rate",      0.01),
    "DGS30":     ("long_bond_rate",      0.01),
    "DBAA":      ("baa_corporate_yield", 0.01),
    "DEXUSEU":   ("fx_usd_eur",          1.00),
    "CPIAUCSL":  ("cpi_yoy",             1.00),  # raw level; YoY computed
    "GDPC1":     ("real_gdp_growth",     1.00),  # raw level; YoY computed
}


def read_series(path: Path) -> list[tuple[str, Optional[float]]]:
    rows = []
    with path.open(newline="") as f:
        reader = csv.reader(f)
        next(reader)
        for r in reader:
            if len(r) < 2:
                continue
            try:
                rows.append((r[0], float(r[1])))
            except ValueError:
                rows.append((r[0], None))
    return rows


def yoy(obs: list[tuple[str, Optional[float]]], current_date: str) -> Optional[float]:
    try:
        cy, cm, cd = (int(x) for x in current_date.split("-"))
        target = _date(cy - 1, cm, cd).isoformat()
    except (ValueError, TypeError):
        return None
    prior = max((o for o in obs if o[0] <= target and o[1] is not None),
                key=lambda o: o[0], default=None)
    current = next((o for o in obs if o[0] == current_date and o[1] is not None), None)
    if not (prior and current and prior[1]):
        return None
    return current[1] / prior[1] - 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--company", default="amzn",
                   help="Coverage ticker (writes to coverage/<company>/inputs/macro/).")
    args = p.parse_args()

    fred_dir = REPO / f"coverage/{args.company}/inputs/macro/fred"
    out_path = REPO / f"coverage/{args.company}/inputs/macro/inputs.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not fred_dir.exists():
        raise SystemExit(
            f"FRED CSV directory missing: {fred_dir}\n"
            f"Run `make seed-data COMPANY={args.company}` first."
        )

    fields: dict[str, object] = {}
    latest_date = None
    for series_id, (field, scale) in SERIES_MAP.items():
        path = fred_dir / f"{series_id.lower()}.csv"
        if not path.exists():
            continue
        obs = read_series(path)
        latest = next((o for o in reversed(obs) if o[1] is not None), None)
        if latest is None:
            continue
        date, value = latest
        latest_date = max(latest_date or date, date)

        if series_id in ("CPIAUCSL", "GDPC1"):
            v = yoy(obs, date)
            if v is not None:
                fields[field] = v
        else:
            fields[field] = value * scale

    rf = fields.get("risk_free_rate")
    baa = fields.get("baa_corporate_yield")
    if isinstance(rf, (int, float)) and isinstance(baa, (int, float)):
        fields["credit_spread_baa"] = baa - rf

    if latest_date:
        fields["as_of_date"] = latest_date

    out_path.write_text(yaml.safe_dump(fields, sort_keys=False))
    print(f"Wrote {out_path.relative_to(REPO)}")
    print(yaml.safe_dump(fields, sort_keys=False))


if __name__ == "__main__":
    main()
