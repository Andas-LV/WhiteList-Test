import json
from pathlib import Path

import pytest

from doc_extractor.grounding import ground
from doc_extractor.schema import SCALAR_FIELDS, ExtractionResult

DATA = Path(__file__).resolve().parents[1] / "data"
DOCS = sorted((DATA / "docs").glob("*.txt"))


def test_dataset_size_and_pairs() -> None:
    assert len(DOCS) >= 10
    expected = {p.stem for p in (DATA / "expected").glob("*.json")}
    assert {p.stem for p in DOCS} == expected


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.stem)
def test_reference_is_grounded_in_text(doc: Path) -> None:
    raw = json.loads((DATA / "expected" / f"{doc.stem}.json").read_text(encoding="utf-8"))
    reference = ExtractionResult.model_validate(raw)
    grounded = ground(reference, doc.read_text(encoding="utf-8"))

    for field in SCALAR_FIELDS:
        assert getattr(grounded, field) == getattr(reference, field), field
    assert grounded.line_items == reference.line_items
