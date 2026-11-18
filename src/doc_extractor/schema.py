from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocType(StrEnum):
    INVOICE = "invoice"
    COMMERCIAL_OFFER = "commercial_offer"
    ACT = "act"
    UNKNOWN = "unknown"


class Currency(StrEnum):
    KZT = "KZT"
    USD = "USD"
    EUR = "EUR"


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    qty: float | None = None
    price: float | None = None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: DocType
    supplier_name: str | None = None
    supplier_bin: str | None = Field(default=None, pattern=r"^\d{12}$")
    doc_number: str | None = None
    doc_date: date | None = None
    currency: Currency | None = None
    total_amount: float | None = None
    vat_amount: float | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


SCALAR_FIELDS: tuple[str, ...] = (
    "doc_type",
    "supplier_name",
    "supplier_bin",
    "doc_number",
    "doc_date",
    "currency",
    "total_amount",
    "vat_amount",
)
