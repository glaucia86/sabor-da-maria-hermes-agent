"""S06: confirmação humana, orçamento e custo por origem na API pública."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal, Inexact, localcontext
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


def evidence(statement):
    return dict(
        turn_ref="synthetic-s06-user", statement=statement, captured_at="2026-11-12T12:00:00Z"
    )


@pytest.fixture
def purchase(clarification):
    service, workspace, _, candidate, _, original, path, database = clarification
    clock = [datetime(2026, 11, 12, 12, tzinfo=UTC)]
    service = BusinessStateReader(SQLiteWorkspaceRepository(database), clock=lambda: clock[0])

    def command(tool, **payload):
        return getattr(service, tool)(
            dict(
                workspace_id=workspace,
                operation_id=str(uuid4()),
                expected_revision=service.get_business_state({"workspace_id": workspace})[
                    "revision"
                ],
            )
            | payload
        )

    candidate["ingredients"] = candidate["ingredients"][:1]
    candidate["ingredients"][0].update(
        description="Mel", ingredient_id=None, quantity=dict(value="200", unit="g")
    )
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    resolved = command(
        "resolve_recipe_ingredient",
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][0]["line_id"],
        new_ingredient=dict(name="Mel", dimension="g"),
        evidence=evidence("O ingrediente é mel."),
    )["data"]
    recipe, ingredient = resolved["candidate"], resolved["ingredient_id"]
    quote_payload = dict(
        ingredient_id=ingredient,
        description="Mel — oferta sintética",
        package_quantity=dict(value="1000", unit="g"),
        package_price="20.00",
        purchase_extra_total="0.00",
        extra_conditions="Retirada gratuita",
        availability="AVAILABLE",
        availability_context="Retirada hoje",
        max_packages=3,
        supplier="Fornecedor sintético",
        source=dict(
            kind="WEB",
            url="https://example.org/oferta-s06",
            title="Fixture offline",
            excerpt="1000 g por 20 reais; retirada gratuita",
            retrieved_at="2026-11-12T12:00:00Z",
        ),
    )
    quote = command("register_complement_quote", quote=quote_payload)["data"]["quote"]
    command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
        evidence=evidence("Tenho interesse neste prato."),
    )
    plan = command(
        "set_production_plan",
        items=[
            dict(recipe_id=recipe["id"], recipe_version=recipe["version"], position=0, batches=1)
        ],
        quote_selections=[dict(ingredient_id=ingredient, quote_id=quote["id"], quote_version=1)],
        evidence=evidence("Confirmo esta produção."),
    )["data"]["plan"]
    scope = dict(
        package_quantity=dict(value="1000", unit="g"),
        package_price="20.00",
        purchase_extra_total="0.00",
        extra_conditions="Retirada gratuita",
        availability_context="Retirada hoje",
        supplier="Fornecedor sintético",
        packages=1,
    )
    statement = (
        "Confirmo 1 pacote de 1000 g a R$ 20,00 por pacote, encargos R$ 0,00, "
        "Retirada gratuita, disponível em Fornecedor sintético: Retirada hoje."
    )
    return dict(
        service=service,
        workspace=workspace,
        command=command,
        recipe=recipe,
        quote=quote,
        quote_payload=quote_payload,
        scope=scope,
        statement=statement,
        clock=clock,
        database=database,
        original=original,
        path=path,
        plan=plan,
        candidate_payload=candidate,
    )


def confirm(p, **changes):
    return p["command"](
        "confirm_complement_quote",
        **(
            dict(
                quote_id=p["quote"]["id"],
                quote_version=p["quote"]["version"],
                scope=p["scope"],
                evidence=evidence(p["statement"]),
            )
            | changes
        ),
    )


def evaluate(p, service=None):
    return (service or p["service"]).evaluate_purchase_plan({"workspace_id": p["workspace"]})[
        "data"
    ]


def accept(p):
    return p["command"](
        "accept_recipe",
        recipe_id=p["recipe"]["id"],
        plan_item_id=p["plan"]["items"][0]["plan_item_id"],
        evaluation_id=evaluate(p)["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )


def revise_and_select(p, **changes):
    p["quote_payload"].update(changes)
    result = p["command"](
        "register_complement_quote",
        quote=p["quote_payload"],
        quote_id=p["quote"]["id"],
        expected_quote_version=p["quote"]["version"],
    )
    assert result["ok"], result
    p["quote"] = result["data"]["quote"]
    result = p["command"](
        "set_production_plan",
        items=[
            dict(
                recipe_id=p["recipe"]["id"],
                recipe_version=p["recipe"]["version"],
                position=0,
                batches=1,
            )
        ],
        quote_selections=[
            dict(
                ingredient_id=p["quote"]["ingredient_id"],
                quote_id=p["quote"]["id"],
                quote_version=p["quote"]["version"],
            )
        ],
        evidence=evidence("Confirmo esta produção."),
    )
    assert result["ok"], result
    p["plan"] = result["data"]["plan"]


@pytest.mark.parametrize(
    "price,status,balance",
    [
        ("80.00", "CONFIRMED", "0.00"),
        ("80.01", "OVER_BUDGET", "-0.01"),
        ("95.00", "OVER_BUDGET", "-15.00"),
    ],
)
def test_inclusive_budget_limit_controls_acceptance_without_mutation(
    purchase, price, status, balance
):
    p = purchase
    revise_and_select(p, package_price=price)
    p["scope"]["package_price"] = price
    p["statement"] = p["statement"].replace("20,00", price.replace(".", ","))
    assert confirm(p)["ok"]
    evaluation = evaluate(p)
    assert evaluation["purchase_status"] == status
    assert evaluation["remaining_budget"] == balance
    before = p["service"].get_business_state({"workspace_id": p["workspace"]})
    result = accept(p)
    if status == "CONFIRMED":
        assert result["ok"], result
    else:
        assert result["ok"] is False
        assert result["error"]["code"] == "BUDGET_EXCEEDED"
        assert result["error"]["details"]["remaining_budget"] == balance
        assert p["service"].get_business_state({"workspace_id": p["workspace"]}) == before


def test_specific_human_confirmation_makes_purchase_definitive_without_buying(purchase):
    p = purchase
    result = confirm(p)
    assert result["ok"], result
    confirmation = result["data"]["confirmation"]
    assert confirmation["confirmation_valid_until"] == "2026-11-13T12:00:00Z"
    evaluation = evaluate(p)
    assert evaluation["purchase_status"] == "CONFIRMED"
    assert evaluation["is_simulation"] is False
    assert evaluation["disbursement"] == "20.00"
    assert evaluation["remaining_budget"] == "60.00"
    assert evaluation["demand"][0]["purchase"]["planned_surplus"] == "800"
    assert (
        p["service"].get_inventory_snapshot({"workspace_id": p["workspace"]})["data"]
        == p["original"]
    )
    restarted = BusinessStateReader(
        SQLiteWorkspaceRepository(p["database"]), clock=lambda: p["clock"][0]
    )
    assert evaluate(p, restarted) == evaluation


@pytest.mark.parametrize(
    "statement",
    [
        "Vinte reais.",
        "Confirmo vinte reais.",
        "Sim.",
        "Talvez confirme tudo.",
        "Confirmo 1 pacote de 500 g a R$ 20,00.",
    ],
)
def test_partial_or_ambiguous_confirmation_cannot_authorize_purchase(purchase, statement):
    p = purchase
    before = p["service"].get_business_state({"workspace_id": p["workspace"]})
    result = confirm(p, evidence=evidence(statement))
    assert result["ok"] is False
    assert result["error"]["code"] == "USER_CONFIRMATION_REQUIRED"
    assert p["service"].get_business_state({"workspace_id": p["workspace"]}) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("package_price", "21.00"),
        ("package_quantity", dict(value="500", unit="g")),
        ("purchase_extra_total", "5.00"),
        ("extra_conditions", "Entrega paga"),
        ("supplier", "Outra loja"),
        ("availability_context", "Entrega amanhã"),
        ("max_packages", 0),
        ("availability", "UNAVAILABLE"),
        ("package_quantity", None),
        ("package_price", None),
        ("purchase_extra_total", None),
        ("availability", "UNKNOWN"),
    ],
)
def test_confirmation_requires_complete_matching_offer_and_sufficient_scope(purchase, field, value):
    p = purchase
    payload = p["quote_payload"] | {field: value}
    if value is None:
        payload[field + "_gap"] = "Dado desconhecido"
    revised = p["command"](
        "register_complement_quote",
        quote_id=p["quote"]["id"],
        expected_quote_version=1,
        quote=payload,
    )
    assert revised["ok"], revised
    p["quote"] = revised["data"]["quote"]
    before = p["service"].get_business_state({"workspace_id": p["workspace"]})
    result = confirm(p)
    assert result["ok"] is False
    assert result["error"]["code"] == "MISSING_INFORMATION"
    assert p["service"].get_business_state({"workspace_id": p["workspace"]}) == before


def test_confirmed_complement_prices_only_consumption_and_persists_choice(purchase):
    p = purchase
    assert confirm(p)["ok"]
    accepted = accept(p)
    assert accepted["ok"], accepted
    calculation = p["command"](
        "calculate_pricing_scenarios",
        recipe_id=p["recipe"]["id"],
        acceptance_id=accepted["data"]["acceptance"]["id"],
    )
    assert calculation["ok"], calculation
    pricing = calculation["data"]["calculation"]
    assert pricing["cmv_production"] == "4.00"
    assert pricing["cmv_per_serving"] == "2.00"
    assert pricing["minimum"]["price"] == "2.23"
    assert [s["price"] for s in pricing["scenarios"]] == ["2.50", "2.86", "3.34"]
    allocation = pricing["allocations"][0]
    assert allocation["origin"] == "QUOTE"
    assert allocation["source_id"] == p["quote"]["id"]
    assert allocation["source_version"] == "1"
    assert allocation["quantity"] == "200"
    assert allocation["purchase_quantity_base"] == "1000"
    assert allocation["acquisition_total"] == "20.00"
    result = p["command"](
        "save_menu_decision",
        recipe_id=p["recipe"]["id"],
        acceptance_id=accepted["data"]["acceptance"]["id"],
        calculation_id=pricing["id"],
        scenario_id="M20",
        evidence=evidence("Escolho M20."),
    )
    assert result["ok"], result
    reopened = BusinessStateReader(
        SQLiteWorkspaceRepository(p["database"]), clock=lambda: p["clock"][0]
    )
    state = reopened.get_business_state({"workspace_id": p["workspace"]})
    assert state["ok"], state
    assert state["data"]["menu"][0]["price"] == "2.86"
    assert state["data"]["acceptances"][0]["validity"] == "VALID"
    assert state["data"]["budget_remaining"] == "60.00"


@pytest.mark.parametrize(
    "deadline,hours", [(None, 24), ("2026-11-12T14:00:00Z", 2), ("2026-11-14T12:00:00Z", 24)]
)
def test_expiration_revalidates_decisions_and_resume_without_changing_identity(
    purchase, deadline, hours
):
    p = purchase
    if deadline:
        revise_and_select(p, valid_until=deadline)
    assert confirm(p)["ok"]
    accepted = accept(p)["data"]["acceptance"]
    calc = p["command"](
        "calculate_pricing_scenarios", recipe_id=p["recipe"]["id"], acceptance_id=accepted["id"]
    )["data"]["calculation"]
    assert p["command"](
        "save_menu_decision",
        recipe_id=p["recipe"]["id"],
        acceptance_id=accepted["id"],
        calculation_id=calc["id"],
        scenario_id="M20",
        evidence=evidence("Escolho M20."),
    )["ok"]
    original = evaluate(p)
    p["clock"][0] += timedelta(hours=hours, microseconds=-1)
    assert evaluate(p)["purchase_status"] == "CONFIRMED"
    p["clock"][0] += timedelta(microseconds=1)
    expired = evaluate(p)
    assert expired["purchase_status"] == "PENDING"
    assert any("QUOTE_EXPIRED" in gap for gap in expired["gaps"])
    assert expired["evaluation_id"] == original["evaluation_id"]
    assert expired["fingerprint"] == original["fingerprint"]
    before_bytes = p["database"].read_bytes()
    restarted = BusinessStateReader(
        SQLiteWorkspaceRepository(p["database"]), clock=lambda: p["clock"][0]
    )
    state = restarted.get_business_state({"workspace_id": p["workspace"]})
    assert state["ok"], state
    assert state["data"]["menu"] == []
    assert state["data"]["acceptances"][0]["validity"] == "INVALIDATED"
    assert state["data"]["pricing_calculations"][0]["validity"] == "INVALIDATED"
    assert p["database"].read_bytes() == before_bytes
    refused = accept(p)
    assert refused["ok"] is False
    assert refused["error"]["code"] == "QUOTE_EXPIRED"
    for tool, payload in [
        ("calculate_pricing_scenarios", dict()),
        (
            "save_menu_decision",
            dict(calculation_id=calc["id"], scenario_id="M10", evidence=evidence("Escolho M10.")),
        ),
    ]:
        result = p["command"](
            tool, recipe_id=p["recipe"]["id"], acceptance_id=accepted["id"], **payload
        )
        assert result["ok"] is False
    assert p["database"].read_bytes() == before_bytes


def test_more_packages_than_human_confirmed_requires_new_confirmation(purchase):
    p = purchase
    assert confirm(p)["ok"]
    result = p["command"](
        "set_production_plan",
        items=[
            dict(
                recipe_id=p["recipe"]["id"],
                recipe_version=p["recipe"]["version"],
                position=0,
                batches=6,
            )
        ],
        quote_selections=[
            dict(
                ingredient_id=p["quote"]["ingredient_id"],
                quote_id=p["quote"]["id"],
                quote_version=1,
            )
        ],
        evidence=evidence("Confirmo esta produção."),
    )
    assert result["ok"], result
    evaluation = evaluate(p)
    assert evaluation["demand"][0]["purchase"]["packages"] == 2
    assert evaluation["purchase_status"] == "PENDING"
    assert any("CONFIRMATION_INSUFFICIENT" in gap for gap in evaluation["gaps"])


def test_resume_distinguishes_current_confirmation_from_expired_history(purchase):
    p = purchase
    assert confirm(p)["ok"]
    state = p["service"].get_business_state({"workspace_id": p["workspace"]})["data"]
    assert state["complement_quotes"][0]["status"] == "CONFIRMED"
    assert state["complement_quotes"][0]["confirmation"]["scope"] == p["scope"]
    p["clock"][0] += timedelta(hours=24)
    state = p["service"].get_business_state({"workspace_id": p["workspace"]})["data"]
    assert state["complement_quotes"][0]["status"] == "EXPIRED"


def test_already_expired_offer_cannot_receive_new_confirmation(purchase):
    p = purchase
    revise_and_select(p, valid_until="2026-11-12T12:00:00Z")
    before = p["service"].get_business_state({"workspace_id": p["workspace"]})
    result = confirm(p)
    assert result["ok"] is False
    assert result["error"]["code"] == "QUOTE_EXPIRED"
    assert p["service"].get_business_state({"workspace_id": p["workspace"]}) == before


def test_next_successful_write_records_expiration_without_reviving_old_acceptance(purchase):
    p = purchase
    assert confirm(p)["ok"]
    acceptance = accept(p)["data"]["acceptance"]
    p["clock"][0] += timedelta(hours=24)
    result = p["command"]("register_complement_quote", quote=p["quote_payload"])
    assert result["ok"], result
    assert result["data"]["invalidated_decisions"] == [acceptance["id"]]
    assert confirm(
        p, evidence=evidence(p["statement"]) | {"captured_at": p["clock"][0].isoformat()}
    )["ok"]
    state = p["service"].get_business_state({"workspace_id": p["workspace"]})["data"]
    assert state["acceptances"][0]["validity"] == "INVALIDATED"
    assert evaluate(p)["purchase_status"] == "CONFIRMED"


def test_old_human_turn_cannot_extend_expired_confirmation(purchase):
    p = purchase
    assert confirm(p)["ok"]
    p["clock"][0] += timedelta(hours=24)
    before = p["service"].get_business_state({"workspace_id": p["workspace"]})
    result = confirm(p)
    assert result["ok"] is False
    assert result["error"]["code"] == "QUOTE_EXPIRED"
    assert p["service"].get_business_state({"workspace_id": p["workspace"]}) == before


def test_future_human_timestamp_cannot_extend_validity(purchase):
    p = purchase
    before = p["service"].get_business_state({"workspace_id": p["workspace"]})
    result = confirm(p, evidence=evidence(p["statement"]) | {"captured_at": "2026-11-14T12:00:00Z"})
    assert result["ok"] is False
    assert result["error"]["code"] == "USER_CONFIRMATION_REQUIRED"
    assert p["service"].get_business_state({"workspace_id": p["workspace"]}) == before


def test_new_confirmation_records_invalidation_of_dependent_acceptance(purchase):
    p = purchase
    assert confirm(p)["ok"]
    accepted = accept(p)["data"]["acceptance"]
    p["clock"][0] += timedelta(minutes=1)
    result = confirm(
        p, evidence=evidence(p["statement"]) | {"captured_at": p["clock"][0].isoformat()}
    )
    assert result["ok"], result
    assert result["data"]["invalidated_decisions"] == [accepted["id"]]


@pytest.mark.parametrize("tamper", ["scope", "deadline", "version", "evidence"])
def test_corrupt_confirmation_is_refused_on_public_reopen(purchase, tamper):
    p = purchase
    assert confirm(p)["ok"]
    with sqlite3.connect(p["database"]) as db:
        state = json.loads(
            db.execute(
                "SELECT state_json FROM workspaces WHERE id=?", (p["workspace"],)
            ).fetchone()[0]
        )
        confirmation = state["quote_confirmations"][0]
        if tamper == "scope":
            confirmation["scope"]["package_price"] = "1.00"
        elif tamper == "deadline":
            confirmation["confirmation_valid_until"] = "2027-11-12T12:00:00Z"
        elif tamper == "version":
            confirmation["quote_version"] = 999
        else:
            confirmation["evidence"]["statement"] = "Talvez."
        db.execute(
            "UPDATE workspaces SET state_json=? WHERE id=?", (json.dumps(state), p["workspace"])
        )
    result = p["service"].get_business_state({"workspace_id": p["workspace"]})
    assert result["ok"] is False
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"


@pytest.mark.parametrize(
    "amount,packages,spend,cost,complement",
    [("5200", 1, "27.00", "28.90", "200"), ("6200", 2, "47.00", "48.90", "1200")],
)
def test_stock_cost_and_quote_cost_remain_separate_with_one_acquisition_charge(
    purchase, amount, packages, spend, cost, complement
):
    p = purchase
    rice = next(i for i in p["original"]["items"] if i["name_original"] == "Arroz")
    candidate = p["candidate_payload"]
    candidate["ingredients"][0].update(
        description="Arroz", ingredient_id=rice["id"], quantity=dict(value=amount, unit="g")
    )
    for review in candidate["category_reviews"]:
        review["method_version"] = p["recipe"]["version"] + 1
    result = p["command"](
        "register_recipe_candidate",
        recipe_id=p["recipe"]["id"],
        expected_recipe_version=p["recipe"]["version"],
        candidate=candidate,
    )
    assert result["ok"], result
    p["recipe"] = result["data"]["candidate"]
    p["quote_payload"].update(
        ingredient_id=rice["id"],
        purchase_extra_total="7.00",
        extra_conditions="Taxa única de aquisição",
    )
    p["quote"] = p["command"]("register_complement_quote", quote=p["quote_payload"])["data"][
        "quote"
    ]
    # Seleciona a versão criada sem alterar a oferta novamente.
    p["plan"] = p["command"](
        "set_production_plan",
        items=[
            dict(
                recipe_id=p["recipe"]["id"],
                recipe_version=p["recipe"]["version"],
                position=0,
                batches=1,
            )
        ],
        quote_selections=[
            dict(ingredient_id=rice["id"], quote_id=p["quote"]["id"], quote_version=1)
        ],
        evidence=evidence("Confirmo esta produção."),
    )["data"]["plan"]
    p["scope"].update(
        packages=packages, purchase_extra_total="7.00", extra_conditions="Taxa única de aquisição"
    )
    p["statement"] = (
        p["statement"]
        .replace("1 pacote de", f"{packages} pacote{'s' if packages != 1 else ''} de")
        .replace("0,00, Retirada", "7,00, Retirada")
        .replace("Retirada gratuita", "Taxa única de aquisição")
    )
    assert confirm(p)["ok"]
    assert evaluate(p)["disbursement"] == spend
    assert evaluate(p)["feasibility_by_recipe"][0]["status"] == "ELIGIBLE", json.dumps(
        evaluate(p)["feasibility_by_recipe"], ensure_ascii=False
    )
    accepted_result = accept(p)
    assert accepted_result["ok"], json.dumps(accepted_result, ensure_ascii=False)
    accepted = accepted_result["data"]["acceptance"]
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = True
        result = p["command"](
            "calculate_pricing_scenarios", recipe_id=p["recipe"]["id"], acceptance_id=accepted["id"]
        )
    assert result["ok"], result
    calculation = result["data"]["calculation"]
    assert Decimal(calculation["cmv_production"]) == Decimal(cost)
    assert [a["origin"] for a in calculation["allocations"]] == ["INVENTORY", "QUOTE"]
    assert calculation["allocations"][0]["quantity"] == "5000"
    assert Decimal(calculation["allocations"][0]["subtotal"]) == Decimal("24.90")
    assert calculation["allocations"][1]["quantity"] == complement
    reopened = BusinessStateReader(
        SQLiteWorkspaceRepository(p["database"]), clock=lambda: p["clock"][0]
    )
    state = reopened.get_business_state({"workspace_id": p["workspace"]})
    assert state["ok"], state
    assert state["data"]["pricing_calculations"][0]["validity"] == "VALID"
    assert (
        reopened.get_inventory_snapshot({"workspace_id": p["workspace"]})["data"] == p["original"]
    )


@pytest.mark.parametrize(
    "changes",
    [
        dict(package_price="21.00"),
        dict(package_quantity=dict(value="500", unit="g")),
        dict(purchase_extra_total="5.00"),
        dict(availability="UNAVAILABLE"),
        dict(max_packages=0),
        dict(extra_conditions="Outra condição"),
    ],
)
def test_revised_selected_offer_invalidates_acceptance_and_requires_new_confirmation(
    purchase, changes
):
    p = purchase
    assert confirm(p)["ok"]
    accepted = accept(p)["data"]["acceptance"]
    result = p["command"](
        "calculate_pricing_scenarios", recipe_id=p["recipe"]["id"], acceptance_id=accepted["id"]
    )
    assert result["ok"], result
    result = p["command"](
        "register_complement_quote",
        quote_id=p["quote"]["id"],
        expected_quote_version=1,
        quote=p["quote_payload"] | changes,
    )
    assert result["ok"], result
    assert result["data"]["quote"]["status"] == "ESTIMATED"
    assert result["data"]["quote"]["confirmation"] is None
    assert result["data"]["invalidated_decisions"] == [accepted["id"]]
    before = p["service"].get_business_state({"workspace_id": p["workspace"]})
    assert before["data"]["acceptances"][0]["validity"] == "INVALIDATED"
    assert before["data"]["pricing_calculations"][0]["validity"] == "INVALIDATED"
    assert evaluate(p)["purchase_status"] == "PENDING"
    stale = confirm(p)
    assert stale["ok"] is False
    assert stale["error"]["code"] == "STALE_REVISION"
    assert p["service"].get_business_state({"workspace_id": p["workspace"]}) == before


@pytest.mark.parametrize(
    "bad",
    [
        dict(approved=True),
        dict(confirmation_valid_until="2027-01-01T00:00:00Z"),
        dict(
            evidence=dict(
                kind="WEB", statement="Confirmo", turn_ref="web", captured_at="2026-11-12T12:00:00Z"
            )
        ),
        dict(scope=dict(packages=1)),
        dict(scope=dict(packages=1.0)),
    ],
)
def test_confirmation_rejects_model_authority_and_malformed_scope(purchase, bad):
    p = purchase
    before = p["database"].read_bytes()
    result = confirm(p, **bad)
    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert p["database"].read_bytes() == before


@settings(
    max_examples=25, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None
)
@given(
    cents=st.integers(min_value=1, max_value=10000),
    confirmed=st.booleans(),
    hours=st.integers(min_value=0, max_value=30),
)
def test_prop007_acceptance_never_bypasses_confirmation_expiry_or_budget(
    purchase, cents, confirmed, hours
):
    p = purchase
    p["clock"][0] = datetime(2026, 11, 12, 12, tzinfo=UTC)
    price = f"{cents // 100}.{cents % 100:02d}"
    revise_and_select(p, package_price=price)
    p["scope"]["package_price"] = price
    p["statement"] = (
        f"Confirmo 1 pacote de 1000 g a R$ {price.replace('.', ',')} por pacote, "
        "encargos R$ 0,00, Retirada gratuita, disponível em Fornecedor sintético: Retirada hoje."
    )
    if confirmed:
        assert confirm(p)["ok"]
    p["clock"][0] += timedelta(hours=hours)
    before = p["service"].get_business_state({"workspace_id": p["workspace"]})
    result = accept(p)
    assert result["ok"] == (confirmed and hours < 24 and cents <= 8000)
    if not result["ok"]:
        assert p["service"].get_business_state({"workspace_id": p["workspace"]}) == before


def test_confirmation_is_not_current_before_its_human_timestamp(purchase):
    p = purchase
    assert confirm(p)["ok"]
    accepted = accept(p)["data"]["acceptance"]
    assert p["command"](
        "calculate_pricing_scenarios", recipe_id=p["recipe"]["id"], acceptance_id=accepted["id"]
    )["ok"]
    before = p["database"].read_bytes()
    p["clock"][0] -= timedelta(microseconds=1)
    reopened = BusinessStateReader(
        SQLiteWorkspaceRepository(p["database"]), clock=lambda: p["clock"][0]
    )
    evaluation = evaluate(p, reopened)
    assert evaluation["purchase_status"] == "PENDING"
    assert any("PRICE_UNCONFIRMED" in gap for gap in evaluation["gaps"])
    state = reopened.get_business_state({"workspace_id": p["workspace"]})["data"]
    assert state["complement_quotes"][0]["status"] == "ESTIMATED"
    assert state["acceptances"][0]["validity"] == "INVALIDATED"
    assert state["pricing_calculations"][0]["validity"] == "INVALIDATED"
    refused = accept(p)
    assert refused["ok"] is False
    assert refused["error"]["code"] == "PRICE_UNCONFIRMED"
    assert p["database"].read_bytes() == before


def test_unrepresentable_persisted_confirmation_deadline_returns_safe_storage_error(purchase):
    p = purchase
    assert confirm(p)["ok"]
    with sqlite3.connect(p["database"]) as db:
        state = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        confirmation = state["quote_confirmations"][0]
        confirmation["confirmed_at"] = "9999-12-31T12:00:00Z"
        confirmation["evidence"]["captured_at"] = confirmation["confirmed_at"]
        confirmation["confirmation_valid_until"] = "9999-12-31T23:00:00Z"
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(state),))
    before = p["database"].read_bytes()
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(p["database"]))
    result = reopened.get_business_state({"workspace_id": p["workspace"]})
    assert result["ok"] is False
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert p["database"].read_bytes() == before
