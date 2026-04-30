# About: Ingestion stage. Takes a source document (10-K HTML, PDF, etc.) and
# emits an ExtractedFinancials. The base Ingester defines the interface; concrete
# implementations live in sibling modules (sec_10k.py, pdf_cim.py, etc.).

from ai_financial_model.ingestion.base import Ingester

__all__ = ["Ingester"]
