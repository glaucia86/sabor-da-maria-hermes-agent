"""S08 pela API pública, usando somente receitas e evidências sintéticas."""

from copy import deepcopy
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dona_maria.business_state import BusinessStateReader
from dona_maria.candidates import CandidateInput
from dona_maria.persistence import SQLiteWorkspaceRepository


def evidence(statement):
    return dict(
        turn_ref="synthetic-s08-user",
        statement=statement,
        captured_at="2026-11-13T12:00:00Z",
    )


def choose_menu(service, workspace, recipe, acceptance, command):
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    saved = command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence=evidence("Escolho M20."),
    )
    assert saved["ok"], saved
    return calculation, saved["data"]["decision"]


def candidate_input(recipe):
    candidate = {k: deepcopy(v) for k, v in recipe.items() if k in CandidateInput.model_fields}
    for ingredient in candidate["ingredients"]:
        ingredient.pop("line_id", None)
    for requirement in candidate["requirements"]:
        requirement.pop("id", None)
        requirement.pop("status", None)
    return candidate


@pytest.fixture
def oven_menu(pricing_workspace):
    return make_oven_menu(pricing_workspace)


def make_oven_menu(pricing_workspace):
    service, workspace, old, _, command, database = pricing_workspace()
    candidate = candidate_input(old)
    source = candidate["sources"][0]
    candidate.update(
        method="Asse o arroz no forno.",
        requirements=[
            dict(
                category="EQUIPMENT",
                key="oven",
                condition="PRESENT",
                reason="O preparo sintético exige forno.",
                source=source,
            )
        ],
    )
    for review in candidate["category_reviews"]:
        review.update(
            method_version=2, requirement_keys=["oven"] if review["category"] == "EQUIPMENT" else []
        )
        if review["category"] == "EQUIPMENT":
            review["not_applicable_reason"] = None
    revised = command(
        "register_recipe_candidate",
        recipe_id=old["id"],
        expected_recipe_version=1,
        candidate=candidate,
    )
    assert revised["ok"], revised["error"]
    recipe = revised["data"]["candidate"]
    plan = command(
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=2, position=0, batches=1)],
        evidence=evidence("Confirmo esta produção."),
    )
    fact = command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="oven",
                value=True,
                evidence=evidence("Tenho forno disponível."),
            )
        ],
    )["data"]["facts"][0]
    evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=plan["data"]["plan"]["items"][0]["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )
    assert accepted["ok"], accepted
    acceptance = accepted["data"]["acceptance"]
    calculation, decision = choose_menu(service, workspace, recipe, acceptance, command)
    return service, workspace, recipe, fact, acceptance, calculation, decision, command, database


def test_preference_survives_restart_without_replacing_acceptance(pricing_workspace):
    service, workspace, _, acceptance, command, database = pricing_workspace()
    before = service.get_business_state({"workspace_id": workspace})["data"]
    saved = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="INGREDIENT",
                term="Arroz",
                value="LIKE",
                evidence=evidence("Gosto de arroz."),
            )
        ],
    )
    assert saved["ok"], saved
    assert saved["data"]["invalidated_decisions"] == []
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    after = reopened.get_business_state({"workspace_id": workspace})["data"]
    assert after["preferences"][0]["term"] == "Arroz"
    assert after["preferences"][0]["value"] == "LIKE"
    assert after["preferences"][0]["validity"] == "VALID"
    assert after["acceptances"] == before["acceptances"]
    assert after["acceptances"][0]["id"] == acceptance["id"]
    assert after["evaluation"]["fingerprint"] == before["evaluation"]["fingerprint"]


