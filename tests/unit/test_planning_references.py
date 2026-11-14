"""Referências de candidatas sem cópia ou alteração do inventário autoritativo."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from dona_maria.ingredients import ComplementIngredient
from dona_maria.inventory import InventorySnapshot
from dona_maria.planning import BusinessRuleError, _validate_ingredient_references


@pytest.fixture
def references(pricing_workspace):
    service, workspace, _, _, _, _ = pricing_workspace()
    _, state, snapshot = service.repository.load(workspace, with_snapshot=True)
    candidate = state.candidates[0]
    complement = ComplementIngredient(
        id=str(uuid4()),
        name_original="Mel",
        name_normalized="mel",
        dimension="g",
        evidence=candidate.sources[0].model_dump(mode="json"),
    )
    return snapshot, candidate, complement


@pytest.mark.parametrize(
    "reference", ["inventory", "complement", "unresolved", "foreign", "duplicate"]
)
def test_reference_validation_preserves_guards_and_inputs(references, reference):
    snapshot, candidate, complement = references
    if reference == "complement":
        candidate.ingredients[0].ingredient_id = complement.id
    elif reference == "unresolved":
        candidate.ingredients[0].ingredient_id = None
    elif reference == "foreign":
        candidate.ingredients[0].ingredient_id = uuid4()
    elif reference == "duplicate":
        candidate.ingredients.append(candidate.ingredients[0].model_copy(deep=True))
    before = snapshot.model_dump_json(), candidate.model_dump_json(), complement.model_dump_json()
    if reference in {"foreign", "duplicate"}:
        with pytest.raises(BusinessRuleError) as caught:
            _validate_ingredient_references(snapshot, candidate, [complement])
        assert caught.value.code == ("NOT_FOUND" if reference == "foreign" else "VALIDATION_ERROR")
    else:
        assert _validate_ingredient_references(snapshot, candidate, [complement]) is None
    assert before == (
        snapshot.model_dump_json(),
        candidate.model_dump_json(),
        complement.model_dump_json(),
    )


def test_reference_validation_does_not_copy_the_inventory(references):
    snapshot, candidate, complement = references
    with patch.object(InventorySnapshot, "model_copy", wraps=snapshot.model_copy) as copy:
        _validate_ingredient_references(snapshot, candidate, [complement])
    copy.assert_not_called()
