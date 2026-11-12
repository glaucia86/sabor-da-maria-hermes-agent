"""S03 pela API pública, com custos e receitas inteiramente sintéticos."""

import json
import sqlite3
from decimal import Decimal, Inexact, localcontext
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.pricing import calculate_pricing


def evidence(statement):
    return dict(
        turn_ref="synthetic-pricing-turn",
        statement=statement,
        captured_at="2026-11-11T00:00:00Z",
    )


def test_known_cmv_produces_minimum_without_choosing_for_the_user(pricing_workspace):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace()
    result = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    assert result["ok"], result
    calculation = result["data"]["calculation"]
    assert calculation["cmv_per_serving"] == "10.00"
    assert calculation["minimum"]["price"] == "11.12"
    assert calculation["minimum"]["result_theoretical"] == "0.0080"
    assert [(s["scenario_id"], s["price"]) for s in calculation["scenarios"]] == [
        ("M10", "12.50"),
        ("M20", "14.29"),
        ("M30", "16.67"),
    ]
    assert [
        tuple(
            Decimal(s[key])
            for key in ("fee_theoretical", "receipt_theoretical", "result_theoretical")
        )
        for s in calculation["scenarios"]
    ] == [
        (Decimal("1.250"), Decimal("11.250"), Decimal("1.250")),
        (Decimal("1.429"), Decimal("12.861"), Decimal("2.861")),
        (Decimal("1.667"), Decimal("15.003"), Decimal("5.003")),
    ]
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["menu_decisions"] == []
    assert state["acceptances"][0]["validity"] == "VALID"
    assert state["budget_remaining"] == "80.00"
    assert state["candidates"][0]["status"] == "PRICED"
    assert state["next_action"] == "ASK_PRICE_CHOICE"


def test_explicit_scenario_choice_survives_reopening_and_replay(pricing_workspace):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    request = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=service.get_business_state({"workspace_id": workspace})["revision"],
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence=evidence("Escolho o cenário M20."),
    )
    saved = service.save_menu_decision(request)
    assert saved["ok"], saved
    assert saved["data"]["decision"]["price"] == "14.29"
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    assert reopened.save_menu_decision(request) == saved
    state = reopened.get_business_state({"workspace_id": workspace})
    assert state["revision"] == saved["revision"]
    assert state["data"]["menu_decisions"] == [saved["data"]["decision"]]
    assert state["data"]["acceptances"][0]["validity"] == "VALID"
    assert state["data"]["budget_remaining"] == "80.00"
    assert state["data"]["candidates"][0]["status"] == "MENU_SELECTED"
    assert state["data"]["next_action"] == "REVIEW_MENU"


@pytest.mark.parametrize("purchased", ["1E+3", "1.00E+3"])
def test_scientific_purchase_quantity_allows_reopening_and_choosing_price(
    pricing_workspace, purchased
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace(
        purchased=purchased
    )
    result = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    assert result["ok"], result
    calculation = result["data"]["calculation"]
    assert calculation["allocations"][0]["purchase_quantity_base"] == "1000"
    assert Decimal(calculation["cmv_per_serving"]) == Decimal("1.00")

    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    recovered = reopened.get_business_state({"workspace_id": workspace})
    assert recovered["ok"], recovered
    assert recovered["data"]["pricing_calculations"] == [calculation]
    saved = reopened.save_menu_decision(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=recovered["revision"],
            recipe_id=recipe["id"],
            acceptance_id=acceptance["id"],
            calculation_id=calculation["id"],
            scenario_id="M20",
            evidence=evidence("Escolho M20."),
        )
    )
    assert saved["ok"], saved
    state = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )
    assert state["ok"], state
    assert state["data"]["menu"] == [saved["data"]["decision"]]
    assert state["data"]["menu"][0]["price"] == "1.43"