def test_preference_replacement_requires_current_id_and_preserves_history(pricing_workspace):
    service, workspace, _, _, command, database = pricing_workspace()
    preference = dict(
        category="OTHER",
        term="  Comida CASEIRA ",
        value="LIKE",
        evidence=evidence("Gosto de comida caseira."),
    )
    first = command("record_user_preferences", preferences=[preference])
    old = first["data"]["preferences"][0]
    replacement = preference | dict(
        term="comida caseira", value="AVOID", evidence=evidence("Agora evito comida caseira.")
    )
    before = service.get_business_state({"workspace_id": workspace})
    refused = command("record_user_preferences", preferences=[replacement])
    assert refused["ok"] is False
    assert refused["error"]["code"] == "STALE_REVISION"

    assert service.get_business_state({"workspace_id": workspace}) == before
    saved = command(
        "record_user_preferences", preferences=[replacement | {"replaces_preference_id": old["id"]}]
    )
    assert saved["ok"], saved
    current = saved["data"]["preferences"][0]
    assert current["version"] == 2
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    history = reopened.get_business_state({"workspace_id": workspace})["data"]["preferences"]
    assert [(p["id"], p["value"], p["validity"]) for p in history] == [
        (old["id"], "LIKE", "INVALIDATED"),
        (current["id"], "AVOID", "VALID"),
    ]
    refused = command(
        "record_user_preferences", preferences=[preference | {"replaces_preference_id": old["id"]}]
    )
    assert refused["error"]["code"] == "STALE_REVISION"


def test_avoid_ingredient_removes_chosen_dish_without_resurrecting_after_replacement(
    pricing_workspace,
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation, decision = choose_menu(service, workspace, recipe, acceptance, command)
    stock = service.get_inventory_snapshot({"workspace_id": workspace})
    saved = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="INGREDIENT",
                term="arroz",
                value="AVOID",
                evidence=evidence("Não quero mais pratos com arroz."),
            )
        ],
    )
    assert saved["ok"], saved
    assert saved["data"]["invalidated_decisions"] == [acceptance["id"]]
    assert saved["data"]["removed_recipe_ids"] == [recipe["id"]]
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    state = reopened.get_business_state({"workspace_id": workspace})["data"]
    assert state["plan"]["items"] == []
    assert state["menu"] == []
    assert state["candidates"][0]["interest"] == "REJECTED"
    assert state["candidates"][0]["status"] == "REJECTED"
    assert [(a["id"], a["validity"]) for a in state["acceptances"]] == [
        (acceptance["id"], "INVALIDATED")
    ]
    assert [(c["id"], c["validity"]) for c in state["pricing_calculations"]] == [
        (calculation["id"], "INVALIDATED")
    ]
    assert [(d["id"], d["validity"]) for d in state["menu_decisions"]] == [
        (decision["id"], "INVALIDATED")
    ]
    assert state["budget_remaining"] == "80.00"
    assert reopened.get_inventory_snapshot({"workspace_id": workspace})["data"] == stock["data"]
    replaced = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="INGREDIENT",
                term="Arroz",
                value="LIKE",
                replaces_preference_id=saved["data"]["preferences"][0]["id"],
                evidence=evidence("Voltei a gostar de arroz."),
            )
        ],
    )
    assert replaced["ok"], replaced
    assert service.get_business_state({"workspace_id": workspace})["data"]["menu"] == []
    assert service.get_business_state({"workspace_id": workspace})["data"]["plan"]["items"] == []


def test_oven_correction_returns_current_summary_and_all_invalidations(oven_menu):
    service, workspace, recipe, fact, acceptance, calculation, decision, command, _ = oven_menu
    changed = command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="oven",
                value=False,
                replaces_fact_id=fact["id"],
                evidence=evidence("O forno quebrou e não está disponível."),
            )
        ],
    )
    assert changed["ok"], changed
    data = changed["data"]
    assert data["summary"]["workspace_revision"] == changed["revision"]
    assert data["summary"]["feasibility_by_recipe"][0]["status"] == "BLOCKED"
    assert data["invalidated_decisions"] == [acceptance["id"]]
    assert data["invalidated_calculation_ids"] == [calculation["id"]]
    assert data["invalidated_menu_decision_ids"] == [decision["id"]]
    assert data["next_action"] == "REVIEW_FEASIBILITY"
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["menu"] == []
    assert state["candidates"][0]["status"] == "BLOCKED"
    refused = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    assert refused["error"]["code"] == "STALE_EVALUATION"


