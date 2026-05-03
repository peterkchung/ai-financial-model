# Demo: extending the pipeline

A walkthrough of how the pipeline goes from "credible baseline" to "more comprehensive" by adding one new data source — driven by a config edit, not a code change in front of the audience.

The example: Amazon's **Anthropic convertible-note conversion gain** (~$15.2B in FY2025, another ~$16.8B in Q1 2026). Buried in the 10-K's MD&A and explicitly called out in the Q1 2026 press release; not separately tagged in XBRL. Today's pipeline silently treats it as recurring; the extended pipeline carves it out, normalizes Other income, and flags the issue in validation.

This doc serves two purposes:
1. **Presenter's script** — the steps to run during a live demo
2. **Implementation plan** — the code work needed to make the demo actually run (not yet built; checklist at the bottom)

---

## The demo arc (4 steps, ~3 minutes live)

```
   Step 1            Step 2                 Step 3              Step 4
   ──────            ──────                 ──────              ──────
  Baseline    →    Edit config       →    Expanded     →     Compare
   run                (one line)            run               outputs

  pipeline as     add one ingester       same pipeline       diff audit.json,
  it ships          to coverage/...        re-runs            mapping.md, model
                    /config.yaml                              cell-by-cell
```

---

## Step 1: baseline run

The pipeline as it ships today.

```bash
# Confirm the API key is loaded (LLM ingester needs it)
set -a && source .env && set +a

# End-to-end run
make process-company COMPANY=amzn

# Open the workbook
open coverage/amzn/outputs/<latest>/model.xlsx
```

**What to point out on the Cover sheet:**

| Cell | Reads | What's hidden |
|---|---|---|
| Forward Guidance section | "Q2 2026 net sales $194B–$199B…" | LLM extracted from press release ✓ |
| Forecast vs guidance sanity | YELLOW finding — implied Q-avg below low end | Real signal ✓ |
| Historicals!D14 (Other income) | $15,229M | **No indication that this is a one-time gain** |

**What to point out in `audit.json`:**

```bash
jq '.summary, .validation' coverage/amzn/outputs/<latest>/audit.json
```

```jsonc
{
  "tagged_cells": 116,
  "populated": 100,
  ...
}
"Overall: YELLOW
 GREEN × 4 (mechanical ties)
 YELLOW × 1 (forecast vs guidance)"
```

**Presenter line:** *"Pipeline produces a model that ties on every mechanical check, with one yellow flag worth the analyst's time. Looks fine. But $15.2B of last year's pre-tax income is one-time — and nothing in this run says so."*

---

## Step 2: enable the extension

One YAML edit. Open `coverage/amzn/config.yaml`. There's a commented-out block — uncomment 3 lines:

```diff
   # ---------------------------------------------------------------------
   # Demo extension point — uncomment to enable LLM-driven extraction of
   # non-recurring items (Anthropic conversion gains, restructuring, etc.)
   # See docs/demo-pipeline-extension.md for the demo arc.
   # ---------------------------------------------------------------------
-  # - type: non_recurring_items
-  #   args:
-  #     html_path: coverage/amzn/inputs/ir/latest_press_release.htm
+  - type: non_recurring_items
+    args:
+      html_path: coverage/amzn/inputs/ir/latest_press_release.htm
```

Or in your editor: select the three commented lines and remove the leading `# ` prefix from each.

That's it. **No code changes during the demo.** The ingester is already registered in the codebase; it just wasn't enabled for this company until you uncommented it.

**Presenter line:** *"Adding a new data feed to a company is a one-line config edit. Behind that line is an LLM-driven extractor that reads the press release and identifies one-time items the company itself flags. Watch what happens."*

---

## Step 3: run with the extension

Same command, no other change.

```bash
make process-company COMPANY=amzn
```

**Console diff vs Step 1:**

