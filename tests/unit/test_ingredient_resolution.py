"""S04: esclarecimentos pela interface pública, com fotografia sintética."""

import json
import sqlite3
from decimal import Decimal, Inexact, localcontext
from uuid import uuid4

import pytest

from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


def evidence(statement):
    return dict(
        turn_ref="synthetic-s04-user", statement=statement, captured_at="2026-11-12T12:00:00Z"
    )


def plan(command, recipe):
    return command(
        "set_production_plan",
        items=[
            dict(recipe_id=recipe["id"], recipe_version=recipe["version"], position=0, batches=1)
        ],
        evidence=evidence("Confirmo um lote desta receita."),
    )


def test_incompatible_measure_stays_pending_without_hiding_valid_ingredients(clarification):
    service, workspace, command, candidate, chocolate, *_ = clarification
    result = command("register_recipe_candidate", candidate=candidate)
    assert result["ok"], result
    assert plan(command, result["data"]["candidate"])["ok"]
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert any("UNIT_CONVERSION_REQUIRED" in gap for gap in evaluation["gaps"])
    assert evaluation["purchase_status"] == "PENDING"
    assert [
        i["stock_available"] for i in evaluation["demand"] if i["ingredient_id"] != chocolate["id"]
    ] == ["5000"]


def historical(chocolate, factor="1000", **changes):
    return (
        dict(
            ingredient_id=chocolate["id"],
            from_unit="un",
            to_unit="g",
            factor=factor,
            context="Embalagem histórica da cobertura desta fotografia",
            scope="HISTORICAL_PACKAGE",
            evidence=evidence(f"Confirmo que a embalagem comprada contém {factor} g."),
        )
        | changes
    )


def test_historical_package_overlay_recalculates_without_editing_the_snapshot(clarification):
    service, workspace, command, candidate, chocolate, original, path, database = clarification
    source_bytes = path.read_bytes()
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    plan(command, recipe)
    before = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    result = command("record_ingredient_conversion", **historical(chocolate))
    assert result["ok"], result
    assert result["data"]["effective_ingredient"]["stock_quantity_base"] == "1000"
    assert result["data"]["remaining_gaps"] == []
    after = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    effective = next(i for i in after["demand"] if i["ingredient_id"] == chocolate["id"])
    assert effective["stock_available"] == "1000"
    assert Decimal(effective["source"]["unit_cost"]) == Decimal("0.07990")
    assert effective["source"]["purchase_quantity_base"] == "1000"
    assert after["fingerprint"] != before["fingerprint"]
    assert after["purchase_status"] == "CONFIRMED"
    assert path.read_bytes() == source_bytes
    restarted = BusinessStateReader(SQLiteWorkspaceRepository(database))
    assert restarted.get_inventory_snapshot({"workspace_id": workspace})["data"] == original
    assert restarted.evaluate_purchase_plan({"workspace_id": workspace})["data"] == after


def test_replacing_a_conversion_invalidates_acceptance_and_never_resurrects_it(clarification):
    service, workspace, command, candidate, chocolate, *_ = clarification
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    item = plan(command, recipe)["data"]["plan"]["items"][0]
    first = command("record_ingredient_conversion", **historical(chocolate))["data"]["conversion"]
    command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
        evidence=evidence("Tenho interesse."),
    )
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito esta receita conforme o resumo."),
    )
    assert accepted["ok"], accepted
    conflict = command("record_ingredient_conversion", **historical(chocolate, "500"))
    assert conflict["error"]["code"] == "STALE_REVISION"
    changed = command(
        "record_ingredient_conversion",
        **historical(chocolate, "500", replaces_conversion_id=first["id"]),
    )
    assert changed["data"]["invalidated_decisions"] == [accepted["data"]["acceptance"]["id"]]
    restored = command(
        "record_ingredient_conversion",
        **historical(chocolate, replaces_conversion_id=changed["data"]["conversion"]["id"]),
    )
    assert restored["ok"]
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["acceptances"][0]["validity"] == "INVALIDATED"
    assert state["evaluation"]["fingerprint"] != evaluation["fingerprint"]
    assert [c["factor"] for c in state["ingredient_conversions"]] == ["1000", "500", "1000"]


def test_identity_resolution_records_confirmed_alias_and_preserves_source(clarification):
    service, workspace, command, candidate, chocolate, *_ = clarification
    candidate["ingredients"][1]["ingredient_id"] = None
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    original_line = recipe["ingredients"][1]
    resolved = command(
        "resolve_recipe_ingredient",
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=original_line["line_id"],
        existing_ingredient_id=chocolate["id"],
        evidence=evidence("A cobertura desta receita é a de chocolate da despensa."),
    )
    assert resolved["ok"], resolved
    updated = resolved["data"]["candidate"]
    assert updated["version"] == 2
    assert updated["ingredients"][1] == original_line | {"ingredient_id": chocolate["id"]}
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["ingredient_resolutions"][0]["alias"] == "Cobertura"
    assert state["ingredient_resolutions"][0]["evidence"]["turn_ref"] == "synthetic-s04-user"
    assert state["candidates"][0]["ingredients"][1]["description"] == "Cobertura"


