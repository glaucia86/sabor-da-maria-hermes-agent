"""Contrato de leitura do estado, com SQLite e manifestações sintéticas."""

from copy import deepcopy

import pytest

import dona_maria.business_state as business_state


@pytest.fixture
def projection_workspace(pricing_workspace):
    def create(stage):
        service, workspace, recipe, acceptance, command, database = pricing_workspace()
        evidence = dict(
            turn_ref="synthetic-f3",
            statement="Escolho M20.",
            captured_at=service.clock().isoformat(),
        )
        if stage in {"priced", "selected", "rejected"}:
            calculation = command(
                "calculate_pricing_scenarios",
                recipe_id=recipe["id"],
                acceptance_id=acceptance["id"],
            )["data"]["calculation"]
            if stage != "priced":
                chosen = command(
                    "save_menu_decision",
                    recipe_id=recipe["id"],
                    acceptance_id=acceptance["id"],
                    calculation_id=calculation["id"],
                    scenario_id="M20",
                    evidence=evidence,
                )
                assert chosen["ok"], chosen
        if stage in {"ready", "undecided", "rejected"}:
            feedback = {"ready": "INTERESTED", "undecided": "UNDECIDED", "rejected": "REJECTED"}[
                stage
            ]
            saved = command(
                "record_recipe_feedback",
                recipe_id=recipe["id"],
                feedback=feedback,
                evidence=evidence | {"statement": f"Registro meu feedback: {feedback}."},
            )
            assert saved["ok"], saved
        return service, workspace, recipe, acceptance, database

    return create


@pytest.mark.parametrize(
    ("stage", "status", "next_action"),
    [
        ("accepted", "ACCEPTED", "REVIEW_ACCEPTED_RECIPES"),
        ("priced", "PRICED", "ASK_PRICE_CHOICE"),
        ("selected", "MENU_SELECTED", "REVIEW_MENU"),
        ("ready", "READY_FOR_ACCEPTANCE", "ASK_EXPLICIT_ACCEPTANCE"),
        ("undecided", "DISCOVERED", "CLARIFY_CANDIDATE_GAPS"),
        ("rejected", "REJECTED", "RESEARCH_CANDIDATE"),
    ],
)
def test_read_projection_preserves_status_history_envelope_and_database(
    projection_workspace, stage, status, next_action
):
    service, workspace, recipe, acceptance, database = projection_workspace(stage)
    revision, _ = service.repository.load(workspace)
    before = database.read_bytes()
    result = service.get_business_state({"workspace_id": workspace})
    assert {key: value for key, value in result.items() if key != "data"} == dict(
        schema_version="1.0",
        ok=True,
        workspace_id=workspace,
        revision=revision,
        operation_id=None,
        warnings=[],
        error=None,
    )
    data = result["data"]
    assert set(data) == {
        "inventory_snapshot_id",
        "budget_initial",
        "budget_remaining",
        "candidates",
        "complement_ingredients",
        "complement_quotes",
        "ingredient_conversions",
        "ingredient_resolutions",
        "acceptances",
        "pricing_calculations",
        "menu_decisions",
        "menu",
        "evaluation",
        "plan",
        "kitchen_facts",
        "preferences",
        "next_action",
    }
    assert data["candidates"][0]["id"] == recipe["id"]
    assert data["candidates"][0]["status"] == status
    assert data["next_action"] == next_action
    assert data["budget_initial"] == data["budget_remaining"] == "80.00"
    assert data["acceptances"][0]["id"] == acceptance["id"]
    invalidated = stage in {"ready", "undecided", "rejected"}
    assert data["acceptances"][0]["validity"] == ("INVALIDATED" if invalidated else "VALID")
    assert len(data["menu"]) == (1 if stage == "selected" else 0)
    if stage == "rejected":
        assert data["plan"]["items"] == []
        assert data["pricing_calculations"][0]["validity"] == "INVALIDATED"
        assert data["menu_decisions"][0]["validity"] == "INVALIDATED"
    assert service.get_business_state({"workspace_id": workspace}) == result
    assert database.read_bytes() == before


@pytest.mark.parametrize("stage", ["accepted", "selected", "rejected"])
def test_projection_is_repeatable_and_does_not_mutate_inputs(projection_workspace, stage):
    service, workspace, _, _, database = projection_workspace(stage)
    _, state, _ = service.repository.load(workspace, with_snapshot=True)
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    expected = service.get_business_state({"workspace_id": workspace})["data"]
    state_before = state.model_dump_json()
    evaluation_before = deepcopy(evaluation)
    database_before = database.read_bytes()

    projected = business_state._project_business_state(state, evaluation, service.clock())
    assert projected == expected
    assert state.model_dump_json() == state_before
    assert evaluation == evaluation_before

    projected["candidates"][0]["title"] = "Alteração apenas da representação devolvida"
    projected["plan"]["items"].clear()
    assert business_state._project_business_state(state, evaluation, service.clock()) == expected
    assert state.model_dump_json() == state_before
    assert evaluation == evaluation_before
    assert database.read_bytes() == database_before
