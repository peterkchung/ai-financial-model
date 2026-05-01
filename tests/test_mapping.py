# About: Test the per-run mapping.md generator. Loads the AMZN company config,
# runs the orchestrator, builds the mapping markdown, and asserts the document
# is structurally complete.

from pathlib import Path

import pytest

from ai_financial_model.pipeline import load_company_config, ingest_all
from ai_financial_model.generation import build_mapping_md, enumerate_template_cells


REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "templates" / "valuation_template.xlsx"
COMPANY = REPO / "coverage" / "amzn" / "config.yaml"
FSDS = REPO / "coverage" / "amzn" / "inputs" / "sec_xbrl"
MACRO = REPO / "coverage" / "amzn" / "inputs" / "macro" / "inputs.yaml"


needs_data = pytest.mark.skipif(
    not (FSDS.exists() and (FSDS / "num.txt").exists() and MACRO.exists()),
    reason="local data corpus not present; run `make seed-data COMPANY=amzn` first",
)


@needs_data
def test_mapping_md_has_all_required_sections():
    cfg = load_company_config(COMPANY)
    data, provenance = ingest_all(cfg)

    md = build_mapping_md(
        company_config=cfg,
        company_config_path=COMPANY,
        template_path=TEMPLATE,
        provenance=provenance,
        extracted=data,
    )

    # 1. Header carries the identity + generated-at
    assert "# Valuation mapping — AMZN" in md
    assert "Amazon.com, Inc." in md
    assert "Generated:" in md

    # 2. Configured data sources lists every ingester from the config + the inline industry block
    assert "## Configured data sources" in md
    for spec in cfg["ingesters"]:
        assert f"`{spec['type']}`" in md
    assert "Inline `industry:` block" in md

    # 3. Field plan has at least one source string from a real ingester
    assert "## Field plan — by template cell" in md
    assert "sec-fsds" in md or "macro:" in md or "industry:inline" in md

    # 4. Unfilled cells section flags market-data cells (no ingester provides those today)
    assert "## Unfilled cells" in md
    assert "market.market_cap_m" in md or "market.price_per_share" in md

    # 5. Schema-fields-without-template-cells section exists (may be empty)
    assert "## Schema fields without template cells" in md


def test_enumerate_template_cells_returns_records():
    """Sanity-check the helper independently of the orchestrator."""
    cells = enumerate_template_cells(TEMPLATE)
    assert cells, "template should have at least one tagged cell"
    # Each entry: (sheet, coord, schema_field)
    assert all(len(t) == 3 for t in cells)
    # Sheets we expect to find
    sheets = {sheet for sheet, _, _ in cells}
    assert {"Cover", "Inputs", "Historicals"}.issubset(sheets)
