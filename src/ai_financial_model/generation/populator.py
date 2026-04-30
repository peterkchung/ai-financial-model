# About: Populator — the bridge between ExtractedFinancials and the blank
# Excel template. The template carries the field-to-cell mapping inline as
# cell comments (e.g. "Pipeline field: pl.net_sales.fy_latest"); the populator
# scans for those comments, resolves each path against the data, and writes.
# Cells whose fields are None in the data are left empty with a reason-code
# comment — never filled with zeros (per PRD §13: "no hallucinated numbers").

from __future__ import annotations
from pathlib import Path
import re
import shutil
from typing import Any

from openpyxl import load_workbook
from openpyxl.comments import Comment

from ai_financial_model.schema import ExtractedFinancials

PIPELINE_TAG = re.compile(r"Pipeline field:\s*([\w\.\[\]]+)")


def _resolve(data: Any, path: str) -> Any:
    """Walk a dotted path against a Pydantic model or dict.

    Supports list indexing via `[i]`, e.g. `segments[0].revenue.fy_latest`.
    Returns None if any segment is missing or out-of-range — never raises.
    """
    parts = re.findall(r"[\w_]+|\[\d+\]", path)
    cur: Any = data
    for p in parts:
        if cur is None:
            return None
        if p.startswith("["):
            idx = int(p[1:-1])
            try:
                cur = cur[idx]
            except (IndexError, TypeError):
                return None
        else:
            cur = getattr(cur, p, None) if not isinstance(cur, dict) else cur.get(p)
    return cur


def populate_template(
    extracted: ExtractedFinancials,
    template_path: Path,
    output_path: Path,
) -> dict[str, int]:
    """Copy the blank template to `output_path`, then write all resolvable
    fields into their tagged cells. Returns a small report dict.

    The output preserves the template's formulas, formatting, and color coding.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(template_path, output_path)

    wb = load_workbook(output_path)
    populated = 0
    skipped_missing = 0
    seen = 0

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.comment is None:
                    continue
                m = PIPELINE_TAG.search(cell.comment.text)
                if not m:
                    continue
                seen += 1
                path = m.group(1)
                value = _resolve(extracted, path)
                if value is None:
                    skipped_missing += 1
                    cell.comment = Comment(
                        f"Pipeline field: {path}\nReason: NO_VALUE_EXTRACTED",
                        "pipeline",
                    )
                    continue
                cell.value = value
                cell.comment = Comment(
                    f"Pipeline field: {path}\nSource: {extracted.meta.source or 'unknown'}",
                    "pipeline",
                )
                populated += 1

    wb.save(output_path)
    return {"tagged_cells": seen, "populated": populated, "skipped_missing": skipped_missing}
