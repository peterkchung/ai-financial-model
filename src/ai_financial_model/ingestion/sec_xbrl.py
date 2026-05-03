# About: SEC XBRL ingester. Reads the SEC's Financial Statement Data Sets
# (sub.txt + num.txt) and maps US-GAAP tags to ExtractedFinancials. Far higher
# recall than HTML scraping — every numeric fact in the filing is already
# typed, dated, and tagged.
#
# Dataset: https://www.sec.gov/dera/data/financial-statement-data-sets
# Format: pipe-tab-separated quarterly bulk files (sub, num, pre, tag).

from __future__ import annotations
from pathlib import Path
from typing import Iterable, Optional
import csv

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.schema import ExtractedFinancials, Segment

# Template/schema convention is $-millions. XBRL facts are in $-units.
SCALE_TO_MILLIONS = 1 / 1_000_000


# Tag mapping: schema dotted-path → list of candidate US-GAAP tags
# (priority order; first non-empty match wins). Single-period BS items go in
# their own block since they don't use YearlyValue.
INCOME_STATEMENT_TAGS: dict[str, list[str]] = {
    "pl.net_sales": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "pl.cost_of_sales": [
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
    ],
    "pl.fulfillment": ["FulfillmentExpense"],
    "pl.tech_and_infra": [
        "TechnologyAndInfrastructureExpense",
        "ResearchAndDevelopmentExpense",
    ],
    "pl.sales_and_marketing": [
        "MarketingExpense",
        "SellingAndMarketingExpense",
        "SellingGeneralAndAdministrativeExpense",  # MSFT/GOOGL bundle differently
    ],
    "pl.general_and_admin": ["GeneralAndAdministrativeExpense"],
    # OtherOperatingIncomeExpenseNet is signed as "income (expense), net":
    # positive = net income, negative = net expense. We treat it as an opex
    # component, so flip the sign (handled via NEGATE_FIELDS below).
    "pl.other_operating": ["OtherOperatingIncomeExpenseNet"],
    "pl.total_opex": ["CostsAndExpenses", "OperatingExpenses"],
    "pl.operating_income": ["OperatingIncomeLoss"],
    "pl.interest_income": [
        "InvestmentIncomeInterest",
        "InterestIncomeOperating",
    ],
    "pl.interest_expense": [
        "InterestExpenseNonoperating",
        "InterestExpense",
    ],
    # Use OtherNonoperatingIncomeExpense (the residual "other income, net" line)
    # rather than NonoperatingIncomeExpense (which is the *aggregate* of all
    # non-operating items including interest income/expense — would double-count).
    "pl.other_income": [
        "OtherNonoperatingIncomeExpense",
        "NonoperatingIncomeExpense",
    ],
    "pl.income_before_tax": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "pl.tax_provision": ["IncomeTaxExpenseBenefit"],
    "pl.net_income": ["NetIncomeLoss"],
}

CASH_FLOW_TAGS: dict[str, list[str]] = {
    "cf.capex": [
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ],
    "cf.cash_from_operations": ["NetCashProvidedByUsedInOperatingActivities"],
}

BALANCE_SHEET_TAGS: dict[str, list[str]] = {
    "bs.cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "bs.marketable_securities": [
        "MarketableSecuritiesCurrent",
        "MarketableSecuritiesNoncurrent",
    ],
    "bs.long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
    "bs.lease_liabilities": [
        "LeaseLiabilityNoncurrent",
        "OperatingLeaseLiabilityNoncurrent",
    ],
}

SHARES_TAGS = {
    "shares.outstanding_m": ["CommonStockSharesOutstanding"],  # raw count; convert to millions
}

# Sign conventions: XBRL reports interest expense, capex, tax provision as
# positive magnitudes (we want negatives in the schema). OtherOperating uses
# the "income (expense), net" sign convention (positive=income), but we
# include it as an opex component, so flip.
NEGATE_FIELDS = {
    "pl.interest_expense",
    "pl.tax_provision",
    "cf.capex",
    "pl.other_operating",
}


class _Fact:
    """One row from num.txt."""
    __slots__ = ("adsh", "tag", "ddate", "qtrs", "uom", "segments", "value")

    def __init__(self, adsh, tag, ddate, qtrs, uom, segments, value):
        self.adsh = adsh
        self.tag = tag
        self.ddate = ddate          # YYYYMMDD string
        self.qtrs = int(qtrs) if qtrs else 0
        self.uom = uom
        self.segments = segments    # dimensional axes, e.g. "BusinessSegments=AWSSegment;"
        try:
            self.value = float(value)
        except (TypeError, ValueError):
            self.value = None


