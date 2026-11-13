"""S07: recursos agregados, ordem explícita e decisões conservadoras na API pública."""

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


def set_plan(p, order=(0, 1), batches=1):
    result = p["command"](
        "set_production_plan",
        items=[
            dict(
                recipe_id=p["recipes"][i]["id"],
                recipe_version=p["recipes"][i]["version"],
                position=position,
                batches=batches,
            )
            for position, i in enumerate(order)
        ],
        quote_selections=[
            dict(
                ingredient_id=p["quote"]["ingredient_id"],
                quote_id=p["quote"]["id"],
                quote_version=1,
            )
        ],
        evidence=p["evidence"],
    )
    assert result["ok"], result
    return result["data"]


def state(p):
    result = p["service"].get_business_state({"workspace_id": p["workspace"]})
    assert result["ok"], result
    return result["data"]


def arrange(p):
    current = state(p)
    previous = next(
        (f for f in current["kitchen_facts"] if f["key"] == "production_arrangement"), None
    )
    result = p["command"](
        "record_kitchen_facts",
        facts=[
            dict(
                category="OPERATION",
                key="production_arrangement",
                value="SEQUENTIAL",
                context=f"{current['plan']['id']}:{current['plan']['version']}",
                replaces_fact_id=previous["id"] if previous else None,
                evidence=p["evidence"]
                | {"statement": "Confirmo capacidade e tempo para produzir em sequência."},
            )
        ],
    )
    assert result["ok"], result


def finish(p):
    calculations = []
    for item in state(p)["plan"]["items"]:
        result = p["command"](
            "accept_recipe",
            recipe_id=item["recipe_id"],
            plan_item_id=item["plan_item_id"],
            evaluation_id=state(p)["evaluation"]["evaluation_id"],
            evidence=p["evidence"] | {"statement": "Aceito este prato."},
        )
        assert result["ok"], result
        accepted = result["data"]["acceptance"]
        result = p["command"](
            "calculate_pricing_scenarios", recipe_id=item["recipe_id"], acceptance_id=accepted["id"]
        )
        assert result["ok"], result
        calculation = result["data"]["calculation"]
        result = p["command"](
            "save_menu_decision",
            recipe_id=item["recipe_id"],
            acceptance_id=accepted["id"],
            calculation_id=calculation["id"],
            scenario_id="M20",
            evidence=p["evidence"] | {"statement": "Escolho M20."},
        )
        assert result["ok"], result
        calculations.append(calculation)
    return calculations


def test_two_dishes_share_one_package_and_return_current_demand(shared_plan):
    p = shared_plan(amounts=("200", "300"), complement=True)
    result = set_plan(p)
    evaluation = result["summary"]
    assert (
        evaluation == p["service"].evaluate_purchase_plan({"workspace_id": p["workspace"]})["data"]
    )
    (line,) = evaluation["demand"]
    assert line["required"] == "500"
    assert line["stock_used"] == "0"
    assert line["shortage"] == "500"
    purchase = line["purchase"]
    assert purchase["packages"] == 1
    assert purchase["purchased_quantity"] == "1000"
    assert purchase["planned_surplus"] == "500"
    assert Decimal(purchase["consumed_ingredient_cost"]) == Decimal("10.00")
    assert evaluation["disbursement"] == "20.00"
    assert evaluation["remaining_budget"] == "60.00"
    arrange(p)
    assert [Decimal(c["cmv_production"]) for c in finish(p)] == [Decimal("4.00"), Decimal("6.00")]
    assert (
        p["service"].get_inventory_snapshot({"workspace_id": p["workspace"]})["data"]
        == p["original"]
    )


