import pytest
from pydantic import ValidationError

from doc_extractor.schema import ExtractionResult


def test_minimal_valid() -> None:
    result = ExtractionResult.model_validate({"doc_type": "unknown"})
    assert result.supplier_bin is None
    assert result.line_items == []


@pytest.mark.parametrize("bad_bin", ["12345", "2l0640900l80", "1234567890123"])
def test_bin_must_be_12_digits(bad_bin: str) -> None:
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({"doc_type": "invoice", "supplier_bin": bad_bin})


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({"doc_type": "act", "iban": "KZ00"})
