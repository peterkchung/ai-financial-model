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
├── config/companies/
│   └── amzn.yaml                     # company config: identity + valuation assumptions + ingesters
├── scripts/
│   ├── seed_data.py                  # one-shot bootstrap: SEC + FRED downloads
│   ├── build_template.py             # regenerate the blank template
│   └── refresh_macro_fred.py         # FRED → data/macro_inputs/<key>.yaml (vendor adapter)
├── templates/
│   └── valuation_template.xlsx       # 7-sheet two-stage FCFF DCF skeleton
├── src/ai_financial_model/
│   ├── schema.py                     # ExtractedFinancials (Pydantic)
│   ├── pipeline.py                   # orchestrator: company config → merged ExtractedFinancials
│   ├── cli.py                        # `aifm process-company | ingest-company | generate | validate`
│   ├── ingestion/
│   │   ├── base.py                   # Ingester ABC
│   │   ├── sec_xbrl.py               # SEC FSDS XBRL → company financials
│   │   ├── sec_10q.py                # 10-Q wrapper around sec_xbrl
│   │   ├── earnings_release.py       # 8-K Ex 99.1 → forward guidance
│   │   ├── form4.py                  # Form 4 XML → insider transactions
│   │   └── macro.py                  # generic MacroInputs loader (YAML/CSV)
│   ├── generation/
│   │   └── populator.py              # ExtractedFinancials → populated workbook
│   └── validation/
│       ├── checks.py                 # mechanical-tie checks
│       └── report.py                 # green/yellow/red findings
├── tests/
│   ├── test_populator.py             # generation + validation
│   └── test_pipeline.py              # orchestrator end-to-end
└── data/
    ├── sec/                          # 10-K, 10-Q, 8-K, DEF 14A, Form 4, FSDS bulk (gitignored)
    ├── ir/                           # press releases, CFO commentary (gitignored)
    ├── macro/                        # raw vendor data — FRED CSVs (gitignored)
    ├── macro_inputs/                 # canonical generic-format yaml the pipeline reads (committed)
    └── litigation/                   # docket notes (committed)
```

## Quick start (fresh clone)

```bash
# 1. Prerequisites: Python 3.11+ and uv (https://docs.astral.sh/uv/)
git clone https://github.com/peterkchung/ai-financial-model
cd ai-financial-model

# 2. Install dependencies
make install

# 3. Bootstrap the data corpus (~80 MB download, ~640 MB unpacked)
#    Pulls SEC EDGAR filings and FRED CSVs.
#    Idempotent: re-running skips files that already exist.
make seed-data

# 4. Run the end-to-end pipeline against Amazon
make process-company COMPANY=amzn
# → output/amzn/extracted.json   (merged data from all ingesters)
# → output/amzn/model.xlsx       (populated valuation workbook — open in Excel)
# → green/yellow/red validation report

# Or in one shot:
make demo                     # = install + seed-data + process-company COMPANY=amzn
```

The `output/amzn/model.xlsx` is the analyst-facing deliverable — a 7-sheet FCFF DCF with cell-level provenance comments.

## What `make seed-data` downloads

| Source | Where it lands | Size | Purpose |
|---|---|---|---|
| SEC Financial Statement Data Sets (2026q1 zip) | `data/sec/financial_statement_data_sets/2026q1/` | ~640 MB unpacked | All-registrant XBRL facts; the pipeline's primary financials feed |
| AMZN Form 4 filings (latest 5) | `data/sec/amzn/` | ~25 KB | Insider transactions |
| AMZN earnings press release (latest 8-K Ex 99.1) | `data/ir/amzn/latest_press_release.htm` | ~600 KB | Forward guidance |
| FRED macro CSVs (DGS10, DGS30, DBAA, DEXUSEU, CPIAUCSL, GDPC1) | `data/macro/fred/*.csv` | ~800 KB | Inputs for `refresh-macro` |

> **SEC Note:** EDGAR requires a User-Agent header identifying the requester. The seed script defaults to `ai-financial-model-research aifm-bootstrap@example.com`. Override via `SEC_UA="Your Org admin@yourorg.com" make seed-data`.

## How the analyst works with the pipeline

The **company config** (`config/companies/<ticker>.yaml`) is the analyst's interface. One file per company. It contains three sections:

1. **`meta:`** — identity (ticker, company name, valuation date)
2. **`industry:`** — per-company calibration (β, ERP, target margins, terminal WACC, ROIC). These are judgment calls; pull starting numbers from any source you like — industry tables, bottom-up build, your own thesis. **Edit them directly here.** No separate file, no vendor lock-in.
3. **`ingesters:`** — which automated data feeds to run for this company (SEC filings, earnings releases, Form 4s, shared macro)

```yaml
meta:
  ticker: AMZN
  company_name: Amazon.com, Inc.
  valuation_date: "2025-12-31"

industry:
  industry_name: Retail (General)
  levered_beta: 0.78                # cost-of-equity input
  equity_risk_premium: 0.0475       # standard mature-US ERP
  pretax_operating_margin: 0.135    # target Y10 EBIT margin (your thesis)
  return_on_invested_capital: 0.31  # terminal ROIC
  cost_of_capital: 0.0727           # terminal WACC
  sales_to_capital: 1.50            # reinvestment efficiency

ingesters:
  - type: sec_xbrl
    args:
      fsds_dir: data/sec/financial_statement_data_sets/2026q1
      cik: 1018724
      form: 10-K
  - type: earnings_release
    args:
      html_path: data/ir/amzn/latest_press_release.htm
  - type: form4
    args:
      form4_dir: data/sec/amzn
  - type: macro
    args:
      path: data/macro_inputs/us_default.yaml
```

**Industry assumptions inline; macro shared.** The split reflects real usage — every analyst will tune β and target margin per company, but rf, FX, and credit spreads are the same across all companies in the same currency / regime, so they live in one shared `data/macro_inputs/<key>.yaml`.

## Pipeline architecture

Three stages, each with a clear contract:

```
company config (YAML) ──orchestrator──▶ ExtractedFinancials (merged)
                                         │
                                         ├──populator──▶ model.xlsx
                                         │                  │
                                         │                  └──validator──▶ ValidationReport
                                         │
                                         (ingesters + inline industry block, deep-merged)
```

The orchestrator runs each ingester listed in the config, then layers in the inline `industry:` block (analyst calibration wins last), and hands the merged result to the populator.

## Day-to-day commands

```bash
# Stage-by-stage (after seed-data):
make ingest-company COMPANY=amzn   # orchestrate ingesters → extracted.json
make generate COMPANY=amzn         # populate the template → model.xlsx
make validate COMPANY=amzn         # run mechanical-tie checks

# Refresh shared macro feed when rates have moved:
make refresh-macro                  # FRED CSVs → data/macro_inputs/us_default.yaml

# Other:
make template                       # regenerate templates/valuation_template.xlsx
make test                           # pytest
make help                           # show every target
```

## Adding a new company

1. Drop source documents into `data/sec/<ticker>/` (filings) and `data/ir/<ticker>/` (IR collateral).
2. Copy `config/companies/amzn.yaml` to `config/companies/<ticker>.yaml` and edit:
   - `meta` block: ticker, name, valuation date
   - `industry` block: your calibration assumptions
   - `ingesters` block: paths and CIK
3. `make process-company COMPANY=<ticker>`.

## What's next

- **Confidence scoring** — every populated cell gets a green/yellow/red badge derived from extraction confidence + cross-source agreement.
- **Peer ingestion config** — extend the company config to pull a peer comp set in one orchestrator run.
- **Web/UI surface** — currently CLI-only.