def test_stove_adaptation_requires_new_production_facts_acceptance_and_price(oven_menu):
    service, workspace, recipe, fact, acceptance, _, _, command, _ = oven_menu
    command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="oven",
                value=False,
                replaces_fact_id=fact["id"],
                evidence=evidence("Não tenho mais forno, tenho air fryer."),
            )
        ],
    )
    candidate = candidate_input(recipe)
    candidate["method"] = "Cozinhe o arroz no fogão. Adaptação sintética explicitamente revisada."
    candidate["requirements"][0]["key"] = "stove"
    candidate["requirements"][0]["reason"] = "A adaptação exige fogão disponível."
    candidate["yield_per_batch"]["servings_per_batch"] = 4
    for review in candidate["category_reviews"]:
        review["method_version"] = 3
        if review["category"] == "EQUIPMENT":
            review["requirement_keys"] = ["stove"]
    revised = command(
        "register_recipe_candidate",
        recipe_id=recipe["id"],
        expected_recipe_version=2,
        candidate=candidate,
    )
    assert revised["ok"], revised
    assert revised["data"]["summary"]["feasibility_by_recipe"][0]["status"] == "PENDING"
    assert service.get_business_state({"workspace_id": workspace})["data"]["menu"] == []
    plan = command(
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=3, position=0, batches=1)],
        evidence=evidence("Confirmo um lote de quatro porções da adaptação."),
    )
    assert plan["ok"], plan
    assert plan["data"]["summary"]["feasibility_by_recipe"][0]["status"] == "PENDING"
    changed = command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="stove",
                value=True,
                evidence=evidence("Tenho fogão disponível para esta adaptação."),
            )
        ],
    )
    assert changed["data"]["next_action"] == "ASK_EXPLICIT_ACCEPTANCE"
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["menu"] == []
    assert all(a["validity"] == "INVALIDATED" for a in state["acceptances"])
    accepted = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=plan["data"]["plan"]["items"][0]["plan_item_id"],
        evaluation_id=changed["data"]["summary"]["evaluation_id"],
        evidence=evidence("Aceito este prato."),
    )
    assert accepted["ok"], accepted["error"]
    assert accepted["data"]["acceptance"]["id"] != acceptance["id"]
    calculation, _ = choose_menu(
        service, workspace, recipe, accepted["data"]["acceptance"], command
    )
    assert calculation["cmv_per_serving"] == "5.00"
    assert (
        service.get_business_state({"workspace_id": workspace})["data"]["menu"][0]["price"]
        == "7.15"
    )


def test_current_avoid_cannot_be_bypassed_by_interest_or_a_new_plan(pricing_workspace):
    service, workspace, recipe, _, command, _ = pricing_workspace()
    saved = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="INGREDIENT",
                term="Arroz",
                value="AVOID",
                evidence=evidence("Evito arroz."),
            )
        ],
    )
    assert saved["ok"], saved
    before = service.get_business_state({"workspace_id": workspace})
    interested = command(
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
        evidence=evidence("Tenho interesse."),
    )
    assert interested["ok"] is False
    assert interested["error"]["code"] == "CONSTRAINT_BLOCKED"
    planned = command(
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=1, position=0, batches=1)],
        evidence=evidence("Confirmo esta produção."),
    )
    assert planned["error"]["code"] == "CONSTRAINT_BLOCKED"
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_preference_batch_rolls_back_refusal_when_later_replacement_is_stale(pricing_workspace):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace()
    choose_menu(service, workspace, recipe, acceptance, command)
    before = service.get_business_state({"workspace_id": workspace})
    result = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="INGREDIENT",
                term="Arroz",
                value="AVOID",
                evidence=evidence("Evito arroz."),
            ),
            dict(
                category="PREPARATION",
                term="forno",
                value="LIKE",
                replaces_preference_id=str(uuid4()),
                evidence=evidence("Gosto de preparos no forno."),
            ),
        ],
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "STALE_REVISION"
    assert service.get_business_state({"workspace_id": workspace}) == before


@pytest.mark.parametrize(
    ("term", "matches"), [("arroz doce", False), ("ARROZ", True), ("doce de leite", True)]
)
def test_ingredient_preference_matches_each_ingredient_separately(pricing_workspace, term, matches):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace()
    choose_menu(service, workspace, recipe, acceptance, command)
    candidate = candidate_input(recipe)
    candidate["ingredients"].append(deepcopy(candidate["ingredients"][0]))
    candidate["ingredients"][1]["description"] = "Doce de leite"
    registered = command("register_recipe_candidate", candidate=candidate)
    assert registered["ok"], registered
    new_recipe = registered["data"]["candidate"]
    before = service.get_business_state({"workspace_id": workspace})["data"]
    saved = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="INGREDIENT", term=term, value="AVOID", evidence=evidence("Evito " + term)
            )
        ],
    )
    assert saved["ok"], saved
    assert (new_recipe["id"] in saved["data"]["affected_recipe_ids"]) is matches
    after = service.get_business_state({"workspace_id": workspace})["data"]
    if not matches:
        assert saved["data"]["invalidated_decisions"] == []
        assert after["plan"] == before["plan"]
        assert after["menu"] == before["menu"]
        assert after["acceptances"] == before["acceptances"]


