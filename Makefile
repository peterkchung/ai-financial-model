# About: Convenience targets for the ai-financial-model pipeline.
# Targets dispatch to `uv run aifm ...`; the underlying CLI lives in
# src/ai_financial_model/cli.py.

COMPANY ?= amzn
COMPANY_CONFIG ?= config/companies/$(COMPANY).yaml
TEMPLATE ?= templates/valuation_template.xlsx
OUT_DIR ?= output/$(COMPANY)
OUT ?= $(OUT_DIR)/model.xlsx
EXTRACTED ?= $(OUT_DIR)/extracted.json

.PHONY: help install seed-data template refresh-macro \
        ingest-company generate validate process-company \
        clean test demo

help:
	@echo "First-time setup:"
	@echo "  install            — uv sync (with dev extras)"
	@echo "  seed-data          — download SEC + FRED data needed for the AMZN demo"
	@echo "  demo               — install + seed-data + process-company COMPANY=amzn (one shot)"
	@echo ""
	@echo "Pipeline:"
	@echo "  template           — regenerate templates/valuation_template.xlsx"
	@echo "  process-company    — orchestrated pipeline: ingest every source in COMPANY_CONFIG → populate → validate"
	@echo "  ingest-company     — only the orchestrated ingestion step"
	@echo "  generate           — only populate the template (using \$$EXTRACTED)"
	@echo "  validate           — only run validation on \$$OUT"
	@echo ""
	@echo "Reference-data refresh:"
	@echo "  refresh-macro      — FRED CSVs → data/macro_inputs/us_default.yaml"
	@echo ""
	@echo "Other:"
	@echo "  test, clean"
	@echo ""
	@echo "Variables: COMPANY=$(COMPANY) COMPANY_CONFIG=$(COMPANY_CONFIG) TEMPLATE=$(TEMPLATE)"

install:
	uv sync --extra dev

seed-data:
	uv run python scripts/seed_data.py

demo: install seed-data
	$(MAKE) process-company COMPANY=amzn

template:
	uv run python scripts/build_template.py

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

ingest-company: $(OUT_DIR)
	uv run aifm ingest-company --company $(COMPANY_CONFIG) --out $(EXTRACTED)

generate: $(OUT_DIR)
	uv run aifm generate --extracted $(EXTRACTED) --template $(TEMPLATE) --out $(OUT)

validate:
	uv run aifm validate --workbook $(OUT)

process-company: $(OUT_DIR)
	uv run aifm process-company --company $(COMPANY_CONFIG) --template $(TEMPLATE) --out-dir $(OUT_DIR)

refresh-macro:
	uv run python scripts/refresh_macro_fred.py --key us_default

clean:
	rm -rf output/$(COMPANY)

test:
	uv run pytest
