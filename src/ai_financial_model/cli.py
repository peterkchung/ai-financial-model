# About: CLI entry point. Subcommands map to pipeline stages
# (ingest-company / generate / validate); `process-company` is the end-to-end
# orchestrator that runs every ingester listed in a company-config YAML,
# merges their outputs, populates the template, and validates the workbook.

from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from ai_financial_model.generation import populate_template
from ai_financial_model.validation import validate_workbook
from ai_financial_model.schema import ExtractedFinancials
from ai_financial_model.pipeline import load_company_config, ingest_all


@click.group()
def cli() -> None:
    """ai-financial-model: company filings → populated valuation model."""


def _write_audit(
    out_dir: Path,
    *,
    cfg: dict,
    data: ExtractedFinancials,
    provenance: dict[str, str],
    pop_report: dict,
    validation_summary: str,
) -> Path:
    """Write a per-run audit log to <out_dir>/audit.json."""
    audit = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "company": data.meta.model_dump(),
        "ingesters": [
            {"type": spec["type"], "args": spec.get("args", {})}
            for spec in cfg.get("ingesters", [])
        ],
        "industry_inline": "industry" in cfg,
        "provenance": provenance,
        "summary": {
            "tagged_cells": pop_report["tagged_cells"],
            "populated": pop_report["populated"],
            "default_kept": pop_report["default_kept"],
            "no_value_extracted": pop_report["skipped_missing"],
        },
        "cells": pop_report["cells"],
        "validation": validation_summary,
    }
    path = out_dir / "audit.json"
    path.write_text(json.dumps(audit, indent=2, default=str))
    return path


@cli.command("ingest-company")
@click.option("--company", type=click.Path(exists=True, path_type=Path), required=True,
              help="Company config YAML listing every ingester to run.")
@click.option("--out", type=click.Path(path_type=Path), required=True,
              help="Where to write the merged ExtractedFinancials JSON.")
def ingest_company(company: Path, out: Path) -> None:
    """Stage 1: run every ingester in `company` config and merge results."""
    cfg = load_company_config(company)
    data, _ = ingest_all(cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(data.model_dump_json(indent=2))
    click.echo(f"Merged from {len(cfg.get('ingesters', []))} ingester(s) → {out}")


@cli.command()
@click.option("--extracted", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--template", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
def generate(extracted: Path, template: Path, out: Path) -> None:
    """Stage 2: populate the template using extracted data."""
    data = ExtractedFinancials.model_validate_json(extracted.read_text())
    report = populate_template(data, template, out)
    click.echo(f"Populated → {out}")
    click.echo(f"  Tagged cells:      {report['tagged_cells']}")
    click.echo(f"  Populated:         {report['populated']}")
    click.echo(f"  Default kept:      {report['default_kept']}")
    click.echo(f"  Empty (no value):  {report['skipped_missing']}")


@cli.command()
@click.option("--workbook", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--tolerance-pct", type=float, default=0.5)
@click.option("--json", "as_json", is_flag=True)
def validate(workbook: Path, tolerance_pct: float, as_json: bool) -> None:
    """Stage 3: run reconciliation and consistency checks."""
    report = validate_workbook(workbook, tolerance_pct=tolerance_pct)
    click.echo(report.model_dump_json(indent=2) if as_json else report.summary())
    if report.overall.value == "red":
        sys.exit(1)


@cli.command("process-company")
@click.option("--company", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--template", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--out-dir", type=click.Path(path_type=Path), required=True)
def process_company(company: Path, template: Path, out_dir: Path) -> None:
    """End-to-end: run every ingester in `company`, populate, validate.

    Writes three artifacts to <out_dir>:
      - extracted.json   — merged ExtractedFinancials
      - model.xlsx       — populated workbook
      - audit.json       — per-cell provenance + run metadata
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = out_dir / "extracted.json"
    out_path = out_dir / "model.xlsx"

    click.echo("[1/3] Orchestrating ingesters…")
    cfg = load_company_config(company)
    data, provenance = ingest_all(cfg)
    extracted_path.write_text(data.model_dump_json(indent=2))
    click.echo(f"  Sources: {data.meta.source}")

    click.echo("[2/3] Populating template…")
    pop_report = populate_template(data, template, out_path, provenance=provenance)
    click.echo(f"  {pop_report['populated']}/{pop_report['tagged_cells']} cells populated "
               f"({pop_report['default_kept']} default kept, "
               f"{pop_report['skipped_missing']} empty)")

    click.echo("[3/3] Validating…")
    report = validate_workbook(out_path)
    click.echo(report.summary())

    audit_path = _write_audit(
        out_dir,
        cfg=cfg, data=data, provenance=provenance,
        pop_report=pop_report,
        validation_summary=report.summary(),
    )

    click.echo(f"\nOutputs:")
    click.echo(f"  {extracted_path}")
    click.echo(f"  {out_path}")
    click.echo(f"  {audit_path}")
    if report.overall.value == "red":
        sys.exit(1)


if __name__ == "__main__":
    cli()