@pytest.mark.parametrize("revise", [False, True])
def test_avoided_candidate_response_matches_persisted_interest(pricing_workspace, revise):
    service, workspace, recipe, _, command, _ = pricing_workspace()
    saved = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="INGREDIENT",
                term="Arroz",
                value="AVOID",
                evidence=evidence("Evito arroz."),
            )
        ],
    )
    assert saved["ok"], saved
    revision = dict(recipe_id=recipe["id"], expected_recipe_version=1) if revise else {}
    result = command(
        "register_recipe_candidate",
        candidate=candidate_input(recipe),
        **revision,
    )
    assert result["ok"], result
    returned = result["data"]["candidate"]
    candidates = service.get_business_state({"workspace_id": workspace})["data"]["candidates"]
    persisted = next(c for c in candidates if c["id"] == returned["id"])
    assert returned["interest"] == persisted["interest"] == "REJECTED"


def test_recipe_revision_that_becomes_avoided_is_removed_atomically(pricing_workspace):
    service, workspace, recipe, acceptance, command, _ = pricing_workspace()
    choose_menu(service, workspace, recipe, acceptance, command)
    saved = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="PREPARATION",
                term="forno",
                value="AVOID",
                evidence=evidence("Evito preparos no forno."),
            )
        ],
    )
    assert saved["data"]["invalidated_decisions"] == []
    candidate = candidate_input(recipe)
    candidate["method"] = "Asse no forno. Variante sintética explicitamente revisada."
    for review in candidate["category_reviews"]:
        review["method_version"] = 2
    revised = command(
        "register_recipe_candidate",
        recipe_id=recipe["id"],
        expected_recipe_version=1,
        candidate=candidate,
    )
    assert revised["ok"], revised
    state = service.get_business_state({"workspace_id": workspace})["data"]
    assert state["plan"]["items"] == []
    assert state["candidates"][0]["status"] == "REJECTED"
    assert state["menu"] == []


def test_title_unrelated_fact_and_price_only_change_preserve_financial_basis(oven_menu):
    service, workspace, recipe, _, acceptance, calculation, decision, command, _ = oven_menu
    before = service.get_business_state({"workspace_id": workspace})["data"]
    candidate = candidate_input(recipe)
    candidate["title"] = "Arroz assado com título corrigido"
    for review in candidate["category_reviews"]:
        review["method_version"] = 3
    revised = command(
        "register_recipe_candidate",
        recipe_id=recipe["id"],
        expected_recipe_version=2,
        candidate=candidate,
    )
    assert revised["ok"], revised
    assert revised["data"]["invalidated_decisions"] == []
    unrelated = command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="blender",
                value=False,
                evidence=evidence("Não tenho liquidificador."),
            )
        ],
    )
    assert unrelated["ok"], unrelated
    assert unrelated["data"]["invalidated_decisions"] == []
    assert unrelated["data"]["next_action"] == "REVIEW_MENU"
    saved = command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M30",
        evidence=evidence("Escolho M30."),
    )
    assert saved["ok"], saved
    after = service.get_business_state({"workspace_id": workspace})["data"]
    assert after["evaluation"]["fingerprint"] == before["evaluation"]["fingerprint"]
    assert after["acceptances"] == before["acceptances"]
    assert after["pricing_calculations"] == before["pricing_calculations"]
    assert after["evaluation"]["disbursement"] == before["evaluation"]["disbursement"]
    assert after["menu"][0]["price"] == "16.67"
    assert [(d["id"], d["validity"]) for d in after["menu_decisions"]] == [
        (decision["id"], "INVALIDATED"),
        (saved["data"]["decision"]["id"], "VALID"),
    ]
    changed = command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="oven",
                value=False,
                replaces_fact_id=after["kitchen_facts"][0]["id"],
                evidence=evidence("O forno deixou de estar disponível."),
            )
        ],
    )
    assert changed["data"]["invalidated_menu_decision_ids"] == [saved["data"]["decision"]["id"]]