def test_order_changes_cost_by_origin_and_removal_leaves_no_phantom_spend(shared_plan):
    p = shared_plan()
    set_plan(p)
    arrange(p)
    calculations = finish(p)
    assert [Decimal(c["cmv_production"]) for c in calculations] == [
        Decimal("19.92"),
        Decimal("16.98"),
    ]
    assert [[a["quantity"] for a in c["allocations"]] for c in calculations] == [
        ["4000"],
        ["1000", "2000"],
    ]
    assert [[a["origin"] for a in c["allocations"]] for c in calculations] == [
        ["INVENTORY"],
        ["INVENTORY", "QUOTE"],
    ]
    current = state(p)
    assert len(current["menu"]) == 2
    assert current["evaluation"]["demand"][0]["shortage"] == "2000"
    assert current["budget_remaining"] == "50.00"
    old_acceptances = {a["id"] for a in current["acceptances"]}
    reordered = set_plan(p, order=(1, 0))
    assert set(reordered["invalidated_decisions"]) == old_acceptances
    assert state(p)["menu"] == []
    assert all(c["validity"] == "INVALIDATED" for c in state(p)["pricing_calculations"])
    arrange(p)
    recalculated = finish(p)
    assert [Decimal(c["cmv_production"]) for c in recalculated] == [
        Decimal("14.94"),
        Decimal("21.96"),
    ]
    assert sum(Decimal(c["cmv_production"]) for c in recalculated) == Decimal("36.90")
    assert state(p)["budget_remaining"] == "50.00"
    removed = set_plan(p, order=(0,))
    assert removed["summary"]["disbursement"] == "0.00"
    assert removed["summary"]["remaining_budget"] == "80.00"
    assert removed["summary"]["demand"][0]["purchase"]["packages"] == 0
    assert state(p)["menu"] == []
    assert Decimal(finish(p)[0]["cmv_production"]) == Decimal("19.92")
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(p["database"]))
    assert reopened.get_business_state({"workspace_id": p["workspace"]})["data"] == state(p)
    assert (
        p["service"].get_inventory_snapshot({"workspace_id": p["workspace"]})["data"]
        == p["original"]
    )


def test_plan_summary_exposes_normalized_consumption_in_explicit_order(shared_plan):
    p = shared_plan()
    result = set_plan(p, order=(1, 0), batches=2)
    rows = result["summary"]["consumption_by_recipe"]
    assert [r["recipe_id"] for r in rows] == [p["recipes"][1]["id"], p["recipes"][0]["id"]]
    assert [r["position"] for r in rows] == [0, 1]
    assert [r["plan_item_id"] for r in rows] == [i["plan_item_id"] for i in result["plan"]["items"]]
    assert [r["ingredients"] for r in rows] == [
        [dict(ingredient_id=p["quote"]["ingredient_id"], unit="g", required="6000")],
        [dict(ingredient_id=p["quote"]["ingredient_id"], unit="g", required="8000")],
    ]


@pytest.mark.parametrize("change", ["include", "scale", "clear"])
def test_each_plan_change_invalidates_previous_decisions_without_resurrection(shared_plan, change):
    p = shared_plan()
    set_plan(p, order=(0,))
    finish(p)
    old = state(p)
    result = set_plan(
        p,
        order=(0, 1) if change == "include" else () if change == "clear" else (0,),
        batches=2 if change == "scale" else 1,
    )
    assert result["invalidated_decisions"] == [old["acceptances"][0]["id"]]
    current = state(p)
    assert current["menu"] == []
    assert current["acceptances"][0]["validity"] == "INVALIDATED"
    assert current["menu_decisions"][0]["validity"] == "INVALIDATED"
    denied = p["command"](
        "calculate_pricing_scenarios",
        recipe_id=p["recipes"][0]["id"],
        acceptance_id=old["acceptances"][0]["id"],
    )
    assert denied["error"]["code"] == "STALE_EVALUATION"
    assert state(p) == current
    set_plan(p, order=(0,))
    assert state(p)["menu"] == []
    assert state(p)["acceptances"][0]["validity"] == "INVALIDATED"


