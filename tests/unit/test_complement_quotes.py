"""S05: complementos e simulações pelo serviço público com banco temporário."""

import json
import sqlite3
from decimal import Decimal, Inexact, localcontext
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


def evidence(statement="Confirmo esta produção."):
    return dict(
        turn_ref="synthetic-s05-user", statement=statement, captured_at="2026-11-12T12:00:00Z"
    )


def new_complement(command, candidate, name="Mel", dimension="g", amount="200"):
    candidate["ingredients"] = candidate["ingredients"][:1]
    candidate["ingredients"][0].update(
        description=name, ingredient_id=None, quantity=dict(value=amount, unit=dimension)
    )
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    return command(
        "resolve_recipe_ingredient",
        recipe_id=recipe["id"],
        recipe_version=recipe["version"],
        line_id=recipe["ingredients"][0]["line_id"],
        new_ingredient=dict(name=name, dimension=dimension),
        evidence=evidence(f"O ingrediente desta receita é {name}."),
    )


def set_plan(command, recipe, **extra):
    return command(
        "set_production_plan",
        items=[
            dict(recipe_id=recipe["id"], recipe_version=recipe["version"], position=0, batches=1)
        ],
        evidence=evidence(),
        **extra,
    )


def quote_input(ingredient_id, **changes):
    return (
        dict(
            ingredient_id=ingredient_id,
            description="Mel: pacote comercial de 1000 g — fixture offline",
            package_quantity=dict(value="1000", unit="g"),
            package_price="20.00",
            purchase_extra_total="0.00",
            extra_conditions="Retirada sem cobrança adicional neste anúncio sintético.",
            availability="AVAILABLE",
            availability_context="Anúncio sintético indica três pacotes disponíveis para retirada.",
            max_packages=3,
            supplier="Fornecedor sintético",
            source=dict(
                kind="WEB",
                url="https://example.org/oferta-fixture",
                title="Oferta sintética offline",
                excerpt="Pacote 1000 g por R$ 20,00; três disponíveis; retirada sem custo.",
                retrieved_at="2026-11-12T12:00:00Z",
            ),
        )
        | changes
    )


def test_new_complement_has_server_identity_and_explicit_snapshot_absence(clarification):
    service, workspace, command, candidate, _, original, path, database = clarification
    source_bytes = path.read_bytes()
    result = new_complement(command, candidate)
    assert result["ok"], result
    identity = result["data"]["ingredient"]
    assert str(UUID(identity["id"])) == result["data"]["ingredient_id"]
    assert identity["origin"] == "COMPLEMENT"
    assert identity["name_normalized"] == "mel"
    assert identity["stock_quantity_base"] == "0"
    assert identity["availability_basis"] == "ABSENT_FROM_SNAPSHOT"
    assert identity["acquisition_total"] is None
    assert set_plan(command, result["data"]["candidate"])["ok"]
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["demand"][0]["shortage"] == "200"
    assert evaluation["demand"][0]["availability_basis"] == "ABSENT_FROM_SNAPSHOT"
    assert evaluation["purchase_status"] == "PENDING"
    restarted = BusinessStateReader(SQLiteWorkspaceRepository(database))
    state = restarted.get_business_state({"workspace_id": workspace})
    assert state["ok"], state
    assert state["data"]["complement_ingredients"] == [identity]
    assert restarted.get_inventory_snapshot({"workspace_id": workspace})["data"] == original
    assert path.read_bytes() == source_bytes


