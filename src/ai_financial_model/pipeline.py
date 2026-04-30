# About: Pipeline orchestrator. Reads a company-config YAML, runs each configured
# ingester in order, deep-merges the resulting ExtractedFinancials, then hands
# the merged data off to the populator and validator.
#
# Each ingester contributes a *partial* ExtractedFinancials populated with
# whatever fields it knows about. Later ingesters override earlier ones for
# overlapping fields (config order = precedence). Lists are concatenated.

from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml

from ai_financial_model.schema import ExtractedFinancials
from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.ingestion.industry import IndustryBenchmarksIngester
from ai_financial_model.ingestion.macro import MacroInputsIngester
from ai_financial_model.ingestion.sec_xbrl import SECXBRLIngester
from ai_financial_model.ingestion.sec_10q import SEC10QIngester
from ai_financial_model.ingestion.sec_10k import SEC10KIngester
from ai_financial_model.ingestion.earnings_release import EarningsReleaseIngester
from ai_financial_model.ingestion.form4 import Form4Ingester


# Registry of ingester types referenced from company configs by short name.
INGESTER_REGISTRY: dict[str, type] = {
    "industry": IndustryBenchmarksIngester,
    "macro": MacroInputsIngester,
    "sec_xbrl": SECXBRLIngester,
    "sec_10q": SEC10QIngester,
    "sec_10k": SEC10KIngester,
    "earnings_release": EarningsReleaseIngester,
    "form4": Form4Ingester,
}


def load_company_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def build_ingester(spec: dict[str, Any]) -> Ingester:
    """A spec is `{type: <name>, args: {...}}`. The args dict is passed as
    kwargs to the ingester constructor; Path values are resolved relative to
    the company config so configs stay portable."""
    type_name = spec["type"]
    if type_name not in INGESTER_REGISTRY:
        raise ValueError(
            f"Unknown ingester type: {type_name}. "
            f"Registered: {sorted(INGESTER_REGISTRY)}")
    cls = INGESTER_REGISTRY[type_name]
    args = dict(spec.get("args", {}))
    # Coerce path-like args
    for k, v in list(args.items()):
        if isinstance(v, str) and (
            v.startswith("data/") or v.startswith("./") or v.endswith((".yaml", ".yml", ".csv", ".xlsx", ".htm", ".html", ".xml"))
            or k.endswith(("_dir", "_path", "path"))
        ):
            args[k] = Path(v)
    return cls(**args)


def merge_into(base: ExtractedFinancials, addition: ExtractedFinancials) -> ExtractedFinancials:
    """Deep-merge `addition` into `base`. Non-None scalars override; lists
    concatenate; nested models recurse."""
    base_d = base.model_dump()
    add_d = addition.model_dump()
    merged = _deep_merge(base_d, add_d)
    return ExtractedFinancials.model_validate(merged)


def _deep_merge(a: Any, b: Any) -> Any:
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _deep_merge(a.get(k), v) if k in a else v
        return out
    if isinstance(a, list) and isinstance(b, list):
        # Concatenate, then de-dup by name+date for InsiderTransaction;
        # otherwise prefer non-empty items.
        if a and b:
            return a + b
        return b or a
    # Scalar (or model becoming dict): prefer non-None addition over base.
    return b if b is not None else a


def ingest_all(config: dict[str, Any]) -> ExtractedFinancials:
    """Run every ingester listed in the config, merge results, return."""
    out = ExtractedFinancials()
    sources: list[str] = []
    for spec in config.get("ingesters", []):
        ingester = build_ingester(spec)
        partial = ingester.extract()
        if partial.meta.source:
            sources.append(partial.meta.source)
        out = merge_into(out, partial)

    # Compose a single source line listing all ingesters used.
    if sources:
        out.meta.source = " + ".join(sources)
    if "meta" in config:
        for k, v in config["meta"].items():
            setattr(out.meta, k, v)
    return out