```
[1/3] Orchestrating ingesters…
  Sources: sec-fsds:... + earnings:latest_press_release.htm
         + non_recurring:latest_press_release.htm    ← NEW
         + form4:... + macro:... + industry:inline
[2/3] Populating template…
  108/116 cells populated  ← was 100/116; 8 new memo cells filled
[3/3] Validating…
Overall: RED   ← was YELLOW

-- RED (1) --
  [non_recurring_items_proportion] One-time items
  $15,229M = 15.6% of FY2025 pre-tax income, exceeds 15%
  threshold. Do not capitalize aggregate Other income into
  terminal value without explicit normalization.

-- YELLOW (1) --
  [forecast_y1_consistent_with_guidance] (unchanged)

-- GREEN (4) --
  (mechanical ties unchanged)
```

**What to point out on the Cover sheet:**

| Cell | Now reads |
|---|---|
| Non-recurring items #1 — description | "Anthropic convertible note conversion gain" |
| Non-recurring items #1 — amount | $15,229M |
| Non-recurring items #1 — period | FY2025 |
| Non-recurring items #1 — line item | Other income (expense), net |
| Non-recurring items #1 — source quote | *"…gain on the portions of our convertible notes investments in Anthropic that were converted to nonvoting preferred stock during 2025."* |
| Other income (as-reported) | $15,229M |
| (-) Non-recurring items, sum | ($15,229M) |
| **Normalized Other income** | **~$0M** |

**Presenter line:** *"The model now distinguishes between $15.2B of one-time gain and $0M of recurring other income. Forecast assumption is no longer hidden — the analyst can see it, the validator flagged it as RED, and the source quote is right there in the cell. Same workbook, same template, same code — one config line."*

---

## Step 4: compare outputs

Side-by-side diff between the two runs.

```bash
LATEST=$(ls -1 coverage/amzn/outputs | sort | tail -1)
PREV=$(ls -1 coverage/amzn/outputs | sort | tail -2 | head -1)

# What changed in the wiring
diff coverage/amzn/outputs/$PREV/mapping.md \
     coverage/amzn/outputs/$LATEST/mapping.md

# What changed in execution
diff coverage/amzn/outputs/$PREV/audit.json \
     coverage/amzn/outputs/$LATEST/audit.json | head -50

# What changed in extracted data
diff <(jq '.non_recurring_items' coverage/amzn/outputs/$PREV/extracted.json) \
     <(jq '.non_recurring_items' coverage/amzn/outputs/$LATEST/extracted.json)
```

The `mapping.md` diff shows the new ingester registered + a new template cell block. The `audit.json` diff shows the new RED finding + the populated cells. The `extracted.json` diff shows the new `non_recurring_items` array.

**Presenter line:** *"Three artifacts, three views of the same change. Wiring, execution trace, and underlying data. Anything an analyst, auditor, or compliance reviewer wants to ask is answerable from these files."*

---

## How the extension works under the hood

The pipeline has four layers; each got one small change to support this extension. **None changes during the demo** — they're all pre-built and committed; the demo just toggles the new ingester on via config.

| Layer | What was added | File |
|---|---|---|
| **Schema** | `NonRecurringItem` Pydantic model + `non_recurring_items: list[…]` field on `ExtractedFinancials` | `src/ai_financial_model/schema.py` |
| **Ingestion** | New `NonRecurringItemsIngester` class registered in `INGESTER_REGISTRY` as `non_recurring_items`. Reuses `extract_via_tool()` from `llm.py`. | `src/ai_financial_model/ingestion/non_recurring.py` (new) + `pipeline.py` registry entry |
| **Template** | New Cover-sheet block: 5 carve-out slots × 5 columns (description, period, line item, amount, source quote) + a "Normalized Other income" computed row | `scripts/build_template.py` |
| **Validation** | `_check_non_recurring_proportion`: GREEN < 5% / YELLOW 5–15% / RED > 15% of pre-tax income | `src/ai_financial_model/validation/checks.py` |

This is the same pattern any future extension follows. **The framework didn't get more complicated — only one specific feature did.**

---