@pytest.mark.parametrize("name", ["  ARROZ  ", "Ａｒｒｏｚ", "  MEL "])
def test_new_complement_cannot_collide_with_existing_identity(clarification, name):
    service, workspace, command, candidate, *_ = clarification
    assert new_complement(command, candidate)["ok"]
    before = service.get_business_state({"workspace_id": workspace})
    recipe = before["data"]["candidates"][0]
    result = command(
        "resolve_recipe_ingredient",
        recipe_id=recipe["id"],
        recipe_version=recipe["version"],
        line_id=recipe["ingredients"][0]["line_id"],
        new_ingredient=dict(name=name, dimension="g"),
        evidence=evidence(),
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_researched_offer_is_persisted_as_estimate_without_human_confirmation(clarification):
    service, workspace, command, candidate, *_, database = clarification
    ingredient = new_complement(command, candidate)["data"]["ingredient_id"]
    payload = quote_input(ingredient)
    result = command("register_complement_quote", quote=payload)
    assert result["ok"], result
    saved = result["data"]["quote"]
    assert saved["status"] == "ESTIMATED"
    assert saved["confirmation"] is None
    assert saved["version"] == 1
    assert saved["source"] == payload["source"]
    assert saved["package_quantity"] == dict(value="1000", unit="g")
    assert saved["gaps"] == []
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    state = reopened.get_business_state({"workspace_id": workspace})
    assert state["ok"], state
    assert state["data"]["complement_quotes"] == [saved]


def test_purchase_simulation_distinguishes_whole_package_from_consumed_cost(clarification):
    service, workspace, command, candidate, *_ = clarification
    resolved = new_complement(command, candidate)["data"]
    ingredient = resolved["ingredient_id"]
    quote = command("register_complement_quote", quote=quote_input(ingredient))["data"]["quote"]
    selected = set_plan(
        command,
        resolved["candidate"],
        quote_selections=[
            dict(ingredient_id=ingredient, quote_id=quote["id"], quote_version=quote["version"])
        ],
    )
    assert selected["ok"], selected
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["is_simulation"] is True
    assert evaluation["purchase_status"] == "PENDING"
    assert evaluation["disbursement"] == "20.00"
    assert evaluation["remaining_budget"] == "60.00"
    purchase = evaluation["demand"][0]["purchase"]
    assert purchase["packages"] == 1
    assert purchase["purchased_quantity"] == "1000"
    assert purchase["planned_surplus"] == "800"
    assert purchase["consumed_ingredient_cost"] == "4.00"
    assert purchase["confirmation"] is None
    assert any("PRICE_UNCONFIRMED" in gap for gap in evaluation["gaps"])
    item = selected["data"]["plan"]["items"][0]
    refused = command(
        "accept_recipe",
        recipe_id=resolved["candidate"]["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )
    assert refused["ok"] is False
    assert service.get_business_state({"workspace_id": workspace})["data"]["acceptances"] == []


@pytest.mark.parametrize(
    "missing", ["package_quantity", "package_price", "purchase_extra_total", "availability"]
)
def test_unknown_offer_data_stays_a_gap_and_never_becomes_zero(clarification, missing):
    service, workspace, command, candidate, *_ = clarification
    resolved = new_complement(command, candidate)["data"]
    payload = quote_input(resolved["ingredient_id"])
    if missing == "availability":
        payload.update(
            availability="UNKNOWN", availability_context="Disponibilidade não informada."
        )
    else:
        payload[missing] = None
        payload[f"{missing}_gap"] = "Dado não encontrado na fonte sintética."
    result = command("register_complement_quote", quote=payload)
    assert result["ok"], result
    saved = result["data"]["quote"]
    assert missing in saved["gaps"]
    assert set_plan(
        command,
        resolved["candidate"],
        quote_selections=[
            dict(ingredient_id=resolved["ingredient_id"], quote_id=saved["id"], quote_version=1)
        ],
    )["ok"]
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["purchase_status"] == "PENDING"
    assert evaluation["is_simulation"] is True
    if missing != "availability":
        assert evaluation["disbursement"] is None
        assert evaluation["remaining_budget"] is None
        if missing == "purchase_extra_total":
            assert evaluation["demand"][0]["purchase"]["package_spend"] == "20.00"
    else:
        assert evaluation["disbursement"] == "20.00"
    assert any(missing in gap for gap in evaluation["gaps"])


@pytest.mark.parametrize("availability,max_packages", [("AVAILABLE", 0), ("UNAVAILABLE", 3)])
def test_offer_cannot_satisfy_demand_beyond_its_availability(
    clarification, availability, max_packages
):
    service, workspace, command, candidate, *_ = clarification
    resolved = new_complement(command, candidate)["data"]
    quote = command(
        "register_complement_quote",
        quote=quote_input(
            resolved["ingredient_id"], availability=availability, max_packages=max_packages
        ),
    )["data"]["quote"]
    assert set_plan(
        command,
        resolved["candidate"],
        quote_selections=[
            dict(ingredient_id=resolved["ingredient_id"], quote_id=quote["id"], quote_version=1)
        ],
    )["ok"]
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["purchase_status"] == "PENDING"
    assert evaluation["demand"][0]["purchase"]["packages"] == 1
    assert any("OFFER_INSUFFICIENT" in gap for gap in evaluation["gaps"])


def test_zero_shortage_never_buys_a_preventive_package_or_charges_freight(clarification):
    service, workspace, command, candidate, *_ = clarification
    candidate["ingredients"] = candidate["ingredients"][:1]
    ingredient = candidate["ingredients"][0]["ingredient_id"]
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    quote = command(
        "register_complement_quote",
        quote=quote_input(
            ingredient,
            package_price=None,
            package_price_gap="Preço não publicado.",
            purchase_extra_total="15.00",
            extra_conditions="Entrega custa R$ 15,00.",
        ),
    )["data"]["quote"]
    assert set_plan(
        command,
        recipe,
        quote_selections=[dict(ingredient_id=ingredient, quote_id=quote["id"], quote_version=1)],
    )["ok"]
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["purchase_status"] == "CONFIRMED"
    assert evaluation["disbursement"] == "0.00"
    assert evaluation["remaining_budget"] == "80.00"
    assert evaluation["demand"][0]["purchase"]["packages"] == 0
    assert evaluation["gaps"] == []


def test_package_dimension_must_match_ingredient_without_density_inference(clarification):
    service, workspace, command, candidate, *_ = clarification
    resolved = new_complement(command, candidate)["data"]
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "register_complement_quote",
        quote=quote_input(
            resolved["ingredient_id"], package_quantity=dict(value="1000", unit="ml")
        ),
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "UNIT_CONVERSION_REQUIRED"
    assert service.get_business_state({"workspace_id": workspace}) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("package_price", "0.00"),
        ("package_price", 20.0),
        ("package_price", "NaN"),
        ("package_price", "20.001"),
        ("purchase_extra_total", "-1.00"),
        ("max_packages", True),
        ("extra_conditions", "  "),
        ("description", "  "),
        ("status", "CONFIRMED"),
        ("packages", 1),
        ("confirmation", evidence()),
    ],
)
def test_offer_boundary_rejects_invalid_and_model_derived_values(clarification, field, value):
    service, workspace, command, candidate, *_ = clarification
    ingredient = new_complement(command, candidate)["data"]["ingredient_id"]
    before = service.get_business_state({"workspace_id": workspace})
    result = command("register_complement_quote", quote=quote_input(ingredient, **{field: value}))
    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_offer_without_a_source_is_refused_without_creating_a_quote(clarification):
    service, workspace, command, candidate, *_ = clarification
    ingredient = new_complement(command, candidate)["data"]["ingredient_id"]
    before = service.get_business_state({"workspace_id": workspace})
    payload = quote_input(ingredient)
    payload.pop("source")
    result = command("register_complement_quote", quote=payload)
    assert result["error"]["code"] == "SOURCE_REQUIRED"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_quote_revision_preserves_history_and_requires_current_selection(clarification):
    service, workspace, command, candidate, *_, database = clarification
    resolved = new_complement(command, candidate)["data"]
    ingredient = resolved["ingredient_id"]
    first = command("register_complement_quote", quote=quote_input(ingredient))["data"]["quote"]
    selection = dict(ingredient_id=ingredient, quote_id=first["id"], quote_version=1)
    assert set_plan(command, resolved["candidate"], quote_selections=[selection])["ok"]
    before = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    changed = command(
        "register_complement_quote",
        quote_id=first["id"],
        expected_quote_version=1,
        quote=quote_input(ingredient, package_price="21.00"),
    )
    assert changed["ok"], changed
    second = changed["data"]["quote"]
    assert (second["id"], second["version"], second["status"]) == (first["id"], 2, "ESTIMATED")
    pending = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert pending["fingerprint"] != before["fingerprint"]
    assert any("STALE_QUOTE" in gap for gap in pending["gaps"])
    assert (
        set_plan(command, resolved["candidate"], quote_selections=[selection])["error"]["code"]
        == "STALE_REVISION"
    )
    assert set_plan(
        command, resolved["candidate"], quote_selections=[selection | {"quote_version": 2}]
    )["ok"]
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    state = reopened.get_business_state({"workspace_id": workspace})
    assert state["data"]["complement_quotes"] == [first, second]
    assert state["data"]["evaluation"]["disbursement"] == "21.00"


def test_simulation_money_ignores_the_callers_decimal_precision(clarification):
    service, workspace, command, candidate, *_, database = clarification
    resolved = new_complement(command, candidate)["data"]
    quote = command(
        "register_complement_quote",
        quote=quote_input(
            resolved["ingredient_id"],
            package_price="20.01",
            package_quantity=dict(value="1234.567891", unit="g"),
        ),
    )["data"]["quote"]
    assert set_plan(
        command,
        resolved["candidate"],
        quote_selections=[
            dict(ingredient_id=resolved["ingredient_id"], quote_id=quote["id"], quote_version=1)
        ],
    )["ok"]
    expected = service.get_business_state({"workspace_id": workspace})
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    with localcontext() as caller:
        caller.prec = 2
        caller.traps[Inexact] = True
        actual = reopened.get_business_state({"workspace_id": workspace})
    assert actual == expected
    assert actual["data"]["evaluation"]["remaining_budget"] == "59.99"


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(shortage=st.integers(1, 20000), content=st.integers(1, 5000))
def test_prop002_packages_are_sufficient_and_minimal_at_the_public_seam(
    clarification, shortage, content
):
    service, workspace, command, candidate, *_ = clarification
    candidate["ingredients"] = candidate["ingredients"][:1]
    ingredient = candidate["ingredients"][0]["ingredient_id"]
    candidate["ingredients"][0]["quantity"] = dict(value=str(5000 + shortage), unit="g")
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    quote = command(
        "register_complement_quote",
        quote=quote_input(
            ingredient, package_quantity=dict(value=str(content), unit="g"), max_packages=None
        ),
    )["data"]["quote"]
    assert set_plan(
        command,
        recipe,
        quote_selections=[dict(ingredient_id=ingredient, quote_id=quote["id"], quote_version=1)],
    )["ok"]
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    purchase = evaluation["demand"][0]["purchase"]
    packages = purchase["packages"]
    assert (packages - 1) * content < shortage <= packages * content
    assert Decimal("0") <= Decimal(purchase["planned_surplus"]) < content
    assert evaluation["purchase_status"] == "PENDING"


def test_explicit_freight_competes_for_budget_but_is_separate_from_ingredients(clarification):
    service, workspace, command, candidate, *_ = clarification
    resolved = new_complement(command, candidate, amount="1200")["data"]
    quote = command(
        "register_complement_quote",
        quote=quote_input(
            resolved["ingredient_id"],
            package_price="40.00",
            purchase_extra_total="5.50",
            extra_conditions="Frete total desta oferta: R$ 5,50.",
        ),
    )["data"]["quote"]
    assert set_plan(
        command,
        resolved["candidate"],
        quote_selections=[
            dict(ingredient_id=resolved["ingredient_id"], quote_id=quote["id"], quote_version=1)
        ],
    )["ok"]
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["disbursement"] == "85.50"
    assert evaluation["remaining_budget"] == "-5.50"
    assert evaluation["demand"][0]["purchase"]["package_spend"] == "80.00"
    assert evaluation["demand"][0]["purchase"]["purchase_extra_total"] == "5.50"
    assert Decimal(evaluation["demand"][0]["purchase"]["consumed_ingredient_cost"]) == Decimal(
        "48.00"
    )
    assert any("BUDGET_EXCEEDED" in gap for gap in evaluation["gaps"])


@pytest.mark.parametrize(
    "damage",
    [
        "identity_name",
        "duplicate_identity",
        "quote_ingredient",
        "quote_version",
        "selection_ingredient",
    ],
)
def test_inconsistent_persisted_complement_is_refused_without_repair(clarification, damage):
    service, workspace, command, candidate, _, original, _, database = clarification
    resolved = new_complement(command, candidate)["data"]
    quote = command("register_complement_quote", quote=quote_input(resolved["ingredient_id"]))[
        "data"
    ]["quote"]
    assert set_plan(
        command,
        resolved["candidate"],
        quote_selections=[
            dict(ingredient_id=resolved["ingredient_id"], quote_id=quote["id"], quote_version=1)
        ],
    )["ok"]
    with sqlite3.connect(database) as db:
        state = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        if damage == "identity_name":
            state["complement_ingredients"][0]["name_normalized"] = "arroz"
        elif damage == "duplicate_identity":
            state["complement_ingredients"].append(state["complement_ingredients"][0])
        elif damage == "quote_ingredient":
            state["complement_quotes"][0]["ingredient_id"] = str(uuid4())
        elif damage == "quote_version":
            state["complement_quotes"][0]["version"] = 2
        else:
            state["plan"]["quote_selections"][0]["ingredient_id"] = original["items"][0]["id"]
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(state),))
    before = database.read_bytes()
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    result = reopened.get_business_state({"workspace_id": workspace})
    assert result["ok"] is False
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert database.read_bytes() == before