def test_recipe_measure_is_scoped_to_one_line_and_its_preparation_basis(clarification):
    service, workspace, command, candidate, _, *_ = clarification
    candidate["ingredients"] = candidate["ingredients"][:1]
    line = candidate["ingredients"][0]
    line.update(
        quantity=None, quantity_gap="Falta converter a xícara cozida.", preparation_basis="COOKED"
    )
    line["original_measure"].update(value="1", unit_label="xícara", raw_text="1 xícara cozida")
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    item = plan(command, recipe)["data"]["plan"]["items"][0]
    result = command(
        "record_ingredient_conversion",
        ingredient_id=line["ingredient_id"],
        from_unit="xícara",
        to_unit="g",
        factor="100",
        context="Xícara cozida desta receita em equivalente cru",
        scope="RECIPE_MEASURE",
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][0]["line_id"],
        from_preparation_basis="COOKED",
        evidence=evidence("Esta xícara cozida equivale a 100 g de arroz cru neste preparo."),
    )
    assert result["ok"], result
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["demand"][0]["required"] == "100"
    assert evaluation["purchase_status"] == "CONFIRMED"
    feasible = service.evaluate_recipe_feasibility(
        dict(workspace_id=workspace, recipe_id=recipe["id"], plan_item_id=item["plan_item_id"])
    )
    assert feasible["data"]["status"] == "ELIGIBLE"
    original = service.get_business_state({"workspace_id": workspace})["data"]["candidates"][0][
        "ingredients"
    ][0]
    assert original["quantity"] is None
    assert original["preparation_basis"] == "COOKED"


@pytest.mark.parametrize(
    "factor", [0, True, "0", "-1", "NaN", "Infinity", "1e3", " 1000", "1.1234567"]
)
def test_invalid_conversion_factors_never_write(clarification, factor):
    service, workspace, command, _, chocolate, *_ = clarification
    before = service.get_business_state({"workspace_id": workspace})
    refused = command("record_ingredient_conversion", **historical(chocolate, factor))
    assert refused["error"]["code"] == "VALIDATION_ERROR"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_conversion_factor_is_not_rounded_by_the_callers_decimal_precision(clarification):
    service, workspace, command, _, chocolate, *_ = clarification
    with localcontext() as caller:
        caller.prec = 2
        result = command("record_ingredient_conversion", **historical(chocolate, "1234.567891"))
    assert result["ok"], result
    assert result["data"]["conversion"]["factor"] == "1234.567891"
    assert result["data"]["effective_ingredient"]["stock_quantity_base"] == "1234.567891"
    assert service.get_business_state({"workspace_id": workspace})["ok"]


def test_periodic_overlay_cost_does_not_inherit_the_callers_inexact_trap(clarification):
    _, _, command, _, chocolate, *_ = clarification
    with localcontext() as caller:
        caller.traps[Inexact] = True
        result = command("record_ingredient_conversion", **historical(chocolate, "3"))
    assert result["ok"], result
    assert result["data"]["effective_ingredient"]["unit_cost"] == (
        "26.63333333333333333333333333333333"
    )


def test_overlay_reopening_preserves_factor_and_effective_state_under_low_precision(clarification):
    service, workspace, command, _, chocolate, *_, database = clarification
    assert command("record_ingredient_conversion", **historical(chocolate, "1234.567891"))["ok"]
    before = service.get_business_state({"workspace_id": workspace})
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    with localcontext() as caller:
        caller.prec = 2
        after = reopened.get_business_state({"workspace_id": workspace})
    assert after == before


def test_standard_metric_relationship_cannot_be_redefined_by_an_overlay(clarification):
    service, workspace, command, _, _, original, *_ = clarification
    rice = next(i for i in original["items"] if i["dimension"] == "g")
    before = service.get_business_state({"workspace_id": workspace})
    refused = command("record_ingredient_conversion", **historical(rice, "1000", from_unit="g"))
    assert refused["error"]["code"] == "UNIT_CONVERSION_REQUIRED"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_recipe_measure_does_not_supply_historical_package_cost(clarification):
    service, workspace, command, candidate, chocolate, *_ = clarification
    line = candidate["ingredients"][1]
    line.update(quantity=None, quantity_gap="Falta medida desta colher.")
    line["original_measure"].update(value="1", unit_label="colher")
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    plan(command, recipe)
    result = command(
        "record_ingredient_conversion",
        ingredient_id=chocolate["id"],
        from_unit="colher",
        to_unit="g",
        factor="20",
        context="Colher desta receita",
        scope="RECIPE_MEASURE",
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][1]["line_id"],
        evidence=evidence("Esta colher tem 20 g."),
    )
    assert result["ok"], result
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["purchase_status"] == "PENDING"
    assert any("UNIT_CONVERSION_REQUIRED" in gap for gap in evaluation["gaps"])
    assert all(i["ingredient_id"] != chocolate["id"] for i in evaluation["demand"])


