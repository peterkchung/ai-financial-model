# ai-financial-model

Pipeline that orchestrates multiple data sources into a populated Excel valuation model with cell-level provenance and reconciliation flags.

## Status

v0.1 — orchestrator runs five ingesters end-to-end against Amazon and produces a validated FCFF DCF workbook. All four mechanical-tie checks pass at 0% variance.

## Project layout

```
ai-financial-model/
├── README.md
├── Makefile
├── pyproject.toml
├── config.yaml                       # global config (currently used for tolerances)
├── config/deals/
│   └── amzn.yaml                     # deal config: which ingesters to run for Amazon
├── scripts/
│   ├── build_template.py             # regenerate the blank template
│   ├── refresh_macro_fred.py         # FRED → data/macro_inputs/<key>.yaml (vendor adapter)
│   └── refresh_industry_damodaran.py # NYU Stern → data/industry/<key>.yaml (vendor adapter)
├── templates/
│   └── valuation_template.xlsx       # 7-sheet two-stage FCFF DCF skeleton
├── src/ai_financial_model/
│   ├── schema.py                     # ExtractedFinancials (Pydantic)
│   ├── pipeline.py                   # orchestrator: deal config → merged ExtractedFinancials
│   ├── cli.py                        # `aifm process-deal | ingest | generate | validate`
│   ├── ingestion/
│   │   ├── base.py                   # Ingester ABC
│   │   ├── sec_xbrl.py               # SEC FSDS XBRL → company financials
│   │   ├── sec_10q.py                # 10-Q wrapper around sec_xbrl
│   │   ├── sec_10k.py                # 10-K HTML stub
│   │   ├── earnings_release.py       # 8-K Ex 99.1 → forward guidance
│   │   ├── form4.py                  # Form 4 XML → insider transactions
│   │   ├── industry.py               # generic IndustryBenchmarks loader (YAML/CSV)
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
    ├── sec/                          # 10-K, 10-Q, 8-K, DEF 14A, Form 4, FSDS bulk
    ├── ir/                           # press releases, CFO commentary
    ├── macro/                        # raw vendor data (FRED CSVs, Damodaran .xls)
    ├── macro_inputs/                 # canonical generic-format yaml the pipeline reads
    ├── industry/                     # canonical generic-format yaml the pipeline reads
    ├── litigation/                   # docket notes
    └── reference/                    # corpus seed (10-K used for early dev)
```

## Installation

```bash
uv sync --extra dev
```

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

## Pipeline architecture

Three stages, each with a clear contract:

```
deal config (YAML) ──orchestrator──▶ ExtractedFinancials (merged)
                                         │
                                         ├──populator──▶ model.xlsx
                                         │                  │
                                         │                  └──validator──▶ ValidationReport
                                         │
                                         (multiple ingesters, deep-merged)
```

The deal config lists which ingesters to run with which arguments. The orchestrator runs them in order, deep-merges their partial `ExtractedFinancials` outputs, and hands the merged result to the populator.

## Generalizable ingestion

Reference-data ingesters are **vendor-agnostic**. They read flat YAML/CSV files written in a standard format. Vendor-specific parsing lives in *adapter scripts* under `scripts/refresh_*.py` that produce those files. The pipeline never imports vendor code.

Pattern:

```
vendor source ──refresh adapter (scripts/)──▶ data/<type>/<key>.yaml ──ingester──▶ ExtractedFinancials
```

Two examples live in the codebase:

| Type | Pipeline reads | Refresh adapter | Vendor |
|---|---|---|---|
| Industry benchmarks | `data/industry/<key>.yaml` | `scripts/refresh_industry_damodaran.py` | NYU Stern |
| Macro inputs | `data/macro_inputs/<key>.yaml` | `scripts/refresh_macro_fred.py` | FRED |

Swap to a different vendor (Bloomberg, FactSet, internal feed) by writing a new `scripts/refresh_<type>_<vendor>.py` that emits the same yaml format. The pipeline is unchanged.

## Quick start

```bash
# Install + build the blank template
make install
make template

# Refresh reference data (run periodically; outputs are gitignored)
make refresh-macro
make refresh-industry

# End-to-end pipeline against the Amazon deal config
make process-deal DEAL=amzn
# → output/amzn/extracted.json
# → output/amzn/model.xlsx
# → green/yellow/red validation report

# Or per stage
make ingest-deal DEAL=amzn      # orchestrate ingesters
make generate DEAL=amzn          # populate the template
make validate DEAL=amzn          # run mechanical-tie checks

# Tests
make test
```

## Adding a new deal

1. Drop source documents into `data/sec/<ticker>/` (filings) and `data/ir/<ticker>/` (IR collateral).
2. Author `config/deals/<ticker>.yaml` listing which ingesters to run with which paths.
3. `make process-deal DEAL=<ticker>`.

A typical deal config:

```yaml
meta:
  ticker: AMZN
  company_name: Amazon.com, Inc.
  valuation_date: "2025-12-31"

ingesters:
  - type: sec_xbrl
    args:
      fsds_dir: data/sec/financial_statement_data_sets/2026q1
      cik: 1018724
      form: 10-K
  - type: earnings_release
    args:
      html_path: data/ir/amzn/q1_2026_press_release.htm
  - type: form4
    args:
      form4_dir: data/sec/amzn
  - type: macro
    args:
      path: data/macro_inputs/us_default.yaml
  - type: industry
    args:
      path: data/industry/retail_general.yaml
```

Later ingesters override earlier ones for overlapping fields; lists (e.g. insider activity) concatenate.

## What's next

- **Replace SEC HTML stub with full extractor** for filings not yet in the FSDS bulk file.
- **Confidence scoring** — every populated cell gets a green/yellow/red badge derived from extraction confidence + cross-source agreement.
- **Peer ingestion config** — extend the deal config to pull a peer comp set in one orchestrator run.
- **Web/UI surface** — currently CLI-only.