def test_like_never_satisfies_missing_or_blocked_equipment(oven_menu):
    service, workspace, recipe, fact, _, _, _, command, _ = oven_menu
    command(
        "record_kitchen_facts",
        facts=[
            dict(
                category="EQUIPMENT",
                key="oven",
                value=False,
                replaces_fact_id=fact["id"],
                evidence=evidence("Não tenho forno disponível."),
            )
        ],
    )
    saved = command(
        "record_user_preferences",
        preferences=[
            dict(
                category="PREPARATION",
                term="forno",
                value="LIKE",
                evidence=evidence("Gosto de preparos no forno."),
            )
        ],
    )
    assert saved["ok"], saved
    assert saved["data"]["summary"]["feasibility_by_recipe"][0]["status"] == "BLOCKED"
    assert service.get_business_state({"workspace_id": workspace})["data"]["menu"] == []


@pytest.mark.parametrize("case", ["blank", "category", "web", "extra", "duplicate", "foreign"])
def test_invalid_preferences_leave_the_workspace_unchanged(pricing_workspace, case):
    service, workspace, _, _, command, _ = pricing_workspace()
    p = dict(
        category="INGREDIENT", term="Arroz", value="LIKE", evidence=evidence("Gosto de arroz.")
    )
    if case == "blank":
        p["term"] = "   "
    elif case == "category":
        p["category"] = "EQUIPMENT"
    elif case == "web":
        p["evidence"]["kind"] = "WEB"
    elif case == "extra":
        p["approved"] = True
    elif case == "foreign":
        p["replaces_preference_id"] = str(uuid4())
    before = service.get_business_state({"workspace_id": workspace})
    result = command("record_user_preferences", preferences=[p, p] if case == "duplicate" else [p])
    assert result["ok"] is False
    assert result["error"]["code"] == (
        "STALE_REVISION" if case == "foreign" else "VALIDATION_ERROR"
    )
    assert service.get_business_state({"workspace_id": workspace}) == before


def test_new_candidate_still_requests_clarification_without_an_active_plan(
    pricing_workspace, recipe_candidate
):
    _, _, _, _, command, _ = pricing_workspace()
    cleared = command(
        "set_production_plan", items=[], evidence=evidence("Confirmo limpar o plano.")
    )
    assert cleared["ok"]
    candidate = deepcopy(recipe_candidate)
    candidate.pop("yield_per_batch", None)
    candidate["yield_gap"] = "Rendimento ainda desconhecido."
    result = command("register_recipe_candidate", candidate=candidate)
    assert result["ok"], result
    assert result["data"]["next_action"] == "CLARIFY_CANDIDATE_GAPS"


@settings(
    max_examples=12,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(changes=st.lists(st.booleans(), max_size=6))
def test_prop006_fact_changes_replay_and_return_never_resurrect_decisions(
    pricing_workspace, changes
):
    service, workspace, _, fact, acceptance, calculation, decision, _, database = make_oven_menu(
        pricing_workspace
    )
    for available in [False, *changes, True]:
        before = service.get_business_state({"workspace_id": workspace})
        request = dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=before["revision"],
            facts=[
                dict(
                    category="EQUIPMENT",
                    key="oven",
                    value=available,
                    replaces_fact_id=fact["id"],
                    evidence=evidence("Atualizo a disponibilidade do forno."),
                )
            ],
        )
        saved = service.record_kitchen_facts(request)
        assert saved["ok"], saved
        fact = saved["data"]["facts"][0]
        assert service.record_kitchen_facts(request) == saved
        state = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
            {"workspace_id": workspace}
        )
        assert state["revision"] == before["revision"] + 1
        assert state["data"]["menu"] == []
        assert (
            next(a for a in state["data"]["acceptances"] if a["id"] == acceptance["id"])["validity"]
            == "INVALIDATED"
        )
        assert (
            next(c for c in state["data"]["pricing_calculations"] if c["id"] == calculation["id"])[
                "validity"
            ]
            == "INVALIDATED"
        )
        assert (
            next(d for d in state["data"]["menu_decisions"] if d["id"] == decision["id"])[
                "validity"
            ]
            == "INVALIDATED"
        )
