# data/

Working corpus for the pipeline. Three buckets:

- **Source documents** the pipeline ingests (`sec/`, `ir/`)
- **External datasets** that feed assumptions (`macro/`, `damodaran/`)
- **Reference / context** that informs assumptions but isn't ingested directly (`litigation/`, `reference/`)

Re-downloadable; large bulk files are gitignored.

## Layout

```
data/
├── sec/
│   ├── amzn/                     # Amazon SEC filings (primary subject)
│   │   ├── 10-q_*.htm            # last 4 quarters
│   │   ├── 8-k_*.htm             # most recent earnings 8-K
│   │   ├── def14a_*.htm          # 2026 proxy
│   │   └── 4_*.xml               # recent insider transactions (Form 4)
│   ├── peers/
│   │   ├── wmt/10-k_*.htm        # Walmart FY2026 10-K
│   │   ├── msft/10-k_*.htm       # Microsoft FY2025 10-K
│   │   └── googl/10-k_*.htm      # Alphabet FY2025 10-K
│   └── financial_statement_data_sets/
│       ├── 2025q4.zip / 2025q4/  # all-registrant XBRL facts (gitignored)
│       └── 2026q1.zip / 2026q1/  # ditto
├── ir/
│   └── amzn/
│       ├── q4_2025_press_release.htm
│       ├── q1_2026_press_release.htm
│       └── *_cfo_commentary.htm
├── macro/
│   ├── fred/
│   │   ├── dgs10.csv             # 10Y UST yield (risk-free)
│   │   ├── dgs30.csv             # 30Y UST yield
│   │   ├── dbaa.csv              # BAA corporate bond yield (credit spread)
│   │   ├── dexuseu.csv           # USD/EUR FX
│   │   ├── cpiaucsl.csv          # CPI-U
│   │   └── gdpc1.csv             # Real GDP
│   └── damodaran/                # NYU Stern industry datasets, monthly cadence
│       ├── totalbeta.xls         # industry betas (levered, unlevered)
│       ├── margin.xls            # industry operating margins
│       ├── roc.xls               # industry returns on capital
│       ├── wacc.xls              # industry costs of capital
│       ├── histimpl.xls          # implied equity risk premium history
│       ├── ctryprem.xlsx         # country risk premiums
│       └── multiples.xls         # industry trading multiples
├── litigation/
│   └── ftc_v_amzn/
│       └── README.md             # docket access notes (CourtListener requires auth)
└── reference/
    └── amazon_10k_fy2025.htm     # original AMZN 10-K used to seed the fixture
```

## How sources map to the pipeline

| Source | Ingester | Schema target |
|---|---|---|
| `sec/amzn/*.htm`, peers | `ingestion/sec_10k.py`, `sec_10q.py` (TBD) | `pl`, `cf`, `bs`, `tax`, `shares`, `segments` |
| SEC Financial Statement Data Sets | `ingestion/sec_xbrl.py` (TBD) | same as above, but pre-parsed — much higher recall |
| `ir/amzn/*.htm` | `ingestion/earnings_release.py` (TBD) | `pl` (current quarter), forward guidance free-text |
| FRED CSVs | `ingestion/fred.py` (TBD) | not in `ExtractedFinancials` — feeds `Inputs` (rf, credit spread) |
| Damodaran files | `ingestion/damodaran_industry.py` (TBD) | feeds `Inputs` (β, ERP, target margin, terminal ROIC) |
| Form 4 (insider txns) | `ingestion/form4.py` (TBD) | sentiment overlay; not a DCF input |
| Litigation | manual | qualitative — affects scenario weighting |

## Re-pulling

All sources are re-downloadable with the queries embedded in commit history (see `scripts/` once a refresh script lands). Bulk SEC files (`financial_statement_data_sets/*`) are gitignored — re-pull from `https://www.sec.gov/dera/data/financial-statement-data-sets`.
