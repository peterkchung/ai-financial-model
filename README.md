# ai-financial-model

Pipeline that orchestrates multiple data sources into a populated Excel valuation model with cell-level provenance and reconciliation flags.

## Status

v0.1 — orchestrator runs four ingesters end-to-end against Amazon and produces a validated FCFF DCF workbook. All four mechanical-tie checks pass at 0% variance.

## Project layout

```
ai-financial-model/
├── README.md
├── Makefile
├── pyproject.toml
├── coverage/                                     ← per-company hub
│   └── amzn/
│       ├── config.yaml                           ← analyst intent (committed)
│       ├── inputs/                               ← per-company raw data (gitignored)
│       │   ├── sec_xbrl/                         ← AMZN slice of SEC FSDS (sub.txt + num.txt)
│       │   ├── sec_filings/                      ← form 4 xmls, 10-Q htms, etc.
│       │   ├── ir/                               ← press releases, CFO commentary
│       │   ├── litigation/                       ← docket notes
│       │   └── macro/
│       │       ├── fred/                         ← raw FRED CSVs (per-company copies)
│       │       └── inputs.yaml                   ← canonical macro yaml (per-company)
│       └── outputs/                              ← per-run snapshots (gitignored)
│           └── 2026-04-30T22-26-18Z/
│               ├── extracted.json                ← merged data from ingesters
│               ├── mapping.md                    ← BLUEPRINT: sources → cells (per-run)
│               ├── model.xlsx                    ← populated workbook (analyst deliverable)
│               └── audit.json                    ← TRACE: per-cell execution + validation
├── scripts/
│   ├── seed_data.py                  # per-company bootstrap; slices SEC FSDS bulk
│   ├── build_template.py             # regenerate the blank template
│   └── refresh_macro_fred.py         # FRED CSVs → coverage/<co>/inputs/macro/inputs.yaml
├── templates/
│   └── valuation_template.xlsx       # 7-sheet two-stage FCFF DCF skeleton
├── src/ai_financial_model/
│   ├── schema.py                     # ExtractedFinancials (Pydantic)
│   ├── pipeline.py                   # orchestrator: company config → merged ExtractedFinancials + provenance
│   ├── cli.py                        # `aifm process-company | ingest-company | generate | validate`
│   ├── ingestion/
│   │   ├── base.py                   # Ingester ABC
│   │   ├── sec_xbrl.py               # SEC FSDS XBRL → company financials
│   │   ├── sec_10q.py                # 10-Q wrapper around sec_xbrl
│   │   ├── earnings_release.py       # 8-K Ex 99.1 → forward guidance
│   │   ├── form4.py                  # Form 4 XML → insider transactions
│   │   └── macro.py                  # generic MacroInputs loader (YAML/CSV)
│   ├── generation/
│   │   ├── populator.py              # ExtractedFinancials → populated workbook
│   │   └── mapping.py                # ExtractedFinancials + template + provenance → mapping.md
│   └── validation/
│       ├── checks.py                 # mechanical-tie checks
│       └── report.py                 # green/yellow/red findings
├── tests/
│   ├── test_populator.py             # generation + validation
│   ├── test_pipeline.py              # orchestrator end-to-end
│   └── test_mapping.py               # blueprint structure
└── data/                                         ← transient bulk download cache (gitignored)
    └── sec_fsds_cache/                           ← 640 MB FSDS bulk; sliced into coverage/<co>/inputs/sec_xbrl/
```

`coverage/` is the analyst's collection. Within it, each ticker is a self-contained hub: config + inputs + outputs. Between-company isolation is total — AMZN's data context never touches MSFT's. The `inputs/` ↔ `outputs/` pair reads symmetrically. `data/` is a transient download cache for the one piece too large to copy per-company (the SEC FSDS bulk file).

> **Naming note.** We use `coverage/` because it matches analyst language ("our coverage list"). The unit is "a name in our coverage list."

## Quick start (fresh clone)

```bash
# 1. Prerequisites: Python 3.11+ and uv (https://docs.astral.sh/uv/)
git clone https://github.com/peterkchung/ai-financial-model
cd ai-financial-model

# 2. Install dependencies
make install

# 3. Bootstrap data for AMZN (~80 MB download, ~640 MB unpacked + small per-company slice)
#    Idempotent: re-running skips files that already exist.
make seed-data COMPANY=amzn

# 4. Run the end-to-end pipeline against Amazon
make process-company COMPANY=amzn
# → coverage/amzn/outputs/<ts>/extracted.json   (merged data from ingesters)
# → coverage/amzn/outputs/<ts>/mapping.md       (blueprint: sources → cells)
# → coverage/amzn/outputs/<ts>/model.xlsx       (populated workbook — open in Excel)
# → coverage/amzn/outputs/<ts>/audit.json       (per-cell execution trace)
# → green/yellow/red validation report

# Or in one shot:
make demo                     # = install + seed-data + process-company COMPANY=amzn
```

The `model.xlsx` is the analyst-facing deliverable — a 7-sheet FCFF DCF with cell-level provenance comments.

## What `make seed-data` downloads

| Source | Where it lands | Size | Purpose |
|---|---|---|---|
| SEC FSDS bulk (2026q1 zip → unpacked) | `data/sec_fsds_cache/2026q1/` | ~640 MB | Shared download cache; sliced per-company below |
| AMZN's slice of FSDS | `coverage/amzn/inputs/sec_xbrl/{sub,num}.txt` | KB-scale | Per-company subset for the orchestrator |
| AMZN Form 4 filings (latest 5) | `coverage/amzn/inputs/sec_filings/` | ~25 KB | Insider transactions |
| AMZN earnings press release (latest 8-K Ex 99.1) | `coverage/amzn/inputs/ir/latest_press_release.htm` | ~600 KB | Forward guidance |
| FRED macro CSVs (DGS10, DGS30, DBAA, DEXUSEU, CPIAUCSL, GDPC1) | `coverage/amzn/inputs/macro/fred/*.csv` | ~800 KB | Inputs for `make refresh-macro` |

