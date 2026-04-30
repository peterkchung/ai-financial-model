# About: CLI entry point. Subcommands map to pipeline stages
# (ingest / generate / validate); `process-deal` is the orchestrator that
# runs every ingester listed in a deal-config YAML, merges, populates, validates.

from __future__ import annotations
import sys
from pathlib import Path

import click

from ai_financial_model.ingestion.base import detect_ingester
from ai_financial_model.generation import populate_template
from ai_financial_model.validation import validate_workbook
from ai_financial_model.schema import ExtractedFinancials
from ai_financial_model.pipeline import load_deal_config, ingest_all


@click.group()
def cli() -> None:
    """ai-financial-model: data room → populated valuation model."""


@cli.command()
@click.option("--source", "source", type=click.Path(exists=True, path_type=Path), required=True,
              help="Path to a single source document (10-K HTML, PDF, etc.).")
@click.option("--out", "out", type=click.Path(path_type=Path), required=True,
              help="Where to write the extracted JSON.")
def ingest(source: Path, out: Path) -> None:
    """Stage 1 (single-source): parse one document into ExtractedFinancials JSON."""
    ingester = detect_ingester(source)
    extracted = ingester.extract(source)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(extracted.model_dump_json(indent=2))
    click.echo(f"Extracted → {out}")


@cli.command("ingest-deal")
@click.option("--deal", type=click.Path(exists=True, path_type=Path), required=True,
              help="Deal config YAML listing every ingester to run.")
@click.option("--out", type=click.Path(path_type=Path), required=True,
              help="Where to write the merged ExtractedFinancials JSON.")
def ingest_deal(deal: Path, out: Path) -> None:
    """Stage 1 (multi-source): run every ingester in `deal` and merge results."""
    cfg = load_deal_config(deal)
    data = ingest_all(cfg)
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


@cli.command("process-deal")
@click.option("--deal", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--template", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--out-dir", type=click.Path(path_type=Path), required=True)
def process_deal(deal: Path, template: Path, out_dir: Path) -> None:
    """End-to-end: run every ingester in `deal`, populate, validate."""
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = out_dir / "extracted.json"
    out_path = out_dir / "model.xlsx"

    click.echo("[1/3] Orchestrating ingesters…")
    cfg = load_deal_config(deal)
    data = ingest_all(cfg)
    extracted_path.write_text(data.model_dump_json(indent=2))
    click.echo(f"  Sources: {data.meta.source}")

    click.echo("[2/3] Populating template…")
    pop = populate_template(data, template, out_path)
    click.echo(f"  {pop['populated']}/{pop['tagged_cells']} cells populated "
               f"({pop['default_kept']} default kept, {pop['skipped_missing']} empty)")

    click.echo("[3/3] Validating…")
    report = validate_workbook(out_path)
    click.echo(report.summary())
    click.echo(f"\nOutputs:\n  {extracted_path}\n  {out_path}")
    if report.overall.value == "red":
        sys.exit(1)


@cli.command()
@click.option("--source", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--template", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--out-dir", type=click.Path(path_type=Path), required=True)
def process(source: Path, template: Path, out_dir: Path) -> None:
    """Single-source process: ingest one document, populate, validate."""
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = out_dir / "extracted.json"
    out_path = out_dir / "model.xlsx"

    click.echo("[1/3] Ingesting…")
    data = detect_ingester(source).extract(source)
    extracted_path.write_text(data.model_dump_json(indent=2))

    click.echo("[2/3] Generating…")
    populate_template(data, template, out_path)

    click.echo("[3/3] Validating…")
    report = validate_workbook(out_path)
    click.echo(report.summary())
    if report.overall.value == "red":
        sys.exit(1)


if __name__ == "__main__":
    cli()
