# About: Pipeline orchestrator. Reads a company-config YAML, runs each configured
# ingester in order, deep-merges the resulting ExtractedFinancials, layers in
# the inline analyst assumptions block, then hands the merged data off to the
# populator and validator.
#
# Each ingester contributes a *partial* ExtractedFinancials populated with
# whatever fields it knows about. Later ingesters override earlier ones for
# overlapping fields (config order = precedence). Lists are concatenated.
# The top-level `industry:` block in the company config wins last — those
# values are the analyst's deliberate calibration.
#
# The orchestrator also tracks per-field provenance — which ingester (or
# inline block) contributed each value — so the populator can surface that
# in audit.json.

from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable

import yaml

from ai_financial_model.schema import ExtractedFinancials, IndustryBenchmarks
from ai_financial_model.ingestion.base import Ingester
from ai_financial_model.ingestion.macro import MacroInputsIngester
from ai_financial_model.ingestion.sec_xbrl import SECXBRLIngester
from ai_financial_model.ingestion.sec_10q import SEC10QIngester
from ai_financial_model.ingestion.earnings_release import EarningsReleaseIngester
from ai_financial_model.ingestion.non_recurring import NonRecurringItemsIngester
from ai_financial_model.ingestion.form4 import Form4Ingester


# Registry of ingester types referenced from company configs by short name.
INGESTER_REGISTRY: dict[str, type] = {
    "macro": MacroInputsIngester,
    "sec_xbrl": SECXBRLIngester,
    "sec_10q": SEC10QIngester,
    "earnings_release": EarningsReleaseIngester,
    "non_recurring_items": NonRecurringItemsIngester,
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
    for k, v in list(args.items()):
        if isinstance(v, str) and (
            v.startswith("data/") or v.startswith("./")
            or v.endswith((".yaml", ".yml", ".csv", ".xlsx", ".htm", ".html", ".xml"))
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
        if a and b:
            return a + b
        return b or a
    return b if b is not None else a


def _walk_paths(obj: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    """Yield (dotted_path, value) for every non-None leaf of a Pydantic model
    or nested dict/list. List elements get [i] indexing in the path."""
    if hasattr(obj, "model_dump"):
        d = obj.model_dump()
    elif isinstance(obj, dict):
        d = obj
    else:
        if obj is not None:
            yield prefix, obj
        return
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            yield from _walk_paths(v, path)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                yield from _walk_paths(item, f"{path}[{i}]")
        elif v is not None:
            yield path, v


def ingest_all(config: dict[str, Any]) -> tuple[ExtractedFinancials, dict[str, str]]:
    """Run every ingester listed in the config, merge results, layer in the
    inline `industry:` block.

    Returns:
        (merged_data, provenance) — provenance maps each populated dotted-path
        to the source-string of the ingester (or "industry:inline") that
        contributed it. Later contributors override earlier ones for the same
        path, mirroring the merge order.
    """
    out = ExtractedFinancials()
    provenance: dict[str, str] = {}
    sources: list[str] = []

    for spec in config.get("ingesters", []):
        ingester = build_ingester(spec)
        partial = ingester.extract()
        partial_source = partial.meta.source or spec["type"]
        for path, _ in _walk_paths(partial):
            provenance[path] = partial_source
        if partial.meta.source:
            sources.append(partial.meta.source)
        out = merge_into(out, partial)

    if "industry" in config:
        industry_partial = ExtractedFinancials()
        industry_partial.industry = IndustryBenchmarks(**config["industry"])
        for path, _ in _walk_paths(industry_partial):
            provenance[path] = "industry:inline"
        sources.append("industry:inline")
        out = merge_into(out, industry_partial)

    if sources:
        out.meta.source = " + ".join(sources)
    if "meta" in config:
        for k, v in config["meta"].items():
            setattr(out.meta, k, v)
            provenance[f"meta.{k}"] = "company-config"
    return out, provenance
