# About: Single source of truth for the pipeline's data contract. The blank
# template's green cells carry comments like "Pipeline field: pl.net_sales.fy_latest"
# that resolve against this Pydantic model. Adding a new green cell means adding
# a field here.

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class YearlyValue(BaseModel):
    fy_minus_2: Optional[float] = None
    fy_minus_1: Optional[float] = None
    fy_latest: Optional[float] = None


class IncomeStatement(BaseModel):
    net_sales: YearlyValue = Field(default_factory=YearlyValue)
    cost_of_sales: YearlyValue = Field(default_factory=YearlyValue)
    fulfillment: YearlyValue = Field(default_factory=YearlyValue)
    tech_and_infra: YearlyValue = Field(default_factory=YearlyValue)
    sales_and_marketing: YearlyValue = Field(default_factory=YearlyValue)
    general_and_admin: YearlyValue = Field(default_factory=YearlyValue)
    other_operating: YearlyValue = Field(default_factory=YearlyValue)
    total_opex: YearlyValue = Field(default_factory=YearlyValue)
    operating_income: YearlyValue = Field(default_factory=YearlyValue)
    interest_income: YearlyValue = Field(default_factory=YearlyValue)
    interest_expense: YearlyValue = Field(default_factory=YearlyValue)
    other_income: YearlyValue = Field(default_factory=YearlyValue)
    income_before_tax: YearlyValue = Field(default_factory=YearlyValue)
    tax_provision: YearlyValue = Field(default_factory=YearlyValue)
    net_income: YearlyValue = Field(default_factory=YearlyValue)
    operating_margin_base: Optional[float] = None


class CashFlow(BaseModel):
    capex: YearlyValue = Field(default_factory=YearlyValue)
    cash_from_operations: YearlyValue = Field(default_factory=YearlyValue)
    free_cash_flow: YearlyValue = Field(default_factory=YearlyValue)


class BalanceSheet(BaseModel):
    cash: Optional[float] = None
    marketable_securities: Optional[float] = None
    long_term_debt: Optional[float] = None
    lease_liabilities: Optional[float] = None


class Tax(BaseModel):
    effective_rate: Optional[float] = None


class Shares(BaseModel):
    outstanding_m: Optional[float] = None


class Market(BaseModel):
    market_cap_m: Optional[float] = None
    price_per_share: Optional[float] = None


class Segment(BaseModel):
    name: Optional[str] = None
    revenue: YearlyValue = Field(default_factory=YearlyValue)
    operating_income: YearlyValue = Field(default_factory=YearlyValue)


class Meta(BaseModel):
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    valuation_date: Optional[str] = None
    source: Optional[str] = None
    cik: Optional[int] = None
    fiscal_year_end: Optional[str] = None  # YYYY-MM-DD


class MacroInputs(BaseModel):
    """Macro / market data; feeds the Inputs sheet (rf, credit spread, etc.)."""
    risk_free_rate: Optional[float] = None        # e.g. 10Y UST yield, decimal
    long_bond_rate: Optional[float] = None        # 30Y UST
    baa_corporate_yield: Optional[float] = None   # for credit spread
    credit_spread_baa: Optional[float] = None     # baa - rf
    fx_usd_eur: Optional[float] = None
    cpi_yoy: Optional[float] = None
    real_gdp_growth: Optional[float] = None
    as_of_date: Optional[str] = None


class IndustryBenchmarks(BaseModel):
    """Industry-aggregate inputs (typically NYU Stern / Damodaran datasets)."""
    industry_name: Optional[str] = None
    levered_beta: Optional[float] = None
    unlevered_beta: Optional[float] = None
    equity_risk_premium: Optional[float] = None
    pretax_operating_margin: Optional[float] = None
    return_on_invested_capital: Optional[float] = None
    cost_of_capital: Optional[float] = None
    sales_to_capital: Optional[float] = None
    as_of_date: Optional[str] = None


class InsiderTransaction(BaseModel):
    filed_date: Optional[str] = None
    insider_name: Optional[str] = None
    insider_title: Optional[str] = None
    transaction_code: Optional[str] = None  # P=purchase, S=sale, A=award, etc.
    shares: Optional[float] = None
    price_per_share: Optional[float] = None
    transaction_value: Optional[float] = None


class ForwardGuidance(BaseModel):
    """Pulled from earnings press release / CFO commentary."""
    period: Optional[str] = None  # e.g. "Q2 2026", "FY2026"
    revenue_low: Optional[float] = None
    revenue_high: Optional[float] = None
    operating_income_low: Optional[float] = None
    operating_income_high: Optional[float] = None
    notes: Optional[str] = None


class ExtractedFinancials(BaseModel):
    """The contract between Ingestion and Generation.

    Every green cell in the template has a comment of the form
    "Pipeline field: <dotted.path>" that resolves against this model.
    """
    meta: Meta = Field(default_factory=Meta)
    pl: IncomeStatement = Field(default_factory=IncomeStatement)
    cf: CashFlow = Field(default_factory=CashFlow)
    bs: BalanceSheet = Field(default_factory=BalanceSheet)
    tax: Tax = Field(default_factory=Tax)
    shares: Shares = Field(default_factory=Shares)
    market: Market = Field(default_factory=Market)
    segments: list[Segment] = Field(default_factory=list)
    macro: MacroInputs = Field(default_factory=MacroInputs)
    industry: IndustryBenchmarks = Field(default_factory=IndustryBenchmarks)
    insider_activity: list[InsiderTransaction] = Field(default_factory=list)
    forward_guidance: Optional[ForwardGuidance] = None
