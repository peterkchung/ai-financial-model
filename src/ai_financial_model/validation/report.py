# About: Validation report schema. Each Finding represents one check result;
# ValidationReport aggregates them and exposes a green/yellow/red roll-up.

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class Finding(BaseModel):
    check: str
    severity: Severity
    message: str
    expected: Optional[float] = None
    actual: Optional[float] = None
    variance_pct: Optional[float] = None
    cell_refs: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    findings: list[Finding] = Field(default_factory=list)

    @property
    def overall(self) -> Severity:
        if any(f.severity == Severity.RED for f in self.findings):
            return Severity.RED
        if any(f.severity == Severity.YELLOW for f in self.findings):
            return Severity.YELLOW
        return Severity.GREEN

    def summary(self) -> str:
        lines = [f"Overall: {self.overall.value.upper()}", ""]
        by_sev = {Severity.RED: [], Severity.YELLOW: [], Severity.GREEN: []}
        for f in self.findings:
            by_sev[f.severity].append(f)
        for sev in (Severity.RED, Severity.YELLOW, Severity.GREEN):
            if by_sev[sev]:
                lines.append(f"-- {sev.value.upper()} ({len(by_sev[sev])}) --")
                for f in by_sev[sev]:
                    lines.append(f"  [{f.check}] {f.message}")
        return "\n".join(lines)