def test_commercial_deadline_is_preserved_as_offer_data_not_confirmation(clarification):
    service, workspace, command, candidate, *_ = clarification
    ingredient = new_complement(command, candidate)["data"]["ingredient_id"]
    result = command(
        "register_complement_quote",
        quote=quote_input(ingredient, valid_until="2026-11-12T10:00:00-03:00"),
    )
    assert result["ok"], result
    assert result["data"]["quote"]["valid_until"] == "2026-11-12T13:00:00Z"
    assert result["data"]["quote"]["confirmation"] is None


def test_availability_explanation_can_be_reworded_without_changing_business_state(clarification):
    service, workspace, command, candidate, *_, database = clarification
    assert new_complement(command, candidate)["ok"]
    with sqlite3.connect(database) as db:
        state = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        state["complement_ingredients"][0]["availability_note"] = (
            "Ausente da fotografia recebida; a pessoa pode esclarecer "
            "estoque adicional antes de comprar."
        )
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(state),))
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    result = reopened.get_business_state({"workspace_id": workspace})
    assert result["ok"], result
    assert (
        result["data"]["complement_ingredients"][0]["availability_basis"] == "ABSENT_FROM_SNAPSHOT"
    )


def test_unselected_complement_preserves_active_acceptance_and_pricing(
    pricing_workspace, recipe_candidate
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    assert command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["ok"]
    before = service.get_business_state({"workspace_id": workspace})["data"]
    resolved = new_complement(command, recipe_candidate)["data"]
    quote = command("register_complement_quote", quote=quote_input(resolved["ingredient_id"]))[
        "data"
    ]["quote"]
    assert command(
        "register_complement_quote",
        quote_id=quote["id"],
        expected_quote_version=1,
        quote=quote_input(resolved["ingredient_id"], package_price="25.00"),
    )["ok"]
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    after = reopened.get_business_state({"workspace_id": workspace})["data"]
    assert after["evaluation"]["fingerprint"] == before["evaluation"]["fingerprint"]
    assert after["acceptances"][0]["validity"] == "VALID"
    assert after["pricing_calculations"][0]["validity"] == "VALID"


def test_quote_in_old_dimension_stays_pending_after_historical_conversion(clarification):
    service, workspace, command, candidate, chocolate, *_, database = clarification
    candidate["ingredients"] = candidate["ingredients"][1:]
    candidate["ingredients"][0]["quantity"] = dict(value="2000", unit="g")
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    quote = command(
        "register_complement_quote",
        quote=quote_input(chocolate["id"], package_quantity=dict(value="1", unit="un")),
    )["data"]["quote"]
    assert set_plan(
        command,
        recipe,
        quote_selections=[
            dict(ingredient_id=chocolate["id"], quote_id=quote["id"], quote_version=1)
        ],
    )["ok"]
    converted = command(
        "record_ingredient_conversion",
        ingredient_id=chocolate["id"],
        from_unit="un",
        to_unit="g",
        factor="1000",
        context="Embalagem histórica sintética de 1000 g.",
        scope="HISTORICAL_PACKAGE",
        evidence=evidence("Confirmo 1000 g na embalagem comprada."),
    )
    assert converted["ok"], converted
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    result = reopened.evaluate_purchase_plan({"workspace_id": workspace})
    assert result["ok"], result
    evaluation = result["data"]
    assert evaluation["purchase_status"] == "PENDING"
    assert evaluation["disbursement"] is None
    assert evaluation["remaining_budget"] is None
    assert any("UNIT_CONVERSION_REQUIRED" in gap for gap in evaluation["gaps"])
    assert evaluation["demand"][0]["shortage"] == "1000"
    assert evaluation["demand"][0]["purchase"]["packages"] is None
