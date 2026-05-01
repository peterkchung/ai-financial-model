# About: Convenience targets for the ai-financial-model pipeline.
# Targets dispatch to `uv run aifm ...`; the underlying CLI lives in
# src/ai_financial_model/cli.py.

COMPANY ?= amzn
COMPANY_DIR ?= coverage/$(COMPANY)
COMPANY_CONFIG ?= $(COMPANY_DIR)/config.yaml
OUTPUTS_DIR ?= $(COMPANY_DIR)/outputs
LATEST_RUN ?= $(shell ls -1 $(OUTPUTS_DIR) 2>/dev/null | sort | tail -1)
LATEST_DIR ?= $(OUTPUTS_DIR)/$(LATEST_RUN)
TEMPLATE ?= templates/valuation_template.xlsx

.PHONY: help install seed-data template refresh-macro \
        ingest-company generate validate process-company \
        clean test demo

help:
	@echo "First-time setup:"
	@echo "  install            — uv sync (with dev extras)"
	@echo "  seed-data          — download SEC + FRED data needed for COMPANY=$(COMPANY)"
	@echo "  demo               — install + seed-data + process-company COMPANY=amzn (one shot)"
	@echo ""
	@echo "Pipeline:"
	@echo "  template           — regenerate templates/valuation_template.xlsx"
	@echo "  process-company    — orchestrated pipeline: ingest → populate → validate"
	@echo "  ingest-company     — only the orchestrated ingestion step"
	@echo "  generate           — only populate the template (using latest run's extracted.json)"
	@echo "  validate           — only run validation on the latest run's model.xlsx"
	@echo ""
	@echo "Reference-data refresh:"
	@echo "  refresh-macro      — FRED CSVs → coverage/\$$(COMPANY)/inputs/macro/inputs.yaml"
	@echo ""
	@echo "Other:"
	@echo "  test, clean"
	@echo ""
	@echo "Variables: COMPANY=$(COMPANY) COMPANY_CONFIG=$(COMPANY_CONFIG) TEMPLATE=$(TEMPLATE)"
	@echo "           Latest run: $(LATEST_DIR)"

install:
	uv sync --extra dev

seed-data:
	uv run python scripts/seed_data.py --company $(COMPANY)

demo: install
	$(MAKE) seed-data COMPANY=amzn
	$(MAKE) process-company COMPANY=amzn

template:
	uv run python scripts/build_template.py

ingest-company:
	@mkdir -p $(OUTPUTS_DIR)
	uv run aifm ingest-company --company $(COMPANY_CONFIG) --out $(LATEST_DIR)/extracted.json

generate:
	uv run aifm generate --extracted $(LATEST_DIR)/extracted.json --template $(TEMPLATE) --out $(LATEST_DIR)/model.xlsx

validate:
	uv run aifm validate --workbook $(LATEST_DIR)/model.xlsx

process-company:
	@mkdir -p $(OUTPUTS_DIR)
	uv run aifm process-company --company $(COMPANY_CONFIG) --template $(TEMPLATE)

refresh-macro:
	uv run python scripts/refresh_macro_fred.py --company $(COMPANY)

clean:
	rm -rf $(OUTPUTS_DIR)

test:
	uv run pytest