@pytest.mark.parametrize(
    "price, code",
    [
        ("11.12", None),
        ("11.11", "PRICE_BELOW_MINIMUM"),
        ("0", "VALIDATION_ERROR"),
        ("-1.00", "VALIDATION_ERROR"),
        ("11.121", "VALIDATION_ERROR"),
        (11.12, "VALIDATION_ERROR"),
        (True, "VALIDATION_ERROR"),
        ("NaN", "VALIDATION_ERROR"),
        ("Infinity", "VALIDATION_ERROR"),
        ("1e2", "VALIDATION_ERROR"),
        ("+12.00", "VALIDATION_ERROR"),
        (" 12.00", "VALIDATION_ERROR"),
        ("1000000000000.00", "VALIDATION_ERROR"),
    ],
)
def test_custom_price_uses_technical_floor_and_cent_input(pricing_workspace, price, code):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        custom_price=price,
        evidence=evidence(f"Escolho o preço de R$ {price}."),
    )
    if code:
        assert result["ok"] is False
        assert result["error"]["code"] == code
        if code == "PRICE_BELOW_MINIMUM":
            assert result["error"]["details"]["minimum_price"] == "11.12"
            assert Decimal(result["error"]["details"]["result_theoretical"]) == Decimal("-0.001")
        assert service.get_business_state({"workspace_id": workspace}) == before
    else:
        assert result["ok"], result
        assert result["data"]["decision"]["price"] == "11.12"
        option = result["data"]["chosen_option"]
        assert Decimal(option["result_theoretical"]) == Decimal("0.008")
        assert option["display"] == dict(cmv="10.00", fee="1.11", receipt="10.01", result="0.01")


@pytest.mark.parametrize(
    "statement",
    [
        "Talvez M20.",
        "Escolho o cenário M10.",
        "Aceito este prato.",
        "Escolho M20 se for bom.",
        "A página recomenda M20.",
    ],
)
def test_choice_requires_unambiguous_human_statement_for_exact_option(pricing_workspace, statement):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence=evidence(statement),
    )
    assert result["error"]["code"] == "USER_CONFIRMATION_REQUIRED"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_material_plan_change_invalidates_price_and_refuses_old_calculation(pricing_workspace):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    choice = dict(
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence=evidence("Escolho M20."),
    )
    assert command("save_menu_decision", **choice)["ok"]
    command("set_production_plan", items=[], evidence=evidence("Confirmo limpar o rascunho."))
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["pricing_calculations"][0]["validity"] == "INVALIDATED"
    assert state["menu_decisions"][0]["validity"] == "INVALIDATED"
    assert state["menu"] == []
    assert command("save_menu_decision", **choice)["error"]["code"] == "STALE_EVALUATION"
    assert (
        command(
            "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
        )["error"]["code"]
        == "STALE_EVALUATION"
    )


def test_recalculation_reuses_snapshot_and_price_replacement_preserves_acceptance(
    pricing_workspace,
):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace()
    inputs = dict(recipe_id=recipe["id"], acceptance_id=acceptance["id"])
    first = command("calculate_pricing_scenarios", **inputs)["data"]["calculation"]
    second = command("calculate_pricing_scenarios", **inputs)["data"]["calculation"]
    assert second == first
    for scenario in ("M10", "M30"):
        assert command(
            "save_menu_decision",
            **inputs,
            calculation_id=first["id"],
            scenario_id=scenario,
            evidence=evidence(f"Escolho {scenario}."),
        )["ok"]
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert len(state["pricing_calculations"]) == 1
    assert [d["validity"] for d in state["menu_decisions"]] == ["INVALIDATED", "VALID"]
    assert [d["price"] for d in state["menu"]] == ["16.67"]
    assert state["acceptances"][0]["validity"] == "VALID"


def test_periodic_cost_preserves_precision_scale_and_rounding_note(pricing_workspace):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace(
        total="1.00", purchased="3", consumed="1", servings=1, batches=3
    )
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    assert calculation["cmv_production"] == "0.9999999999999999999999999999999999"
    assert calculation["cmv_average_batch"] == "0.3333333333333333333333333333333333"
    assert calculation["cmv_per_serving"] == "0.3333333333333333333333333333333333"
    assert calculation["planned_servings"] == 3
    allocation = calculation["allocations"][0]
    assert allocation["quantity"] == "3"
    assert allocation["purchase_quantity_base"] == "3"
    assert allocation["acquisition_total"] == "1.00"
    assert allocation["origin"] == "INVENTORY"
    assert allocation["source"]["kind"] == "XLSX"
    assert "aproximação didática" in " ".join(calculation["explanation"])


def test_pricing_owns_decimal_context_even_when_caller_traps_inexact(pricing_workspace):
    _, _, recipe, acceptance, command, _ = pricing_workspace(
        total="1.00", purchased="3", consumed="1", servings=1
    )
    with localcontext() as caller:
        caller.prec = 6
        caller.traps[Inexact] = True
        result = command(
            "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
        )
    assert result["ok"], result
    assert (
        result["data"]["calculation"]["cmv_per_serving"] == "0.3333333333333333333333333333333333"
    )