def test_overlay_cost_is_used_by_existing_calculation_and_survives_replacement(clarification):
    service, workspace, command, candidate, chocolate, *_ = clarification
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    item = plan(command, recipe)["data"]["plan"]["items"][0]
    conversion = command("record_ingredient_conversion", **historical(chocolate))["data"][
        "conversion"
    ]
    command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
        evidence=evidence("Tenho interesse."),
    )
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )
    calculated = command(
        "calculate_pricing_scenarios",
        recipe_id=recipe["id"],
        acceptance_id=accepted["data"]["acceptance"]["id"],
    )
    assert calculated["ok"], calculated
    assert Decimal(calculated["data"]["calculation"]["cmv_production"]) == Decimal("8.488")
    assert service.get_business_state({"workspace_id": workspace})["ok"]
    command(
        "record_ingredient_conversion",
        **historical(chocolate, "500", replaces_conversion_id=conversion["id"]),
    )
    state = service.get_business_state({"workspace_id": workspace})
    assert state["ok"], state
    assert state["data"]["pricing_calculations"][0]["validity"] == "INVALIDATED"


def test_unrelated_package_clarification_preserves_the_current_acceptance(clarification):
    service, workspace, command, candidate, chocolate, *_ = clarification
    candidate["ingredients"] = candidate["ingredients"][:1]
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    item = plan(command, recipe)["data"]["plan"]["items"][0]
    command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
        evidence=evidence("Tenho interesse."),
    )
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )
    assert accepted["ok"]
    result = command("record_ingredient_conversion", **historical(chocolate))
    assert result["data"]["invalidated_decisions"] == []
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["evaluation"]["fingerprint"] == evaluation["fingerprint"]
    assert state["acceptances"][0]["validity"] == "VALID"


@pytest.mark.parametrize("in_plan", [False, True])
def test_identity_resolution_invalidates_only_when_the_recipe_belongs_to_the_plan(
    clarification, in_plan
):
    service, workspace, command, candidate, chocolate, *_ = clarification
    recipe = command(
        "register_recipe_candidate",
        candidate=candidate | {"ingredients": candidate["ingredients"][:1]},
    )["data"]["candidate"]
    item = plan(command, recipe)["data"]["plan"]["items"][0]
    command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
        evidence=evidence("Tenho interesse neste prato."),
    )
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )
    assert accepted["ok"]
    other = command(
        "register_recipe_candidate",
        candidate=candidate
        | {
            "title": "Outra candidata sintética",
            "ingredients": [candidate["ingredients"][1] | {"ingredient_id": None}],
        },
    )["data"]["candidate"]
    target = recipe if in_plan else other
    result = command(
        "resolve_recipe_ingredient",
        recipe_id=target["id"],
        recipe_version=1,
        line_id=target["ingredients"][0]["line_id"],
        existing_ingredient_id=chocolate["id"],
        evidence=evidence("Esta linha corresponde à cobertura de chocolate da despensa."),
    )
    assert result["ok"], result
    assert result["data"]["invalidated_decisions"] == (
        [accepted["data"]["acceptance"]["id"]] if in_plan else []
    )
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert (state["evaluation"]["fingerprint"] != evaluation["fingerprint"]) is in_plan
    assert state["acceptances"][0]["validity"] == ("INVALIDATED" if in_plan else "VALID")


def test_conversion_keeps_computed_precision_beyond_input_scale(clarification):
    service, workspace, command, candidate, *_ = clarification
    candidate["ingredients"] = candidate["ingredients"][:1]
    line = candidate["ingredients"][0]
    line.update(quantity=None, quantity_gap="Falta converter a medida.")
    line["original_measure"].update(value="1.111111", unit_label="colher")
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    plan(command, recipe)
    result = command(
        "record_ingredient_conversion",
        ingredient_id=line["ingredient_id"],
        from_unit="colher",
        to_unit="g",
        factor="0.1",
        context="Medida desta linha",
        scope="RECIPE_MEASURE",
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][0]["line_id"],
        evidence=evidence("Cada colher equivale a 0.1 g neste preparo."),
    )
    assert result["ok"], result
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})
    assert evaluation["ok"], evaluation
    assert evaluation["data"]["demand"][0]["required"] == "0.1111111"


