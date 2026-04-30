# About: Convenience targets for the ai-financial-model pipeline.
# Most targets dispatch to `uv run aifm ...`; the underlying CLI lives in
# src/ai_financial_model/cli.py.

DEAL ?= amzn
DEAL_CONFIG ?= config/deals/$(DEAL).yaml
TEMPLATE ?= templates/valuation_template.xlsx
OUT_DIR ?= output/$(DEAL)
OUT ?= $(OUT_DIR)/model.xlsx
EXTRACTED ?= $(OUT_DIR)/extracted.json

# Single-source variant (legacy path; prefer process-deal)
SOURCE ?= data/reference/amazon_10k_fy2025.htm

.PHONY: help install template refresh-macro refresh-industry \
        ingest-deal generate validate process-deal \
        ingest process clean test

help:
	@echo "Pipeline targets:"
	@echo "  install            — uv sync (with dev extras)"
	@echo "  template           — regenerate templates/valuation_template.xlsx"
	@echo "  process-deal       — orchestrated pipeline: ingest every source in DEAL_CONFIG → populate → validate"
	@echo "  ingest-deal        — only the orchestrated ingestion step"
	@echo "  generate           — only populate the template (using \$$EXTRACTED)"
	@echo "  validate           — only run validation on \$$OUT"
	@echo ""
	@echo "Reference-data refresh (vendor adapters):"
	@echo "  refresh-macro      — FRED CSVs → data/macro_inputs/us_default.yaml"
	@echo "  refresh-industry   — Damodaran .xls → data/industry/retail_general.yaml"
	@echo "                       Override INDUSTRY=\"...\" KEY=... for other industries."
	@echo ""
	@echo "Single-source legacy:"
	@echo "  ingest             — extract from SOURCE → \$$EXTRACTED"
	@echo "  process            — single-source: ingest → generate → validate"
	@echo ""
	@echo "Other:"
	@echo "  test, clean"
	@echo ""
	@echo "Variables: DEAL=$(DEAL) DEAL_CONFIG=$(DEAL_CONFIG) TEMPLATE=$(TEMPLATE)"

install:
	uv sync --extra dev

template:
	uv run python scripts/build_template.py

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

# Orchestrated pipeline (preferred)
ingest-deal: $(OUT_DIR)
	uv run aifm ingest-deal --deal $(DEAL_CONFIG) --out $(EXTRACTED)

generate: $(OUT_DIR)
	uv run aifm generate --extracted $(EXTRACTED) --template $(TEMPLATE) --out $(OUT)

validate:
	uv run aifm validate --workbook $(OUT)

process-deal: $(OUT_DIR)
	uv run aifm process-deal --deal $(DEAL_CONFIG) --template $(TEMPLATE) --out-dir $(OUT_DIR)

# Reference-data refresh (run when you want fresh inputs)
refresh-macro:
	uv run python scripts/refresh_macro_fred.py --key us_default

INDUSTRY ?= Retail (General)
KEY ?= retail_general
refresh-industry:
	uv run python scripts/refresh_industry_damodaran.py --industry "$(INDUSTRY)" --key $(KEY)

# Single-source legacy path
ingest: $(OUT_DIR)
	uv run aifm ingest --source $(SOURCE) --out $(EXTRACTED)

process: ingest generate validate

clean:
	rm -rf output/$(DEAL)

test:
	uv run pytest
