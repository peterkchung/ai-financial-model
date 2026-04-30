# About: Smoke-test the orchestrator. Runs the AMZN company config end-to-end
# and asserts the populated workbook validates GREEN (mechanical ties hold).
# Doubles as the integration-level eval harness flagged in PRD §13.

from pathlib import Path

import pytest

from ai_financial_model.pipeline import load_company_config, ingest_all
from ai_financial_model.generation import populate_template
from ai_financial_model.validation import validate_workbook, Severity


REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "templates" / "valuation_template.xlsx"
COMPANY = REPO / "config" / "companies" / "amzn.yaml"
FSDS = REPO / "data" / "sec" / "financial_statement_data_sets" / "2026q1"
INDUSTRY = REPO / "data" / "industry" / "retail_general.yaml"
MACRO = REPO / "data" / "macro_inputs" / "us_default.yaml"


needs_data = pytest.mark.skipif(
    not (FSDS.exists() and INDUSTRY.exists() and MACRO.exists()),
    reason="local data corpus not present; run scripts/refresh_*.py and download FSDS first",
)


@needs_data
def test_orchestrator_amzn_extracts_core_financials():
    cfg = load_company_config(COMPANY)
    data = ingest_all(cfg)

    assert data.meta.cik == 1018724
    assert data.pl.net_sales.fy_latest == pytest.approx(716_924, rel=1e-3)
    assert data.pl.operating_income.fy_latest == pytest.approx(79_975, rel=1e-3)
    assert data.bs.cash == pytest.approx(86_810, rel=1e-3)

    # Macro + industry contributed
    assert data.macro.risk_free_rate is not None
    assert data.industry.industry_name == "Retail (General)"

    # Form 4 ingester contributed at least one transaction
    assert len(data.insider_activity) > 0

    # Sources string contains every ingester
    assert "sec-fsds" in (data.meta.source or "")
    assert "macro:" in (data.meta.source or "")
    assert "industry:" in (data.meta.source or "")


@needs_data
def test_orchestrator_to_validated_workbook(tmp_path: Path):
    cfg = load_company_config(COMPANY)
    data = ingest_all(cfg)
    out = tmp_path / "model.xlsx"
    populate_template(data, TEMPLATE, out)
    report = validate_workbook(out)

    # Mechanical ties should hold for the published 10-K numbers.
    failed = [f for f in report.findings if f.severity == Severity.RED]
    assert not failed, f"Validation regressed:\n{report.summary()}"
