# About: Generation stage. Two functions:
#   populate_template — write resolved schema values into the template's tagged cells
#   write_mapping     — emit a per-run mapping.md describing the wiring used

from ai_financial_model.generation.populator import populate_template
from ai_financial_model.generation.mapping import (
    build_mapping_md,
    enumerate_template_cells,
    write_mapping,
)

__all__ = [
    "populate_template",
    "build_mapping_md",
    "enumerate_template_cells",
    "write_mapping",
]
