# Macro inputs

Files in this directory hold macro / market inputs (risk-free rate, credit spread, FX, CPI, GDP) that feed the **Inputs** sheet's tunable cells.

## Pipeline contract

The pipeline reads `<key>.yaml` or `.csv` via `ai_financial_model.ingestion.macro.MacroInputsIngester`. Field names match `schema.MacroInputs`. All numeric fields are decimals (4.2% → `0.042`).

```yaml
risk_free_rate: 0.042         # 10Y UST yield
long_bond_rate: 0.045         # 30Y UST
baa_corporate_yield: 0.058    # BAA corporate bond yield
credit_spread_baa: 0.016      # baa - rf
fx_usd_eur: 1.085
cpi_yoy: 0.030
real_gdp_growth: 0.025
as_of_date: 2026-04-30
```

## Where the data comes from

Vendor-agnostic. Adapters in `scripts/` write files in this format from any source:

| Source | Adapter |
|---|---|
| **FRED (St. Louis Fed)** | `uv run python scripts/refresh_macro_fred.py --key us_default` |
| **Bloomberg / Reuters** | Write `scripts/refresh_macro_bloomberg.py` that emits the same yaml |
| **Internal mark / hand-edited** | Write `scripts/refresh_macro_internal.py` or just edit the yaml |

The pipeline never imports FRED-specific code.