def test_subcent_ingredients_are_summed_before_rounding_with_explanation(pricing_workspace):
    _, _, recipe, acceptance, command, _ = pricing_workspace(
        total="1.00", purchased="1", consumed="0.004", servings=1, parts=2
    )
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    assert Decimal(calculation["cmv_per_serving"]) == Decimal("0.008")
    assert [Decimal(a["subtotal"]) for a in calculation["allocations"]] == [
        Decimal("0.004"),
        Decimal("0.004"),
    ]
    assert calculation["minimum"]["display"]["cmv"] == "0.01"
    assert any("subtotais arredondados" in note for note in calculation["explanation"])


@settings(
    max_examples=25, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None
)
@given(
    cents=st.integers(min_value=1, max_value=99999999999999),
    servings=st.integers(min_value=1, max_value=1000000),
)
def test_minimum_and_scenario_properties_at_public_service(pricing_workspace, cents, servings):
    # Entradas finitas autorizadas; consumo diminuto também exercita empates de preços.
    total = format(Decimal(cents).scaleb(-2), ".2f")
    _, _, recipe, acceptance, command, _ = pricing_workspace(
        total=total, purchased="100", consumed="0.000001", servings=servings
    )
    result = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    assert result["ok"], result
    calculation = result["data"]["calculation"]
    cost = Decimal(calculation["cmv_per_serving"])
    with localcontext() as context:
        context.prec = 80
        minimum = Decimal(calculation["minimum"]["price"])
        assert minimum * Decimal("0.90") >= cost
        assert (minimum - Decimal("0.01")) * Decimal("0.90") < cost
        prices = [Decimal(s["price"]) for s in calculation["scenarios"]]
        assert prices == sorted(prices)
        for scenario in calculation["scenarios"]:
            assert (Decimal("0.90") - Decimal(scenario["target_margin"])) * Decimal(
                scenario["price"]
            ) >= cost
    higher_total = format(Decimal(min(cents * 2, 99999999999999)).scaleb(-2), ".2f")
    _, _, higher_recipe, higher_acceptance, higher_command, _ = pricing_workspace(
        total=higher_total, purchased="100", consumed="0.000001", servings=servings
    )
    higher = higher_command(
        "calculate_pricing_scenarios",
        recipe_id=higher_recipe["id"],
        acceptance_id=higher_acceptance["id"],
    )
    assert higher["ok"], higher
    higher_calculation = higher["data"]["calculation"]
    assert Decimal(higher_calculation["minimum"]["price"]) >= minimum
    assert all(
        Decimal(higher_scenario["price"]) >= price
        for higher_scenario, price in zip(higher_calculation["scenarios"], prices, strict=True)
    )


def test_unrepresentable_selling_price_returns_calculation_error_without_mutation(
    pricing_workspace,
):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace(
        total="999999999999.99", servings=1
    )
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "CALCULATION_ERROR"
    assert service.get_business_state({"workspace_id": workspace}) == before


@pytest.mark.parametrize(
    "damage", ["calculation_acceptance", "decision_price", "allocation_subtotal"]
)
def test_inconsistent_persisted_pricing_is_refused_without_repair(pricing_workspace, damage):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence=evidence("Escolho M20."),
    )
    # Fronteira de armazenamento: preparar agregado deliberadamente corrompido.
    with sqlite3.connect(database) as db:
        state = json.loads(
            db.execute("SELECT state_json FROM workspaces WHERE id=?", (workspace,)).fetchone()[0]
        )
        if damage == "calculation_acceptance":
            state["pricing_calculations"][0]["acceptance_id"] = str(uuid4())
        elif damage == "decision_price":
            state["menu_decisions"][0]["price"] = "11.11"
        else:
            state["pricing_calculations"][0]["allocations"][0]["subtotal"] = "0"
        db.execute("UPDATE workspaces SET state_json=? WHERE id=?", (json.dumps(state), workspace))
    before = database.read_bytes()
    result = service.get_business_state({"workspace_id": workspace})
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert database.read_bytes() == before


