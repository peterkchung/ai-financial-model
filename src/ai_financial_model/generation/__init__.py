# About: Generation stage. Takes ExtractedFinancials + a blank template, walks
# the template's cells looking for "Pipeline field:" comments, and writes the
# resolved values into those cells.

from ai_financial_model.generation.populator import populate_template

__all__ = ["populate_template"]
