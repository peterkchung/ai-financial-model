# About: Smoke-test the orchestrator. Runs the AMZN company config end-to-end
# and asserts the populated workbook validates GREEN (mechanical ties hold).
# Doubles as the integration-level eval harness.

from pathlib import Path

import pytest

from ai_financial_model.pipeline import load_company_config, ingest_all
from ai_financial_model.generation import populate_template
from ai_financial_model.validation import validate_workbook, Severity


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
def test_orchestrator_amzn_extracts_core_financials():
    cfg = load_company_config(COMPANY)
    data, provenance = ingest_all(cfg)

    assert data.meta.cik == 1018724
    assert data.pl.net_sales.fy_latest == pytest.approx(716_924, rel=1e-3)
    assert data.pl.operating_income.fy_latest == pytest.approx(79_975, rel=1e-3)
    assert data.bs.cash == pytest.approx(86_810, rel=1e-3)

    # Macro feed contributed live values
    assert data.macro.risk_free_rate is not None

    # Inline industry block from the company config was applied
    assert data.industry.industry_name is not None
    assert data.industry.levered_beta is not None

    # Form 4 ingester contributed at least one transaction
    assert len(data.insider_activity) > 0

    # Sources string lists every contributor
    assert "sec-fsds" in (data.meta.source or "")
    assert "macro:" in (data.meta.source or "")
    assert "industry:inline" in (data.meta.source or "")

    # Provenance map records the source for each populated path
    assert provenance.get("pl.net_sales.fy_latest", "").startswith("sec-fsds")
    assert provenance.get("macro.risk_free_rate", "").startswith("macro:")
    assert provenance.get("industry.levered_beta") == "industry:inline"


@needs_data
def test_orchestrator_to_validated_workbook(tmp_path: Path):
    cfg = load_company_config(COMPANY)
    data, provenance = ingest_all(cfg)
    out = tmp_path / "model.xlsx"
    pop = populate_template(data, TEMPLATE, out, provenance=provenance)
    report = validate_workbook(out)

    failed = [f for f in report.findings if f.severity == Severity.RED]
    assert not failed, f"Validation regressed:\n{report.summary()}"

    # Audit trail: every populated cell has a recognized source
    populated = [c for c in pop["cells"] if c["status"] == "populated"]
    assert populated, "expected at least one populated cell"
    assert all(c["source"] for c in populated), \
        "every populated cell should record its source"
