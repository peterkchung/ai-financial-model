# Industry benchmarks

Files in this directory describe **industry-aggregate priors** — β, ERP, operating margin, ROIC, WACC, sales-to-capital — that the pipeline uses to anchor valuation assumptions.

## Pipeline contract

The pipeline reads `<key>.yaml` (or `.csv`) via `ai_financial_model.ingestion.industry.IndustryBenchmarksIngester`. The contents must match the field names in `schema.IndustryBenchmarks`:

```yaml
industry_name: Retail (General)
as_of_date: 2026-04-01
source: <free-form, for traceability only>

# Capital structure / cost of capital
levered_beta: 1.05
unlevered_beta: 0.85
equity_risk_premium: 0.045
cost_of_capital: 0.078

# Operating profile
pretax_operating_margin: 0.085
return_on_invested_capital: 0.12
sales_to_capital: 1.65
```

All numeric fields are decimals (4.5% → `0.045`). Unknown fields are silently ignored; missing fields stay `None`.

## Where the data comes from

The pipeline is **vendor-agnostic**. It only reads the yaml. You can populate the yaml from any source:

| Source | How |
|---|---|
| **NYU Stern (Damodaran)** | `uv run python scripts/refresh_industry_damodaran.py --industry "Retail (General)" --key retail_general` |
| **Bloomberg / FactSet / S&P Capital IQ** | Write your own `scripts/refresh_industry_<vendor>.py` that emits the same yaml |
| **Internal house data** | Write `scripts/refresh_industry_internal.py`, or just hand-edit the yaml |
| **Hand-edited** | Just edit the yaml — equally valid |

Vendor adapters live in `scripts/` and are *not* on the pipeline's hot path. Swap vendors without touching pipeline code.

## Why this design

Industry data is changing infrequently (monthly at most), comes from many possible sources, and isn't worth coupling the pipeline to any one of them. The yaml is a stable contract; the rate at which it gets refreshed and the source it comes from are independent concerns.

The same pattern can apply to other reference data (macro inputs, peer comp tables) as the pipeline grows.
