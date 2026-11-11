"""Comportamentos S02 pela interface pública; receitas inteiramente sintéticas."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


@pytest.fixture
def kitchen(tmp_path, inventory_file, recipe_candidate):
    database = tmp_path / "kitchen.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    service = BusinessStateReader(
        SQLiteWorkspaceRepository(database), clock=lambda: datetime(2026, 11, 11, tzinfo=UTC)
    )
    workspace = created["workspace_id"]
    inventory = service.get_inventory_snapshot({"workspace_id": workspace})["data"]
    recipe_candidate["ingredients"][0]["ingredient_id"] = inventory["items"][0]["id"]

    def command(tool, **payload):
        revision = service.get_business_state({"workspace_id": workspace})["revision"]
        return getattr(service, tool)(
            dict(workspace_id=workspace, operation_id=str(uuid4()), expected_revision=revision)
            | payload
        )

    registered = command("register_recipe_candidate", candidate=recipe_candidate)
    return service, workspace, registered["data"]["candidate"], command, database


def evidence(statement):
    return {
        "turn_ref": "synthetic-user-turn-1",
        "statement": statement,
        "captured_at": "2026-11-11T00:00:00Z",
    }


def test_interest_is_recoverable_but_never_accepts_a_recipe(kitchen):
    service, workspace, recipe, command, database = kitchen
    result = command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
        evidence=evidence("Tenho interesse neste arroz."),
    )
    assert result["ok"] is True
    recovered = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )
    assert recovered["data"]["candidates"][0]["interest"] == "INTERESTED"
    assert recovered["data"]["acceptances"] == []
    assert recovered["data"]["budget_remaining"] == "80.00"


@pytest.fixture
def producible(kitchen, recipe_candidate):
    service, workspace, old_recipe, command, database = kitchen
    source = recipe_candidate["sources"][0]
    recipe_candidate.pop("yield_gap")
    recipe_candidate.pop("context_gap")
    recipe_candidate.update(
        yield_per_batch={"servings_per_batch": 5, "sale_unit_label": "porção", "source": source},
        operational_context="Um lote leva 30 minutos no forno.",
        context_source=source,
        requirements=[
            dict(
                category="EQUIPMENT",
                key="oven",
                condition="PRESENT",
                reason="Método sintético usa forno.",
                source=source,
            )
        ],
        category_reviews=[
            dict(
                category=category,
                requirement_keys=["oven"] if category == "EQUIPMENT" else [],
                method_version=2,
                source=source,
                not_applicable_reason=None
                if category == "EQUIPMENT"
                else "Método sintético revisto não exige condição específica nesta categoria.",
            )
            for category in ("EQUIPMENT", "SKILL", "OPERATION")
        ],
    )
    recipe = command(
        "register_recipe_candidate",
        recipe_id=old_recipe["id"],
        expected_recipe_version=1,
        candidate=recipe_candidate,
    )["data"]["candidate"]
    return service, workspace, recipe, command, database


def test_confirmed_whole_batches_preserve_adjusted_yield_and_surplus(producible):
    service, workspace, recipe, command, _ = producible
    result = command(
        "set_production_plan",
        items=[
            dict(
                recipe_id=recipe["id"],
                recipe_version=2,
                position=0,
                batches=3,
                requested_servings=12,
            )
        ],
        evidence=evidence("Confirmo 3 lotes, 15 porções e sobra de 3."),
    )
    assert result["ok"] is True
    item = result["data"]["plan"]["items"][0]
    assert item["servings"] == 15
    assert item["surplus_servings"] == 3
    recovered = service.get_business_state({"workspace_id": workspace})
    assert recovered["data"]["plan"]["items"] == [item]
    assert recovered["data"]["budget_remaining"] == "80.00"


def plan_one(kitchen, batches=1):
    _, _, recipe, command, _ = kitchen
    result = command(
        "set_production_plan",
        items=[
            dict(
                recipe_id=recipe["id"],
                recipe_version=recipe["version"],
                position=0,
                batches=batches,
            )
        ],
        evidence=evidence(f"Confirmo {batches} lote(s) desta receita."),
    )
    assert result["ok"], result
    return result["data"]["plan"]["items"][0]


def test_unknown_oven_asks_and_confirmed_absence_blocks_without_acceptance(producible):
    service, workspace, recipe, command, _ = producible
    item = plan_one(producible)
    query = dict(workspace_id=workspace, recipe_id=recipe["id"], plan_item_id=item["plan_item_id"])
    before = service.get_business_state({"workspace_id": workspace})
    pending = service.evaluate_recipe_feasibility(query)
    assert pending["ok"] is True
    assert pending["data"]["status"] == "PENDING"
    assert pending["data"]["requirements"][0]["status"] == "UNKNOWN"
    assert "oven" in pending["data"]["requirements"][0]["question"]
    assert service.get_business_state({"workspace_id": workspace}) == before
    saved = command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="oven",
                value=False,
                evidence=evidence("Não tenho forno."),
            )
        ],
    )
    assert saved["ok"] is True
    blocked = service.evaluate_recipe_feasibility(query)
    assert blocked["data"]["status"] == "BLOCKED"
    assert blocked["data"]["requirements"][0]["status"] == "BLOCKED"
    assert service.get_business_state({"workspace_id": workspace})["data"]["acceptances"] == []


def test_purchase_evaluation_aggregates_all_drafts_without_debiting_stock(producible):

    service, workspace, recipe, command, _ = producible
    candidate = {
        key: deepcopy(recipe[key])
        for key in (
            "title",
            "sources",
            "ingredients",
            "method",
            "method_source",
            "yield_per_batch",
            "operational_context",
            "context_source",
            "category_reviews",
            "requirements",
        )
    }
    for ingredient in candidate["ingredients"]:
        ingredient.pop("line_id")
        ingredient["quantity"]["value"] = "3000"
    for requirement in candidate["requirements"]:
        requirement.pop("id")
        requirement.pop("status")
    candidate["title"] = "Segundo arroz — fixture"
    for review in candidate["category_reviews"]:
        review["method_version"] = 1
    second = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    command(
        "set_production_plan",
        items=[
            dict(recipe_id=recipe["id"], recipe_version=2, position=0, batches=30),
            dict(recipe_id=second["id"], recipe_version=1, position=1, batches=1),
        ],
        evidence=evidence("Confirmo estes lotes para os dois pratos."),
    )
    inventory = service.get_inventory_snapshot({"workspace_id": workspace})["data"]
    query = {"workspace_id": workspace}
    evaluation = service.evaluate_purchase_plan(query)
    assert evaluation["ok"] is True
    line = evaluation["data"]["demand"][0]
    assert line["required"] == "6000"
    assert line["stock_used"] == "5000"
    assert line["shortage"] == "1000"
    assert evaluation["data"]["purchase_status"] == "PENDING"
    assert evaluation["data"]["disbursement"] is None
    assert service.evaluate_purchase_plan(query) == evaluation
    assert service.get_inventory_snapshot(query)["data"] == inventory


def ready_for_acceptance(kitchen):
    service, workspace, recipe, command, _ = kitchen
    item = plan_one(kitchen)
    command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
        evidence=evidence("Tenho interesse neste prato."),
    )
    command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="oven",
                value=True,
                evidence=evidence("Tenho forno disponível."),
            )
        ],
    )
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    return item, evaluation


def test_explicit_acceptance_binds_current_summary_and_survives_restart(producible):
    service, workspace, recipe, command, database = producible
    item, evaluation = ready_for_acceptance(producible)
    inventory = service.get_inventory_snapshot({"workspace_id": workspace})["data"]
    assert evaluation["purchase_status"] == "CONFIRMED"
    assert evaluation["disbursement"] == "0.00"
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato conforme este resumo."),
    )
    assert accepted["ok"] is True
    acceptance = accepted["data"]["acceptance"]
    assert acceptance["fingerprint"] == evaluation["fingerprint"]
    assert acceptance["evaluation_id"] == evaluation["evaluation_id"]
    assert acceptance["validity"] == "VALID"
    resumed = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )
    assert resumed["data"]["acceptances"] == [acceptance]
    assert resumed["data"]["candidates"][0]["status"] == "ACCEPTED"
    assert resumed["data"]["budget_remaining"] == "80.00"
    assert service.get_inventory_snapshot({"workspace_id": workspace})["data"] == inventory


def test_changing_facts_does_not_resurrect_old_acceptance_and_rejection_removes_plan(producible):
    service, workspace, recipe, command, _ = producible
    item, evaluation = ready_for_acceptance(producible)
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )["data"]["acceptance"]
    fact = service.get_business_state({"workspace_id": workspace})["data"]["kitchen_facts"][0]
    for value in (False, True):
        changed = command(
            "record_kitchen_facts",
            facts=[
                dict(
                    category="EQUIPMENT",
                    key="oven",
                    value=value,
                    replaces_fact_id=fact["id"],
                    evidence=evidence("Atualizo a disponibilidade do forno."),
                )
            ],
        )
        assert changed["ok"] is True
        fact = changed["data"]["facts"][0]
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["acceptances"][0]["validity"] == "INVALIDATED"
    assert state["acceptances"][0]["id"] == accepted["id"]
    rejected = command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="REJECTED",
        evidence=evidence("Não quero mais este prato. Quero outra candidata."),
    )
    assert rejected["ok"] is True
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["plan"]["items"] == []
    assert state["candidates"][0]["status"] == "REJECTED"
    assert state["budget_remaining"] == "80.00"


def candidate_input(recipe):
    keys = (
        "title",
        "sources",
        "ingredients",
        "method",
        "method_source",
        "yield_per_batch",
        "operational_context",
        "context_source",
        "category_reviews",
        "requirements",
    )
    candidate = {key: deepcopy(recipe[key]) for key in keys}
    for ingredient in candidate["ingredients"]:
        ingredient.pop("line_id", None)
    for requirement in candidate["requirements"]:
        requirement.pop("id", None)
        requirement.pop("status", None)
    return candidate


@pytest.mark.parametrize(
    "condition,category,key,required,unit,available,expected",
    [
        ("MIN_CAPACITY", "EQUIPMENT", "pot", "2", "L", "1", "BLOCKED"),
        ("MIN_CAPACITY", "EQUIPMENT", "pot", "2", "L", "2", "ELIGIBLE"),
        ("MIN_AVAILABLE_TIME", "OPERATION", "time", "30", "min", "29", "BLOCKED"),
        ("MIN_AVAILABLE_TIME", "OPERATION", "time", "30", "min", "30", "ELIGIBLE"),
        ("EXPLICIT_CONDITION", "OPERATION", "storage", "refrigerado", None, "ambiente", "BLOCKED"),
        (
            "EXPLICIT_CONDITION",
            "OPERATION",
            "storage",
            "refrigerado",
            None,
            "refrigerado",
            "ELIGIBLE",
        ),
    ],
)
def test_typed_capacity_time_and_explicit_conditions_are_checked_at_confirmed_scale(
    producible,
    condition,
    category,
    key,
    required,
    unit,
    available,
    expected,
):
    service, workspace, recipe, command, database = producible
    candidate = candidate_input(recipe)
    source = candidate["sources"][0]
    candidate["requirements"] = [
        dict(
            category=category,
            key=key,
            condition=condition,
            value=required,
            unit=unit,
            reason="Condição do método.",
            source=source,
        )
    ]
    for review in candidate["category_reviews"]:
        review["method_version"] = 3
        review["requirement_keys"] = [key] if review["category"] == category else []
        review["not_applicable_reason"] = (
            None if review["category"] == category else "Método revisado."
        )
    revised = command(
        "register_recipe_candidate",
        recipe_id=recipe["id"],
        expected_recipe_version=2,
        candidate=candidate,
    )["data"]["candidate"]
    item = plan_one((service, workspace, revised, command, database))
    saved = command(
        "record_kitchen_facts",
        facts=[
            dict(
                category=category,
                key=key,
                value=available,
                unit=unit,
                evidence=evidence("Informo esta condição de produção."),
            )
        ],
    )
    assert saved["ok"] is True
    result = service.evaluate_recipe_feasibility(
        dict(workspace_id=workspace, recipe_id=recipe["id"], plan_item_id=item["plan_item_id"])
    )
    assert result["data"]["status"] == expected


def test_multiple_batches_require_plan_scoped_sequencing_confirmation(producible):
    service, workspace, recipe, command, _ = producible
    item = plan_one(producible, batches=3)
    command(
        "record_kitchen_facts",
        facts=[
            dict(category="EQUIPMENT", key="oven", value=True, evidence=evidence("Tenho forno."))
        ],
    )
    before = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert before["feasibility_by_recipe"][0]["status"] == "PENDING"
    plan = service.get_business_state({"workspace_id": workspace})["data"]["plan"]
    command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="OPERATION",
                key="production_arrangement",
                value="SEQUENTIAL",
                context=f"{plan['id']}:{plan['version']}",
                evidence=evidence(
                    "Confirmo produzir os três lotes em sequência usando o mesmo forno."
                ),
            )
        ],
    )
    after = service.evaluate_recipe_feasibility(
        dict(workspace_id=workspace, recipe_id=recipe["id"], plan_item_id=item["plan_item_id"])
    )
    assert after["data"]["status"] == "ELIGIBLE"
    plan_one(producible, batches=4)
    changed = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert changed["feasibility_by_recipe"][0]["status"] == "PENDING"


def test_requested_servings_do_not_confirm_adjusted_batches_implicitly(producible):
    service, workspace, recipe, command, _ = producible
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "set_production_plan",
        items=[
            dict(
                recipe_id=recipe["id"],
                recipe_version=2,
                position=0,
                batches=3,
                requested_servings=12,
            )
        ],
        evidence=evidence("Quero 12 porções."),
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "USER_CONFIRMATION_REQUIRED"
    assert "15" in result["error"]["message"]
    assert service.get_business_state({"workspace_id": workspace}) == before


@pytest.mark.parametrize(
    "case,code",
    [
        ("ambiguous", "USER_CONFIRMATION_REQUIRED"),
        ("negative", "USER_CONFIRMATION_REQUIRED"),
        ("unknown", "MISSING_INFORMATION"),
        ("blocked", "CONSTRAINT_BLOCKED"),
        ("unreviewed", "MISSING_INFORMATION"),
        ("missing_yield", "MISSING_INFORMATION"),
        ("missing_quantity", "MISSING_INFORMATION"),
        ("cooked", "MISSING_INFORMATION"),
        ("stale_evaluation", "STALE_EVALUATION"),
        ("foreign_item", "NOT_FOUND"),
        ("foreign_recipe", "NOT_FOUND"),
        ("derived_field", "VALIDATION_ERROR"),
        ("web_confirmation", "VALIDATION_ERROR"),
        ("no_interest", "USER_CONFIRMATION_REQUIRED"),
    ],
)
def test_direct_acceptance_guards_refuse_without_any_state_change(producible, case, code):
    service, workspace, recipe, command, _ = producible
    item, evaluation = ready_for_acceptance(producible)
    statement = "Aceito este prato."
    if case in {"unknown", "blocked"}:
        fact = service.get_business_state({"workspace_id": workspace})["data"]["kitchen_facts"][0]
        command(
            "record_kitchen_facts",
            facts=[
                dict(
                    category="EQUIPMENT",
                    key="oven",
                    value="desconhecido" if case == "unknown" else False,
                    replaces_fact_id=fact["id"],
                    evidence=evidence("Corrijo o estado do forno."),
                )
            ],
        )
    if case in {"unreviewed", "missing_yield", "missing_quantity", "cooked"}:
        candidate = candidate_input(recipe)
        for review in candidate["category_reviews"]:
            review["method_version"] = 3
        if case == "unreviewed":
            candidate["category_reviews"].pop()
        elif case == "missing_yield":
            candidate["yield_per_batch"] = None
            candidate["yield_gap"] = "Rendimento desconhecido."
        elif case == "missing_quantity":
            candidate["ingredients"][0].update(quantity=None, quantity_gap="Medida desconhecida.")
        else:
            candidate["ingredients"][0]["preparation_basis"] = "COOKED"
        revised = command(
            "register_recipe_candidate",
            recipe_id=recipe["id"],
            expected_recipe_version=2,
            candidate=candidate,
        )["data"]["candidate"]
        item = plan_one((service, workspace, revised, command, None))
    if case == "no_interest":
        command(
            "record_recipe_feedback",
            recipe_id=recipe["id"],
            feedback="UNDECIDED",
            evidence=evidence("Ainda não decidi."),
        )
    previous_evaluation = evaluation
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    if case == "ambiguous":
        statement = "Parece bom."
    if case == "negative":
        statement = "Não aceito este prato."
    payload = dict(
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence(statement),
    )
    if case == "stale_evaluation":
        plan_one(producible)
        payload["evaluation_id"] = previous_evaluation["evaluation_id"]
    if case == "foreign_item":
        payload["plan_item_id"] = str(uuid4())
    if case == "foreign_recipe":
        payload["recipe_id"] = str(uuid4())
    if case == "derived_field":
        payload["approved"] = True
    if case == "web_confirmation":
        payload["evidence"]["kind"] = "WEB"
    before = service.get_business_state({"workspace_id": workspace})
    refused = command("accept_recipe", **payload)
    assert refused["ok"] is False, refused
    assert refused["error"]["code"] == code
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_active_recipe_revision_announces_invalidated_acceptance_before_return(producible):
    _, _, recipe, command, _ = producible
    item, evaluation = ready_for_acceptance(producible)
    acceptance = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )["data"]["acceptance"]
    candidate = candidate_input(recipe)
    candidate["ingredients"][0]["quantity"]["value"] = "200"
    for review in candidate["category_reviews"]:
        review["method_version"] = 3
    result = command(
        "register_recipe_candidate",
        recipe_id=recipe["id"],
        expected_recipe_version=2,
        candidate=candidate,
    )
    assert result["ok"] is True
    assert result["data"]["invalidated_decisions"] == [acceptance["id"]]


def test_title_correction_preserves_the_accepted_business_basis(producible):
    service, workspace, recipe, command, _ = producible
    item, evaluation = ready_for_acceptance(producible)
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )["data"]["acceptance"]
    candidate = candidate_input(recipe)
    candidate["title"] = "Arroz com título corrigido — fixture"
    for review in candidate["category_reviews"]:
        review["method_version"] = 3
    result = command(
        "register_recipe_candidate",
        recipe_id=recipe["id"],
        expected_recipe_version=2,
        candidate=candidate,
    )
    assert result["data"]["invalidated_decisions"] == []
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["candidates"][0]["title"] == candidate["title"]
    assert state["acceptances"] == [accepted]


def test_state_reports_current_readiness_and_the_facts_that_satisfy_requirements(producible):
    service, workspace, _, _, _ = producible
    ready_for_acceptance(producible)
    state = service.get_business_state({"workspace_id": workspace})["data"]
    candidate = state["candidates"][0]
    assert candidate["status"] == "READY_FOR_ACCEPTANCE"
    assert candidate["requirements"][0]["status"] == "CONFIRMED"
    assert candidate["requirements"][0]["fact_ids"] == [state["kitchen_facts"][0]["id"]]
    assert state["next_action"] == "ASK_EXPLICIT_ACCEPTANCE"


def test_rejected_candidate_cannot_be_reintroduced_by_production_plan(producible):
    service, workspace, recipe, command, _ = producible
    command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="REJECTED",
        evidence=evidence("Não quero este prato."),
    )
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=2, position=0, batches=1)],
        evidence=evidence("Confirmo um lote."),
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "CONSTRAINT_BLOCKED"
    assert service.get_business_state({"workspace_id": workspace}) == before


@settings(
    max_examples=20,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    events=st.lists(
        st.tuples(
            st.sampled_from([True, False, None]),
            st.integers(min_value=1, max_value=80),
            st.sampled_from(["INTERESTED", "REJECTED", "UNDECIDED"]),
        ),
        min_size=1,
        max_size=6,
    )
)
def test_prop007_fact_plan_and_acceptance_sequences_never_bypass_guards(
    producible,
    inventory_file,
    tmp_path,
    events,
):
    _, _, template, _, _ = producible
    database = tmp_path / f"sequence-{uuid4()}.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    service = BusinessStateReader(SQLiteWorkspaceRepository(database))

    def command(tool, **payload):
        state = service.get_business_state({"workspace_id": workspace})
        return getattr(service, tool)(
            dict(
                workspace_id=workspace,
                operation_id=str(uuid4()),
                expected_revision=state["revision"],
            )
            | payload
        )

    candidate = candidate_input(template)
    for review in candidate["category_reviews"]:
        review["method_version"] = 1
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    inventory = service.get_inventory_snapshot({"workspace_id": workspace})["data"]
    for available, batches, interest in events:
        state = service.get_business_state({"workspace_id": workspace})["data"]
        previous = next((f for f in state["kitchen_facts"] if f["key"] == "oven"), None)
        command(
            "record_kitchen_facts",
            facts=[
                dict(
                    category="EQUIPMENT",
                    key="oven",
                    value="desconhecido" if available is None else available,
                    replaces_fact_id=previous["id"] if previous else None,
                    evidence=evidence("Condição sintética gerada para o forno."),
                )
            ],
        )
        command(
            "record_recipe_feedback",
            recipe_id=recipe["id"],
            feedback=interest,
            evidence=evidence("Feedback sintético gerado."),
        )
        if interest == "REJECTED":
            assert (
                service.get_business_state({"workspace_id": workspace})["data"]["plan"] is None
                or not service.get_business_state({"workspace_id": workspace})["data"]["plan"][
                    "items"
                ]
            )
            continue
        plan = command(
            "set_production_plan",
            items=[dict(recipe_id=recipe["id"], recipe_version=1, position=0, batches=batches)],
            evidence=evidence("Confirmo os lotes da fixture."),
        )["data"]["plan"]
        if batches > 1:
            state = service.get_business_state({"workspace_id": workspace})["data"]
            previous = next(
                (f for f in state["kitchen_facts"] if f["key"] == "production_arrangement"), None
            )
            command(
                "record_kitchen_facts",
                facts=[
                    dict(
                        category="OPERATION",
                        key="production_arrangement",
                        value="SEQUENTIAL",
                        context=f"{plan['id']}:{plan['version']}",
                        replaces_fact_id=previous["id"] if previous else None,
                        evidence=evidence(
                            "Confirmo produzir os lotes em sequência com os recursos informados."
                        ),
                    )
                ],
            )
        evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
        result = command(
            "accept_recipe",
            recipe_id=recipe["id"],
            plan_item_id=plan["items"][0]["plan_item_id"],
            evaluation_id=evaluation["evaluation_id"],
            evidence=evidence("Aceito este prato."),
        )
        assert result["ok"] is (available is True and interest == "INTERESTED" and batches <= 50)
        current = service.get_business_state({"workspace_id": workspace})["data"]
        if available is not True or batches > 50 or interest != "INTERESTED":
            assert all(a["validity"] == "INVALIDATED" for a in current["acceptances"])
        assert current["budget_initial"] == "80.00"
        assert service.get_inventory_snapshot({"workspace_id": workspace})["data"] == inventory


def test_fractional_eggs_and_batches_and_unjustified_categories_are_rejected(producible):
    service, workspace, recipe, command, _ = producible
    before = service.get_business_state({"workspace_id": workspace})
    for batches in (0, -1, "1", 1.5, True):
        result = command(
            "set_production_plan",
            items=[dict(recipe_id=recipe["id"], recipe_version=2, position=0, batches=batches)],
            evidence=evidence("Confirmo esta produção."),
        )
        assert result["error"]["code"] == "VALIDATION_ERROR"
    candidate = candidate_input(recipe)
    candidate["ingredients"][0]["quantity"] = {"value": "0.5", "unit": "un"}
    result = command("register_recipe_candidate", candidate=candidate)
    assert result["error"]["code"] == "VALIDATION_ERROR"
    candidate = candidate_input(recipe)
    candidate["category_reviews"][1]["not_applicable_reason"] = None
    result = command("register_recipe_candidate", candidate=candidate)
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_unrelated_kitchen_fact_does_not_invalidate_current_acceptance(producible):
    service, workspace, recipe, command, _ = producible
    item, evaluation = ready_for_acceptance(producible)
    acceptance = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=item["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )["data"]["acceptance"]
    result = command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="unused_freezer",
                value=False,
                evidence=evidence("Não tenho freezer."),
            )
        ],
    )
    assert result["data"]["invalidated_decisions"] == []
    assert service.get_business_state({"workspace_id": workspace})["data"]["acceptances"] == [
        acceptance
    ]


@pytest.mark.parametrize(
    "corruption",
    [
        "foreign_plan",
        "duplicate_fact",
        "acceptance_item",
        "acceptance_batches",
        "acceptance_version",
    ],
)
def test_inconsistent_persisted_production_is_refused_without_repairing_storage(
    producible, corruption
):
    import json
    import sqlite3
    from contextlib import closing

    service, workspace, recipe, command, database = producible
    item, evaluation = ready_for_acceptance(producible)
    if corruption.startswith("acceptance_"):
        accepted = command(
            "accept_recipe",
            recipe_id=recipe["id"],
            plan_item_id=item["plan_item_id"],
            evaluation_id=evaluation["evaluation_id"],
            evidence=evidence("Aceito este prato."),
        )
        assert accepted["ok"] is True
    with closing(sqlite3.connect(database)) as db:
        state = json.loads(
            db.execute("SELECT state_json FROM workspaces WHERE id=?", (workspace,)).fetchone()[0]
        )
        if corruption == "foreign_plan":
            state["plan"]["items"][0]["recipe_id"] = str(uuid4())
        elif corruption == "duplicate_fact":
            state["kitchen_facts"].append(deepcopy(state["kitchen_facts"][0]))
        elif corruption == "acceptance_item":
            state["acceptances"][0]["plan_item_id"] = str(uuid4())
        elif corruption == "acceptance_batches":
            state["acceptances"][0]["batches"] += 1
        else:
            state["acceptances"][0]["recipe_version"] += 1
        db.execute("UPDATE workspaces SET state_json=? WHERE id=?", (json.dumps(state), workspace))
        db.commit()
    original = database.read_bytes()
    result = service.get_business_state({"workspace_id": workspace})
    assert result["ok"] is False
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert database.read_bytes() == original


def test_blocked_draft_prevents_otherwise_ready_recipe_acceptance_in_global_plan(producible):
    service, workspace, recipe, command, _ = producible
    ready_for_acceptance(producible)
    candidate = candidate_input(recipe)
    candidate["requirements"].append(
        dict(
            category="SKILL",
            key="pressure_skill",
            condition="SKILL_KNOWN",
            reason="Técnica indispensável da fixture.",
            source=candidate["sources"][0],
        )
    )
    for review in candidate["category_reviews"]:
        review["method_version"] = 1
        if review["category"] == "SKILL":
            review.update(requirement_keys=["pressure_skill"], not_applicable_reason=None)
    other = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    plan = command(
        "set_production_plan",
        items=[
            dict(recipe_id=recipe["id"], recipe_version=2, position=0, batches=1),
            dict(recipe_id=other["id"], recipe_version=1, position=1, batches=1),
        ],
        evidence=evidence("Confirmo um lote de cada receita."),
    )["data"]["plan"]
    command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="SKILL",
                key="pressure_skill",
                value=False,
                evidence=evidence("Não domino esta técnica."),
            ),
            dict(
                category="OPERATION",
                key="production_arrangement",
                value="SEQUENTIAL",
                context=f"{plan['id']}:{plan['version']}",
                evidence=evidence("Confirmo preparar um prato de cada vez."),
            ),
        ],
    )
    before = service.get_business_state({"workspace_id": workspace})
    target = next(c for c in before["data"]["candidates"] if c["id"] == recipe["id"])
    assert target["status"] != "READY_FOR_ACCEPTANCE"
    refused = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=plan["items"][0]["plan_item_id"],
        evaluation_id=before["data"]["evaluation"]["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )
    assert refused["error"]["code"] == "CONSTRAINT_BLOCKED"
    assert service.get_business_state({"workspace_id": workspace}) == before


@pytest.mark.parametrize(
    "statement", ["Quero este prato.", "Parece bom.", "Confirmo um lote, mas não aceito produzir."]
)
def test_interest_or_contradictory_speech_does_not_confirm_production(producible, statement):
    service, workspace, recipe, command, _ = producible
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=2, position=0, batches=1)],
        evidence=evidence(statement),
    )
    assert result["error"]["code"] == "USER_CONFIRMATION_REQUIRED"
    assert service.get_business_state({"workspace_id": workspace}) == before


@pytest.mark.parametrize("field", ["turn_ref", "statement"])
@pytest.mark.parametrize("blank", ["   ", "\t\n\u00a0"])
def test_blank_human_evidence_cannot_register_a_kitchen_fact(kitchen, field, blank):
    service, workspace, _, command, database = kitchen
    before = service.get_business_state({"workspace_id": workspace})
    original = database.read_bytes()
    human_evidence = evidence("Tenho forno disponível.") | {field: blank}

    refused = command(
        "record_kitchen_facts",
        facts=[dict(category="EQUIPMENT", key="oven", value=True, evidence=human_evidence)],
    )

    assert refused["ok"] is False
    assert refused["error"]["code"] == "VALIDATION_ERROR"
    assert service.get_business_state({"workspace_id": workspace}) == before
    assert database.read_bytes() == original