## Implementation checklist (work needed before this demo runs)

To make the demo above actually execute, the following code work needs to land. Each item is small; everything below is a one-PR scope.

### Schema
- [ ] In `src/ai_financial_model/schema.py`: define `NonRecurringItem` (description, amount, period, line_item, source_quote)
- [ ] Add `non_recurring_items: list[NonRecurringItem]` to `ExtractedFinancials`

### Ingester
- [ ] New file `src/ai_financial_model/ingestion/non_recurring.py`:
  - `NonRecurringItemsIngester(html_path)` class
  - System prompt: identify one-time items (gains/losses on investments, restructuring, impairments, settlements, etc.)
  - Tool schema: list of `NonRecurringItem`-shaped objects
  - HTML → text → `extract_via_tool()` → populate `out.non_recurring_items`
- [ ] Register `"non_recurring_items": NonRecurringItemsIngester` in `INGESTER_REGISTRY` in `pipeline.py`

### Template
- [ ] In `scripts/build_template.py`, add to Cover sheet (after the existing Forward Guidance / Sanity blocks):
  - Header: "Non-recurring items (carved out for normalization)"
  - 5 row slots × tagged cells: `non_recurring_items[i].{description,amount,period,line_item,source_quote}`
  - Computed block: "Other income (as-reported)" → `=Historicals!D13`; "(-) Non-recurring sum"; "Normalized Other income"
- [ ] `make template` to regenerate the .xlsx

### Validator
- [ ] In `src/ai_financial_model/validation/checks.py`, new `_check_non_recurring_proportion`:
  - Sum `non_recurring_items[*].amount` from Cover sheet
  - Read `pl.income_before_tax.fy_latest` from Historicals
  - GREEN < 5% / YELLOW 5–15% / RED > 15%
  - Hook into `validate_workbook()`

### Tests
- [ ] In `tests/test_earnings_release_llm.py` (or a new `test_non_recurring.py`):
  - Mocked test: returns one Anthropic-style item
  - Mocked test: returns empty list (no one-timers)
  - Mocked test: API failure → empty list, no crash

### Config policy
- [ ] **Default `coverage/amzn/config.yaml` does NOT list the `non_recurring_items` ingester** — the baseline state for the demo. The presenter adds it live during Step 2.

### Verification
- `make test` — all existing + new tests green
- `make process-company COMPANY=amzn` (baseline config) — same output as today, validator YELLOW
- Edit config to add ingester, re-run — validator RED, Cover sheet populated, audit.json shows new fields

---

## Generalizing — what other one-timers fit the same shape

The new `non_recurring_items` ingester isn't AMZN-specific. It applies to any company with material non-recurring items. Cases worth showcasing for other names later:

- **Restructuring charges** — frequent in turnaround stories; usually disclosed as a line item with a narrative footnote
- **Goodwill impairments** — single-period writedowns; the LLM can pull the dollar amount and explanation
- **Gains/losses on business disposals** — divestitures, sale-leasebacks
- **Litigation settlements** — discrete, large, non-operating
- **One-time tax benefits** — DTA releases, audit settlements
- **Insurance recoveries** — disaster, cyber

The system prompt for the ingester already lists these examples; it generalizes for free. The validator's threshold is per-company-config so it can be tuned (e.g., relaxed for serial restructurers, tightened for steady-state names).

---

## What this demo proves

- **The pipeline is config-driven extensible** — adding a data feed is a YAML edit, not a code change.
- **The LLM unlocks footnoted disclosures** — XBRL doesn't tag the Anthropic gain specifically; you need prose understanding. The LLM ingester reads the press release and surfaces it.
- **The validator enforces analyst discipline** — RED isn't an error in the code; it's the system saying "an analyst needs to think about this before publishing the model." That's the point of the validator.
- **Every change is auditable** — `audit.json`, `mapping.md`, and the source-quote cell all trace the new finding back to the verbatim sentence in the press release. Nothing was inferred or hallucinated.