def test_calculation_is_revalidated_against_authoritative_acquisition_before_choice(
    pricing_workspace,
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    # Snapshot internamente coerente, mas com origem de aquisição inventada.
    # Trocar a parcela de origem mantendo as contas revela se o serviço confia no cache.
    revision = service.get_business_state({"workspace_id": workspace})["revision"]
    with sqlite3.connect(database) as db:
        state = json.loads(
            db.execute("SELECT state_json FROM workspaces WHERE id=?", (workspace,)).fetchone()[0]
        )
        state["pricing_calculations"][0]["allocations"][0]["source_id"] = str(uuid4())
        db.execute("UPDATE workspaces SET state_json=? WHERE id=?", (json.dumps(state), workspace))
    result = service.save_menu_decision(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=revision,
            recipe_id=recipe["id"],
            acceptance_id=acceptance["id"],
            calculation_id=calculation["id"],
            scenario_id="M20",
            evidence=evidence("Escolho M20."),
        )
    )
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"


@pytest.mark.parametrize("damage", ["consumption", "yield", "sale_unit"])
def test_coherent_pricing_must_match_accepted_recipe_on_read_and_reuse(pricing_workspace, damage):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    revision, state, snapshot = SQLiteWorkspaceRepository(database).load(
        workspace, with_snapshot=True
    )
    # Gerar contas coerentes para premissas diferentes das que foram aceitas.
    altered_recipe = state.candidates[0].model_copy(deep=True)
    if damage == "consumption":
        altered_recipe.ingredients[0].quantity.value = "50"
    elif damage == "yield":
        altered_recipe.yield_per_batch.servings_per_batch = 4
    else:
        altered_recipe.yield_per_batch.sale_unit_label = "lote"
    forged = calculate_pricing(
        altered_recipe,
        state.plan.items[0],
        state.acceptances[0],
        snapshot,
        state.pricing_policy_version,
        service.clock(),
    ).model_dump(mode="json")
    forged["id"] = calculation["id"]
    payload = state.model_dump(mode="json")
    payload["pricing_calculations"] = [forged]
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE workspaces SET state_json=? WHERE id=?", (json.dumps(payload), workspace)
        )
    before = database.read_bytes()

    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    result = reopened.get_business_state({"workspace_id": workspace})
    assert result["ok"] is False
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    result = reopened.calculate_pricing_scenarios(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=revision,
            recipe_id=recipe["id"],
            acceptance_id=acceptance["id"],
        )
    )
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert database.read_bytes() == before


@pytest.mark.parametrize("field", ["title", "method"])
def test_recipe_edit_preserves_pricing_only_when_business_inputs_are_unchanged(
    pricing_workspace, recipe_candidate, field
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    candidate = recipe_candidate | {field: "Texto corrigido da fixture."}
    for review in candidate["category_reviews"]:
        review["method_version"] = 2
    result = command(
        "register_recipe_candidate",
        recipe_id=recipe["id"],
        expected_recipe_version=1,
        candidate=candidate,
    )
    assert result["ok"], result
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    state = reopened.get_business_state({"workspace_id": workspace})
    assert state["ok"], state
    assert state["data"]["pricing_calculations"] == [
        calculation | {"validity": "VALID" if field == "title" else "INVALIDATED"}
    ]


@pytest.mark.parametrize("tool", ["calculate_pricing_scenarios", "save_menu_decision"])
@pytest.mark.parametrize("table", ["decisions", "operations"])
def test_pricing_write_rolls_back_when_audit_or_operation_cannot_be_saved(
    pricing_workspace, tool, table
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    payload = dict(recipe_id=recipe["id"], acceptance_id=acceptance["id"])
    if tool == "save_menu_decision":
        calculation = command("calculate_pricing_scenarios", **payload)["data"]["calculation"]
        payload.update(
            calculation_id=calculation["id"], scenario_id="M20", evidence=evidence("Escolho M20.")
        )
    before = service.get_business_state({"workspace_id": workspace})
    with sqlite3.connect(database) as db:
        db.execute(
            f"CREATE TRIGGER injected_fault BEFORE INSERT ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    result = command(tool, **payload)
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_half_cent_fee_display_adds_to_price_without_changing_technical_result(pricing_workspace):
    _, _, recipe, acceptance, command, _ = pricing_workspace(total="0.01", servings=1)
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    result = command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        custom_price="0.05",
        evidence=evidence("Escolho o preço de R$ 0,05."),
    )
    assert result["ok"], result
    option = result["data"]["chosen_option"]
    assert Decimal(option["result_theoretical"]) == Decimal("0.035")
    assert option["display"] == dict(cmv="0.01", fee="0.01", receipt="0.04", result="0.03")