class SECXBRLIngester(Ingester):
    """Ingest from a SEC Financial Statement Data Sets directory.

    Args:
        path: directory containing sub.txt and num.txt (e.g. data/sec/financial_statement_data_sets/2026q1/)
        cik: SEC central index key, integer (e.g. 1018724 for AMZN)
        form: filing form to match (default '10-K')
    """

    def __init__(self, path: Path, cik: int, form: str = "10-K"):
        self.path = Path(path)
        self.cik = int(cik)
        self.form = form

    # The base Ingester.extract takes a `source` Path; we accept it for
    # interface compatibility but ignore it (the source spec is in __init__).
    def extract(self, source: Optional[Path] = None) -> ExtractedFinancials:
        sub_path = self.path / "sub.txt"
        num_path = self.path / "num.txt"
        if not sub_path.exists() or not num_path.exists():
            raise FileNotFoundError(
                f"FSDS dir missing sub.txt/num.txt: {self.path}")

        adsh, sub_meta = self._find_filing(sub_path)
        facts = list(self._load_facts(num_path, adsh))

        out = ExtractedFinancials()
        out.meta.source = f"sec-fsds:{self.path.name}:{adsh}"
        out.meta.cik = self.cik
        out.meta.company_name = sub_meta.get("name")
        out.meta.fiscal_year_end = self._fmt_date(sub_meta.get("period"))

        annual_facts = [f for f in facts if f.qtrs == 4 and not f.segments]
        instant_facts = [f for f in facts if f.qtrs == 0 and not f.segments]

        # Map ddates to fy_latest / fy_minus_1 / fy_minus_2 based on the most
        # recent annual periods present.
        annual_dates = sorted({f.ddate for f in annual_facts}, reverse=True)
        date_to_year_field = {}
        for i, d in enumerate(annual_dates[:3]):
            date_to_year_field[d] = ["fy_latest", "fy_minus_1", "fy_minus_2"][i]

        # Income statement + cash flow: yearly values (scaled to $-millions).
        # For each schema field, pick the highest-priority tag that actually
        # has data (priority = position in the candidate list).
        for path, tag_candidates in {**INCOME_STATEMENT_TAGS, **CASH_FLOW_TAGS}.items():
            chosen_tag = next(
                (t for t in tag_candidates
                 if any(f.tag == t and f.ddate in date_to_year_field
                        for f in annual_facts)),
                None,
            )
            if chosen_tag is None:
                continue
            for f in annual_facts:
                if f.tag == chosen_tag and f.ddate in date_to_year_field:
                    year_field = date_to_year_field[f.ddate]
                    val = f.value
                    if val is not None:
                        if path in NEGATE_FIELDS:
                            val = -val      # flip sign (not -abs); preserves
                                            # already-signed values correctly
                        val *= SCALE_TO_MILLIONS
                    self._set_path(out, f"{path}.{year_field}", val)

        # Operating margin base (current year, computed)
        if out.pl.net_sales.fy_latest and out.pl.operating_income.fy_latest:
            out.pl.operating_margin_base = (
                out.pl.operating_income.fy_latest / out.pl.net_sales.fy_latest)

        # Effective tax rate
        if out.pl.income_before_tax.fy_latest and out.pl.tax_provision.fy_latest:
            # tax_provision is stored as negative; rate is positive
            out.tax.effective_rate = (
                abs(out.pl.tax_provision.fy_latest) / out.pl.income_before_tax.fy_latest)

        # Free cash flow: derive if we have OCF + capex
        for yf in ("fy_latest", "fy_minus_1", "fy_minus_2"):
            ocf = getattr(out.cf.cash_from_operations, yf)
            capex = getattr(out.cf.capex, yf)
            if ocf is not None and capex is not None:
                setattr(out.cf.free_cash_flow, yf, ocf + capex)  # capex already negative

        # Balance sheet: latest period only (scaled to $-millions). Honor
        # tag priority: the first candidate with a value at the latest date wins.
        latest_bs_date = max((f.ddate for f in instant_facts), default=None)
        for path, tag_candidates in BALANCE_SHEET_TAGS.items():
            for tag in tag_candidates:
                f = next((x for x in instant_facts
                          if x.tag == tag and x.ddate == latest_bs_date), None)
                if f and f.value is not None:
                    self._set_path(out, path, f.value * SCALE_TO_MILLIONS)
                    break

        # Shares outstanding (latest snapshot, convert to millions)
        latest_shares = max(
            (f for f in instant_facts if f.tag in SHARES_TAGS["shares.outstanding_m"]),
            key=lambda f: f.ddate, default=None)
        if latest_shares and latest_shares.value:
            out.shares.outstanding_m = latest_shares.value / 1_000_000

        # Segments: filter on BusinessSegments dimension in revenue facts
        out.segments = self._build_segments(facts, date_to_year_field)

        return out

    # -- helpers --

    def _find_filing(self, sub_path: Path) -> tuple[str, dict]:
        """Locate the most recent <form> filing for self.cik in sub.txt."""
        with sub_path.open(newline="", encoding="latin-1") as f:
            reader = csv.DictReader(f, delimiter="\t")
            matches = [r for r in reader
                       if r["cik"] and int(r["cik"]) == self.cik
                       and r["form"] == self.form]
        if not matches:
            raise LookupError(
                f"No {self.form} for CIK {self.cik} in {sub_path}")
        # filed is YYYYMMDD; pick the latest
        latest = max(matches, key=lambda r: r["filed"])
        return latest["adsh"], latest

    def _load_facts(self, num_path: Path, adsh: str) -> Iterable[_Fact]:
        """Stream num.txt, yielding only rows for the target adsh."""
        with num_path.open(encoding="latin-1") as f:
            header = f.readline().rstrip("\n").split("\t")
            idx = {col: i for i, col in enumerate(header)}
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if parts[idx["adsh"]] != adsh:
                    continue
                yield _Fact(
                    adsh=parts[idx["adsh"]],
                    tag=parts[idx["tag"]],
                    ddate=parts[idx["ddate"]],
                    qtrs=parts[idx["qtrs"]],
                    uom=parts[idx["uom"]],
                    segments=parts[idx["segments"]],
                    value=parts[idx["value"]],
                )

    def _build_segments(self, facts: list[_Fact], date_to_year_field: dict[str, str]) -> list[Segment]:
        """Aggregate revenue / operating income facts that carry a
        BusinessSegments dimension into Segment records (in $-millions)."""
        revenue_tags = set(INCOME_STATEMENT_TAGS["pl.net_sales"])
        op_inc_tags = set(INCOME_STATEMENT_TAGS["pl.operating_income"])
        by_segment: dict[str, Segment] = {}

        for f in facts:
            if f.qtrs != 4 or "BusinessSegments=" not in (f.segments or ""):
                continue
            seg_name = self._extract_segment_name(f.segments)
            if seg_name is None or f.ddate not in date_to_year_field:
                continue
            year_field = date_to_year_field[f.ddate]
            val = f.value * SCALE_TO_MILLIONS if f.value is not None else None
            seg = by_segment.setdefault(seg_name, Segment(name=seg_name))
            if f.tag in revenue_tags:
                setattr(seg.revenue, year_field, val)
            elif f.tag in op_inc_tags:
                setattr(seg.operating_income, year_field, val)

        # Stable ordering: by latest-year revenue desc.
        segs = list(by_segment.values())
        segs.sort(key=lambda s: -(s.revenue.fy_latest or 0))
        return segs

    @staticmethod
    def _extract_segment_name(segments: str) -> Optional[str]:
        """Pull the BusinessSegments=<Name> value out of the dimension blob."""
        for part in (segments or "").split(";"):
            part = part.strip()
            if part.startswith("BusinessSegments="):
                raw = part.split("=", 1)[1]
                # Convert PascalCaseSegment → "Pascal Case" without the trailing "Segment"
                if raw.endswith("Segment"):
                    raw = raw[: -len("Segment")]
                # Insert spaces before each capital after the first
                out = "".join(
                    (" " + c) if (i > 0 and c.isupper() and not raw[i-1].isupper()) else c
                    for i, c in enumerate(raw)
                )
                return out.strip()
        return None

    @staticmethod
    def _fmt_date(yyyymmdd: Optional[str]) -> Optional[str]:
        if not yyyymmdd or len(yyyymmdd) != 8:
            return None
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"

    @staticmethod
    def _set_path(obj, path: str, value):
        """Set a dotted path on a Pydantic model."""
        parts = path.split(".")
        cur = obj
        for p in parts[:-1]:
            cur = getattr(cur, p)
        setattr(cur, parts[-1], value)
