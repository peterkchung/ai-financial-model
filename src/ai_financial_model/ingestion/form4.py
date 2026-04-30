# About: SEC Form 4 ingester (insider transactions). Each filing is an XML
# blob describing one insider's reportable trades on a given date. We parse
# the standard fields (insider name/title, transaction code, shares, price)
# and append to ExtractedFinancials.insider_activity.

from __future__ import annotations
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.schema import ExtractedFinancials, InsiderTransaction


class Form4Ingester(Ingester):
    """Read all Form 4 XMLs in a directory; aggregate transactions."""

    def __init__(self, form4_dir: Path, glob: str = "4_*.xml"):
        self.form4_dir = Path(form4_dir)
        self.glob = glob

    def extract(self, source: Optional[Path] = None) -> ExtractedFinancials:
        out = ExtractedFinancials()
        for path in sorted(self.form4_dir.glob(self.glob)):
            try:
                txs = self._parse_one(path)
            except ET.ParseError:
                continue
            out.insider_activity.extend(txs)
        # Most recent first
        out.insider_activity.sort(key=lambda t: t.filed_date or "", reverse=True)
        out.meta.source = f"form4:{self.form4_dir.name}"
        return out

    @staticmethod
    def _parse_one(path: Path) -> list[InsiderTransaction]:
        tree = ET.parse(path)
        root = tree.getroot()

        insider_name = (root.findtext(".//reportingOwnerId/rptOwnerName") or "").strip()
        insider_title = (root.findtext(".//reportingOwner/reportingOwnerRelationship/officerTitle")
                         or root.findtext(".//reportingOwner/reportingOwnerRelationship/isOfficer")
                         or "").strip()

        out: list[InsiderTransaction] = []
        for tx in root.findall(".//nonDerivativeTransaction"):
            code = (tx.findtext(".//transactionCoding/transactionCode") or "").strip()
            shares = _f(tx.findtext(".//transactionAmounts/transactionShares/value"))
            price = _f(tx.findtext(".//transactionAmounts/transactionPricePerShare/value"))
            tx_date = (tx.findtext(".//transactionDate/value") or "").strip()
            value = (shares or 0) * (price or 0) if shares and price else None
            out.append(InsiderTransaction(
                filed_date=tx_date or None,
                insider_name=insider_name or None,
                insider_title=insider_title or None,
                transaction_code=code or None,
                shares=shares,
                price_per_share=price,
                transaction_value=value,
            ))
        return out


def _f(s) -> Optional[float]:
    if s is None or not s.strip():
        return None
    try:
        return float(s)
    except ValueError:
        return None