def test_historical_package_cannot_claim_a_recipe_preparation_basis(clarification):
    service, workspace, command, _, chocolate, *_ = clarification
    before = service.get_business_state({"workspace_id": workspace})
    refused = command(
        "record_ingredient_conversion", **historical(chocolate, from_preparation_basis="COOKED")
    )
    assert refused["error"]["code"] == "VALIDATION_ERROR"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_historical_overlay_cannot_create_fractional_units(clarification):
    service, workspace, command, _, chocolate, *_ = clarification
    before = service.get_business_state({"workspace_id": workspace})
    refused = command("record_ingredient_conversion", **historical(chocolate, "0.5", to_unit="un"))
    assert refused["error"]["code"] == "UNIT_CONVERSION_REQUIRED"
    assert service.get_business_state({"workspace_id": workspace}) == before


@pytest.mark.parametrize(
    "raw,value,unit,quantity,basis",
    [
        ("ovo em g", "100", "g", {"value": "100", "unit": "g"}, "RAW"),
        ("sal a gosto", None, "a gosto", None, "RAW"),
        ("1 xícara", "1", "xícara", None, "RAW"),
        ("100 g cozido", "100", "g", {"value": "100", "unit": "g"}, "COOKED"),
    ],
)
def test_unconfirmed_measures_stay_local_pending(clarification, raw, value, unit, quantity, basis):
    service, workspace, command, candidate, *_ = clarification
    line = candidate["ingredients"][1]
    line.update(quantity=quantity, quantity_gap="Esclareça a medida.", preparation_basis=basis)
    line["original_measure"].update(raw_text=raw, value=value, unit_label=unit)
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    plan(command, recipe)
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["purchase_status"] == "PENDING"
    assert evaluation["disbursement"] is None
    assert len(evaluation["demand"]) == 1
    assert evaluation["demand"][0]["stock_available"] == "5000"


def test_corrupt_overlay_reference_is_refused_without_repair(clarification):
    service, workspace, command, _, chocolate, _, _, database = clarification
    assert command("record_ingredient_conversion", **historical(chocolate))["ok"]
    with sqlite3.connect(database) as db:
        state = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        state["ingredient_conversions"][0]["ingredient_id"] = str(uuid4())
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(state),))
    before = database.read_bytes()
    result = service.get_business_state({"workspace_id": workspace})
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert database.read_bytes() == before


@pytest.mark.parametrize("damage", ["historical_fraction", "metric_factor", "recipe_fraction"])
def test_persisted_overlay_must_obey_the_same_measure_rules_as_a_command(clarification, damage):
    service, workspace, command, candidate, chocolate, original, _, database = clarification
    if damage == "recipe_fraction":
        candidate["ingredients"] = candidate["ingredients"][:1]
        line = candidate["ingredients"][0]
        line.update(quantity=None, quantity_gap="Medida pendente.")
        line["original_measure"].update(value="1", unit_label="medida")
        recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
        request = dict(
            ingredient_id=line["ingredient_id"],
            from_unit="medida",
            to_unit="g",
            factor="10",
            context="Medida desta linha",
            scope="RECIPE_MEASURE",
            recipe_id=recipe["id"],
            recipe_version=1,
            line_id=recipe["ingredients"][0]["line_id"],
            evidence=evidence("Esta medida equivale a 10 g."),
        )
    else:
        request = historical(chocolate)
    assert command("record_ingredient_conversion", **request)["ok"]
    with sqlite3.connect(database) as db:
        state = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        conversion = state["ingredient_conversions"][0]
        if damage == "metric_factor":
            rice = next(item for item in original["items"] if item["dimension"] == "g")
            conversion.update(ingredient_id=rice["id"], from_unit="g", factor="2")
        else:
            conversion.update(to_unit="un", factor="0.5")
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(state),))
    before = database.read_bytes()
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    result = reopened.get_business_state({"workspace_id": workspace})
    assert result["ok"] is False
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    "value,factor,to_unit",
    [
        ("0", "10", "g"),
        ("1", "0.5", "un"),
        ("999999999999.999999", "999999999999.999999", "un"),
    ],
)
def test_conversion_cannot_create_zero_consumption_or_fractional_counts(
    clarification, value, factor, to_unit
):
    service, workspace, command, candidate, *_ = clarification
    candidate["ingredients"] = candidate["ingredients"][:1]
    line = candidate["ingredients"][0]
    line.update(quantity=None, quantity_gap="Medida pendente.")
    line["original_measure"].update(value=value, unit_label="medida")
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "record_ingredient_conversion",
        ingredient_id=line["ingredient_id"],
        from_unit="medida",
        to_unit=to_unit,
        factor=factor,
        context="Medida indivisível desta linha",
        scope="RECIPE_MEASURE",
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][0]["line_id"],
        evidence=evidence("Confirmo esta medida."),
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "UNIT_CONVERSION_REQUIRED"
    assert service.get_business_state({"workspace_id": workspace}) == before
