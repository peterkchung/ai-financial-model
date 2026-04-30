# About: Smoke-test the generation stage end-to-end with a hand-crafted
# ExtractedFinancials → populated workbook → validation. Uses Amazon FY2025
# values as the fixture (matches the public 10-K we have in data/reference/).

from pathlib import Path

import pytest

from ai_financial_model.schema import (
    ExtractedFinancials, Meta, IncomeStatement, CashFlow, BalanceSheet,
    Tax, Shares, Market, Segment, YearlyValue,
)
from ai_financial_model.generation import populate_template
from ai_financial_model.validation import validate_workbook, Severity


REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "templates" / "valuation_template.xlsx"


def amazon_fy2025_fixture() -> ExtractedFinancials:
    return ExtractedFinancials(
        meta=Meta(
            ticker="AMZN",
            company_name="Amazon.com, Inc.",
            valuation_date="2025-12-31",
            source="amazon_10k_fy2025.htm",
        ),
        pl=IncomeStatement(
            net_sales=YearlyValue(fy_minus_2=574_785, fy_minus_1=637_959, fy_latest=716_924),
            cost_of_sales=YearlyValue(fy_minus_2=304_739, fy_minus_1=326_288, fy_latest=356_414),
            fulfillment=YearlyValue(fy_minus_2=90_619, fy_minus_1=98_505, fy_latest=109_074),
            tech_and_infra=YearlyValue(fy_minus_2=85_622, fy_minus_1=88_544, fy_latest=108_521),
            sales_and_marketing=YearlyValue(fy_minus_2=44_370, fy_minus_1=43_900, fy_latest=47_129),
            general_and_admin=YearlyValue(fy_minus_2=11_816, fy_minus_1=11_359, fy_latest=11_172),
            other_operating=YearlyValue(fy_minus_2=767, fy_minus_1=763, fy_latest=4_639),
            total_opex=YearlyValue(fy_minus_2=537_933, fy_minus_1=569_366, fy_latest=636_949),
            operating_income=YearlyValue(fy_minus_2=36_852, fy_minus_1=68_593, fy_latest=79_975),
            interest_income=YearlyValue(fy_minus_2=2_949, fy_minus_1=4_677, fy_latest=4_381),
            interest_expense=YearlyValue(fy_minus_2=-3_182, fy_minus_1=-2_406, fy_latest=-2_274),
            other_income=YearlyValue(fy_minus_2=938, fy_minus_1=-2_250, fy_latest=15_229),
            income_before_tax=YearlyValue(fy_minus_2=37_557, fy_minus_1=68_614, fy_latest=97_311),
            tax_provision=YearlyValue(fy_minus_2=-7_120, fy_minus_1=-9_270, fy_latest=-19_100),
            net_income=YearlyValue(fy_minus_2=30_425, fy_minus_1=59_248, fy_latest=77_670),
            operating_margin_base=79_975 / 716_924,
        ),
        cf=CashFlow(
            capex=YearlyValue(fy_minus_2=-48_133, fy_minus_1=-77_658, fy_latest=-128_320),
            cash_from_operations=YearlyValue(fy_minus_2=84_946, fy_minus_1=115_877, fy_latest=139_514),
            free_cash_flow=YearlyValue(fy_minus_2=36_813, fy_minus_1=38_219, fy_latest=11_194),
        ),
        bs=BalanceSheet(
            cash=86_810, marketable_securities=36_219,
            long_term_debt=65_600, lease_liabilities=87_300,
        ),
        tax=Tax(effective_rate=19_100 / 97_311),
        shares=Shares(outstanding_m=10_734.92),
        market=Market(market_cap_m=None, price_per_share=None),
        segments=[
            Segment(name="North America",
                    revenue=YearlyValue(fy_minus_2=352_828, fy_minus_1=387_497, fy_latest=426_298),
                    operating_income=YearlyValue(fy_minus_2=14_877, fy_minus_1=24_961, fy_latest=28_881)),
            Segment(name="International",
                    revenue=YearlyValue(fy_minus_2=131_200, fy_minus_1=142_925, fy_latest=161_902),
                    operating_income=YearlyValue(fy_minus_2=-2_656, fy_minus_1=3_787, fy_latest=6_864)),
            Segment(name="AWS",
                    revenue=YearlyValue(fy_minus_2=90_757, fy_minus_1=107_537, fy_latest=128_724),
                    operating_income=YearlyValue(fy_minus_2=24_631, fy_minus_1=39_834, fy_latest=44_230)),
        ],
    )


@pytest.fixture
def out_path(tmp_path: Path) -> Path:
    return tmp_path / "model.xlsx"


def test_template_exists():
    assert TEMPLATE.exists(), "Run `make template` first."


def test_populate_amazon(out_path: Path):
    data = amazon_fy2025_fixture()
    report = populate_template(data, TEMPLATE, out_path)

    # Every tagged cell should either be populated or recorded as missing.
    assert report["tagged_cells"] > 0
    assert report["populated"] + report["skipped_missing"] == report["tagged_cells"]
    # We populated most fields except market price; expect populated >> missing.
    assert report["populated"] >= report["skipped_missing"]


def test_populated_workbook_validates_green(out_path: Path):
    data = amazon_fy2025_fixture()
    populate_template(data, TEMPLATE, out_path)
    report = validate_workbook(out_path)

    # Mechanical ties should hold for the published 10-K numbers.
    failed = [f for f in report.findings if f.severity == Severity.RED]
    assert not failed, f"Unexpected RED findings:\n{report.summary()}"