@pytest.mark.parametrize(
    "amounts,arranged,code",
    [
        (("4000", "3000"), False, "MISSING_INFORMATION"),
        (("10000", "10000"), True, "BUDGET_EXCEEDED"),
    ],
)
def test_unresolved_global_draft_prevents_acceptance_of_either_dish(
    shared_plan, amounts, arranged, code
):
    p = shared_plan(amounts=amounts)
    set_plan(p)
    if arranged:
        arrange(p)
    before = state(p)
    for item in before["plan"]["items"]:
        result = p["command"](
            "accept_recipe",
            recipe_id=item["recipe_id"],
            plan_item_id=item["plan_item_id"],
            evaluation_id=before["evaluation"]["evaluation_id"],
            evidence=p["evidence"] | {"statement": "Aceito este prato."},
        )
        assert result["error"]["code"] == code
        assert state(p) == before


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(a=st.integers(1, 6000), b=st.integers(1, 6000), scale=st.integers(1, 3))
def test_prop001_002_003_conservation_minimum_packages_and_monotonicity(shared_plan, a, b, scale):
    p = shared_plan(amounts=(str(a), str(b)), extra="7.00")
    first = set_plan(p)["summary"]
    arrange(p)
    costs = finish(p)
    (line,) = first["demand"]
    purchase = line["purchase"]
    allocations = [allocation for cost in costs for allocation in cost["allocations"]]
    inventory = sum(
        (Decimal(x["quantity"]) for x in allocations if x["origin"] == "INVENTORY"), Decimal("0")
    )
    complement = sum(
        (Decimal(x["quantity"]) for x in allocations if x["origin"] == "QUOTE"), Decimal("0")
    )
    assert inventory + complement == Decimal(line["required"])
    assert all(Decimal(x["quantity"]) > 0 for x in allocations)
    assert inventory <= Decimal(line["stock_available"])
    assert complement <= Decimal(purchase["purchased_quantity"])
    assert Decimal(purchase["planned_surplus"]) >= 0
    if purchase["packages"]:
        assert purchase["packages"] * 5000 >= Decimal(line["shortage"])
        assert (purchase["packages"] - 1) * 5000 < Decimal(line["shortage"])
        assert Decimal(purchase["planned_surplus"]) < 5000
    reordered = set_plan(p, order=(1, 0))["summary"]
    arrange(p)
    recosted = finish(p)
    assert reordered["demand"] == first["demand"]
    assert reordered["disbursement"] == first["disbursement"]
    assert sum(Decimal(c["cmv_production"]) for c in costs) == sum(
        Decimal(c["cmv_production"]) for c in recosted
    )
    # A escala cresce com as mesmas ofertas, encargos e capacidade de confirmação.
    increased = set_plan(p, batches=scale)["summary"]
    assert increased["demand"][0]["purchase"]["packages"] >= purchase["packages"]
    assert Decimal(increased["disbursement"]) >= Decimal(first["disbursement"])


def test_sequential_dishes_require_total_time_and_cannot_be_accepted_in_isolation(shared_plan):
    p = shared_plan(minutes=(30, 40))
    set_plan(p)
    arrange(p)
    for available, status in [("60", "BLOCKED"), ("70", "ELIGIBLE")]:
        previous = next((f for f in state(p)["kitchen_facts"] if f["key"] == "time"), None)
        assert p["command"](
            "record_kitchen_facts",
            facts=[
                dict(
                    category="OPERATION",
                    key="time",
                    value=available,
                    unit="min",
                    replaces_fact_id=previous["id"] if previous else None,
                    evidence=p["evidence"] | {"statement": f"Tenho {available} minutos no total."},
                )
            ],
        )["ok"]
        before = state(p)
        assert [f["status"] for f in before["evaluation"]["feasibility_by_recipe"]] == [
            status,
            status,
        ]
        if status == "BLOCKED":
            for item in before["plan"]["items"]:
                result = p["command"](
                    "accept_recipe",
                    recipe_id=item["recipe_id"],
                    plan_item_id=item["plan_item_id"],
                    evaluation_id=before["evaluation"]["evaluation_id"],
                    evidence=p["evidence"] | {"statement": "Aceito este prato."},
                )
                assert result["error"]["code"] == "CONSTRAINT_BLOCKED"
                assert state(p) == before
    assert len(finish(p)) == 2