> **SEC Note:** EDGAR requires a User-Agent identifying the requester. The seed script defaults to `ai-financial-model-research aifm-bootstrap@example.com`. Override via `SEC_UA="Your Org admin@yourorg.com" make seed-data COMPANY=amzn`.

## How the analyst works with the pipeline

The **company config** (`coverage/<ticker>/config.yaml`) is the analyst's interface. One file per company. Three sections:

1. **`meta:`** — identity (ticker, company name, valuation date)
2. **`industry:`** — per-company calibration (β, ERP, target margins, terminal WACC, ROIC). Judgment calls; pull starting numbers from any source — industry tables, bottom-up build, your own thesis. Edit them directly here.
3. **`ingesters:`** — automated data feeds (SEC filings, earnings releases, Form 4s, macro)

```yaml
meta:
  ticker: AMZN
  company_name: Amazon.com, Inc.
  valuation_date: "2025-12-31"

industry:
  industry_name: Retail (General)
  levered_beta: 0.78                # cost-of-equity input
  equity_risk_premium: 0.0475       # mature-US ERP
  pretax_operating_margin: 0.135    # target Y10 EBIT margin (your thesis)
  return_on_invested_capital: 0.31  # terminal ROIC
  cost_of_capital: 0.0727           # terminal WACC
  sales_to_capital: 1.50            # reinvestment efficiency

ingesters:
  - type: sec_xbrl
    args:
      fsds_dir: coverage/amzn/inputs/sec_xbrl
      cik: 1018724
      form: 10-K
  - type: earnings_release
    args:
      html_path: coverage/amzn/inputs/ir/latest_press_release.htm
  - type: form4
    args:
      form4_dir: coverage/amzn/inputs/sec_filings
  - type: macro
    args:
      path: coverage/amzn/inputs/macro/inputs.yaml
```

## Per-run artifacts: blueprint + per-cell trace

Every `make process-company` writes a fresh timestamped directory under `coverage/<ticker>/outputs/`. Two artifacts (besides `extracted.json` and `model.xlsx`) describe the run:

### `mapping.md` — blueprint

The wiring used for this run. Five sections:

1. **Header** — ticker, name, valuation date, generated-at, config path.
2. **Configured data sources** — a table of every ingester + the inline `industry:` block, with their args. Together with the timestamp directory, this *is* the record of *what files were used at what time*.
3. **Field plan — by template cell** — per-sheet table of `(cell, schema_field, source)`.
4. **Unfilled cells** — analyst follow-up list.
5. **Schema fields without template cells** — extracted-but-unused (data we have but don't show).

### `audit.json` — per-cell execution trace

JSON. Per-cell: which value was written from which source, status (`populated` / `default_kept` / `no_value_extracted`), plus run summary and validation result.

```jsonc
{
  "generated_at": "2026-04-30T22-26-18Z",
  "company": {"ticker": "AMZN", "company_name": "Amazon.com, Inc.", "cik": 1018724, ...},
  "summary": {"tagged_cells": 110, "populated": 94, "default_kept": 0, "no_value_extracted": 16},
  "cells": [
    {"sheet": "Historicals", "cell": "D2", "schema_field": "pl.net_sales.fy_latest",
     "value": 716924.0, "source": "sec-fsds:0001018724-26-000004", "status": "populated"},
    ...
  ],
  "validation": "Overall: GREEN ..."
}
```

**Diff across runs** is meaningful:
```bash
diff coverage/amzn/outputs/<old>/mapping.md  coverage/amzn/outputs/<new>/mapping.md   # what changed in wiring
diff coverage/amzn/outputs/<old>/audit.json  coverage/amzn/outputs/<new>/audit.json   # what changed per cell
```

## Pipeline architecture

```
coverage/<ticker>/config.yaml ──orchestrator──▶ ExtractedFinancials + provenance map
                                                  │
                                                  ├──write_mapping───▶ mapping.md
                                                  ├──populate────────▶ model.xlsx
                                                  │                       │
                                                  │                       └──validate──▶ audit.json
                                                  │
                                                  (ingesters + inline industry block, deep-merged)
```

## Day-to-day commands

```bash
# Stage-by-stage (after seed-data):
make ingest-company COMPANY=amzn   # orchestrate ingesters → extracted.json
make generate COMPANY=amzn         # populate the template → model.xlsx
make validate COMPANY=amzn         # run mechanical-tie checks

# Refresh per-company macro feed:
make refresh-macro COMPANY=amzn    # FRED CSVs → coverage/amzn/inputs/macro/inputs.yaml

# Other:
make template                       # regenerate templates/valuation_template.xlsx
make test                           # pytest
make help                           # show every target
```

## Adding a new company

1. Register the company in `scripts/seed_data.py` `COMPANY_REGISTRY` (CIK + ticker prefix used in 8-K exhibit naming, e.g. `msft` → `{cik: "789019", ticker_prefix: "msft"}`).
2. `make seed-data COMPANY=<ticker>` to download + slice everything into `coverage/<ticker>/inputs/`.
3. Copy `coverage/amzn/config.yaml` to `coverage/<ticker>/config.yaml` and edit the `meta`, `industry`, and ingester paths.
4. `make process-company COMPANY=<ticker>`.

## What's next

- **Confidence scoring** — green/yellow/red per cell based on extraction confidence + cross-source agreement.
- **Peer ingestion** — pull a peer comp set in the same orchestrator run.
- **Web/UI surface** — currently CLI-only.
