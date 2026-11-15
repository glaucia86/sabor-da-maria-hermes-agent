"""S18: disponibilidade não atesta aquisição nem CMV completo."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from conftest import pricing_evidence
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openpyxl import load_workbook
from pydantic import ValidationError

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.business_state import AttendanceService, BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.planning import BusinessRuleError


def propose_acquisition(reader, workspace, local, **changes):
    ingredient = reader.get_inventory_snapshot({"workspace_id": workspace})["data"]["items"][0]
    payload = (
        dict(
            ingredient_id=ingredient["id"],
            available_quantity={"value": "500", "unit": "g"},
            acquired_quantity={"value": "1000", "unit": "g"},
            acquisition_total="20.00",
            basis="HISTORICAL_ACQUISITION",
            context="Relato sintético: comprei 1 kg por R$20; restam 500g dessa aquisição.",
        )
        | changes
    )
    return local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=reader.get_business_state({"workspace_id": workspace})["revision"],
            command={"kind": "record_inventory_acquisition", "payload": payload},
        )
    )


def local_decision(reader, workspace, local, kind, **payload):
    proposal = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=reader.get_business_state({"workspace_id": workspace})["revision"],
            command={"kind": kind, "payload": payload},
        )
    )
    return local.approve(workspace, proposal["id"], proposal["hash"], attest=True)


def test_available_stock_without_historical_cost_remains_operational_but_blocks_acceptance(
    pricing_workspace,
):
    reader, workspace, recipe, _, command, _ = pricing_workspace(total=None, accept=False)
    evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["feasibility_by_recipe"][0]["status"] == "ELIGIBLE"
    assert evaluation["purchase_status"] == "CONFIRMED"
    assert evaluation["disbursement"] == "0.00"
    line = evaluation["demand"][0]
    assert line["stock_available"] == "5000"
    assert line["shortage"] == "0"
    assert evaluation["financial_readiness"]["status"] == "PENDING"
    gap = evaluation["financial_readiness"]["gaps"][0]
    assert gap["ingredient_id"] == line["ingredient_id"]
    assert gap["quantity"] == "100"
    assert gap["origin"] == "INVENTORY"
    assert line["historical_consumed_cost"] is None
    assert "não sabemos quanto custou" in gap["message"]
    state = reader.get_business_state({"workspace_id": workspace})["data"]
    assert state["candidates"][0]["status"] == "FINANCIAL_PENDING"
    refused = command(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=state["plan"]["items"][0]["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
        evidence=pricing_evidence("Aceito este prato."),
    )
    assert refused["error"]["code"] == "FINANCIAL_INCOMPLETE"
    assert reader.get_business_state({"workspace_id": workspace})["data"]["acceptances"] == []


def test_reported_acquisition_needs_local_approval_and_keeps_original_snapshot(
    pricing_workspace,
    tmp_path,
):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    original = reader.get_inventory_snapshot({"workspace_id": workspace})
    migrate_proposals(reader.repository, tmp_path / "backup.sqlite3")
    local = ApprovalService(reader.repository, clock=reader.clock)
    proposal = propose_acquisition(reader, workspace, local)
    assert (
        reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]["financial_readiness"][
            "status"
        ]
        == "PENDING"
    )
    with pytest.raises(BusinessRuleError, match="Ateste"):
        local.approve(workspace, proposal["id"], proposal["hash"], attest=False)
    approved = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert approved["ok"]
    acquisition = approved["data"]["acquisition"]
    assert acquisition["version"] == 1
    assert acquisition["sources"]["acquisition_total"]["kind"] == "USER_PROVIDED"
    assert acquisition["sources"]["acquisition_total"]["local_event_id"]
    evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["financial_readiness"]["status"] == "READY"
    assert evaluation["demand"][0]["stock_available"] == "500"
    assert evaluation["demand"][0]["historical_consumed_cost"] == "2.00"
    assert reader.get_inventory_snapshot({"workspace_id": workspace})["data"] == original["data"]
    assert local.approve(workspace, proposal["id"], proposal["hash"], attest=True) == approved


def test_material_acquisition_change_invalidates_prices_and_reprices_from_reported_origin(
    pricing_workspace,
    reconfirm_attendance,
):
    reader, workspace, recipe, _, command, database = pricing_workspace()
    decide = reconfirm_attendance(reader, workspace, database)
    state = reader.get_business_state({"workspace_id": workspace})["data"]
    acceptance = state["acceptances"][-1]
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    decide(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
    )
    local = ApprovalService(reader.repository, clock=reader.clock)
    proposal = propose_acquisition(reader, workspace, local)
    changed = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert acceptance["id"] in changed["data"]["invalidated_decisions"]
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database), clock=reader.clock)
    current = reopened.get_business_state({"workspace_id": workspace})["data"]
    assert current["menu"] == []
    assert current["pricing_calculations"][-1]["validity"] == "INVALIDATED"
    assert len(current["menu_decisions"]) == 1
    evaluation = current["evaluation"]
    accepted = decide(
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=current["plan"]["items"][0]["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
    )["data"]["acceptance"]
    result = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=accepted["id"]
    )
    assert result["ok"], result
    calculated = result["data"]["calculation"]
    assert calculated["cmv_production"] == "2.00"
    allocation = calculated["allocations"][0]
    assert allocation["origin"] == "REPORTED_ACQUISITION"
    assert allocation["source_id"] == changed["data"]["acquisition"]["id"]
    assert allocation["purchase_quantity_base"] == "1000"
    assert reopened.get_business_state({"workspace_id": workspace})["ok"]
    missing = propose_acquisition(
        reader,
        workspace,
        local,
        acquisition_total=None,
        acquisition_gap="Valor pago ainda não sustentado.",
        replaces_acquisition_id=changed["data"]["acquisition"]["id"],
    )
    removed = local.approve(workspace, missing["id"], missing["hash"], attest=True)
    blocked = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=accepted["id"]
    )
    assert blocked["error"]["code"] == "FINANCIAL_INCOMPLETE"
    restored = propose_acquisition(
        reader,
        workspace,
        local,
        replaces_acquisition_id=removed["data"]["acquisition"]["id"],
    )
    local.approve(workspace, restored["id"], restored["hash"], attest=True)
    final = reopened.get_business_state({"workspace_id": workspace})["data"]
    assert final["menu"] == []
    assert all(a["validity"] == "INVALIDATED" for a in final["acceptances"])
    assert len(final["inventory_acquisitions"]) == 3
    assert len(final["pricing_calculations"]) == 2


def test_water_in_food_requires_cost_while_cleaning_water_is_explicitly_external(
    pricing_workspace,
    inventory_file,
    recipe_candidate,
    tmp_path,
):
    book = load_workbook(inventory_file)
    book["Despensa"]["A2"] = book["Precos"]["A2"] = "Água"
    book["Despensa"]["C2"] = "L"
    book.save(inventory_file)
    book.close()
    recipe_candidate["ingredients"][0]["description"] = "Água incorporada ao alimento"
    measure = recipe_candidate["ingredients"][0]["original_measure"]
    measure.update(raw_text="100ml de água incorporada", unit_label="ml")
    reader, workspace, recipe, _, command, _ = pricing_workspace(
        total=None, accept=False, unit="ml"
    )
    migrate_proposals(reader.repository, tmp_path / "water-backup.sqlite3")
    local = ApprovalService(reader.repository, clock=reader.clock)
    proposal = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=reader.get_business_state({"workspace_id": workspace})["revision"],
            command={
                "kind": "record_operational_resource",
                "payload": dict(
                    recipe_id=recipe["id"],
                    recipe_version=1,
                    resource_name="Água",
                    purpose="Lavagem dos utensílios, sem incorporar ao alimento.",
                    classification="EXTERNAL_OPERATIONAL_RESOURCE",
                    quantity={"value": "2", "unit": "L"},
                    cost_gap="Conta não disponível; custo de limpeza desconhecido.",
                    context="Atividade externa para esta produção sintética.",
                ),
            },
        )
    )
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["financial_readiness"]["status"] == "PENDING"
    assert evaluation["financial_readiness"]["net_profit_complete"] is False
    assert evaluation["demand"][0]["required"] == "100"
    resource = evaluation["operational_resources"][0]
    assert resource["resource_name"] == "Água"
    assert resource["included_in_ingredient_cmv"] is False
    assert resource["cost"] is None
    assert resource["sources"]["purpose"]["local_event_id"]
    assert "lucro líquido" in evaluation["financial_readiness"]["explanation"]
    acquisition = propose_acquisition(
        reader,
        workspace,
        local,
        available_quantity={"value": "500", "unit": "ml"},
        acquired_quantity={"value": "1000", "unit": "ml"},
        context="Água incorporada: aquisição de 1L por R$20, com 500ml disponíveis.",
    )
    local.approve(workspace, acquisition["id"], acquisition["hash"], attest=True)
    local_decision(
        reader,
        workspace,
        local,
        "record_recipe_feedback",
        recipe_id=recipe["id"],
        feedback="INTERESTED",
    )
    plan = local_decision(
        reader,
        workspace,
        local,
        "set_production_plan",
        items=[
            dict(
                recipe_id=recipe["id"],
                recipe_version=1,
                position=0,
                batches=1,
            )
        ],
    )["data"]["plan"]
    evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    assert evaluation["financial_readiness"]["status"] == "READY"
    assert evaluation["financial_readiness"]["net_profit_complete"] is False
    acceptance = local_decision(
        reader,
        workspace,
        local,
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=plan["items"][0]["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
    )["data"]["acceptance"]
    calculated = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    assert calculated["ok"], calculated
    calculation = calculated["data"]["calculation"]
    assert calculation["cmv_production"] == "2.00"
    assert calculation["allocations"][0]["quantity"] == "100"
    assert calculation["allocations"][0]["unit"] == "ml"
    assert len(calculation["allocations"]) == 1
    assert any("não é lucro líquido" in text for text in calculation["explanation"])


def test_attendance_explains_missing_cost_and_can_revise_report_by_local_reference(
    pricing_workspace,
    tmp_path,
):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    migrate_proposals(reader.repository, tmp_path / "attendance-backup.sqlite3")
    local = ApprovalService(reader.repository)
    attendance = AttendanceService(database, workspace, "ATTENDANCE")
    projected = attendance.call("evaluate_purchase_plan", {})
    assert projected["ok"], projected
    readiness = projected["data"]["financial_readiness"]
    assert readiness["status"] == "PENDING"
    assert readiness["gaps"][0]["ingredient"] == 1
    assert "não sabemos quanto custou" in readiness["gaps"][0]["message"]
    initial = propose_acquisition(reader, workspace, local)
    local.approve(workspace, initial["id"], initial["hash"], attest=True)
    state = attendance.call("get_business_state", {})["data"]
    assert state["inventory_acquisitions"][0]["acquisition"] == 1
    inventory = attendance.call("get_inventory_snapshot", {})["data"]
    assert inventory["items"][0]["available_quantity"] == {"value": "500", "unit": "g"}
    assert inventory["items"][0]["unit_cost"] == "0.02"
    changed = attendance.call(
        "propose_user_change",
        dict(
            operation_id=str(uuid4()),
            command={
                "kind": "record_inventory_acquisition",
                "payload": dict(
                    ingredient_id=1,
                    available_quantity={"value": "500", "unit": "g"},
                    acquired_quantity={"value": "1000", "unit": "g"},
                    acquisition_total="30.00",
                    basis="HISTORICAL_ACQUISITION",
                    context="Correção humana da mesma aquisição.",
                    replaces_acquisition_id=1,
                ),
            },
        ),
    )
    assert changed["ok"], changed
    proposal = local.list(workspace)[-1]
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert (
        reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]["demand"][0][
            "historical_consumed_cost"
        ]
        == "3.00"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"basis": "CURRENT_REPLACEMENT"},
        {"acquisition_total": 20.0},
        {"acquisition_total": "0"},
        {"acquisition_total": None},
        {"acquired_quantity": None},
        {"context": " "},
        {"acquired_quantity": {"value": "1", "unit": "L"}},
        {"ingredient_id": str(uuid4())},
    ],
)
def test_unsubstantiated_or_foreign_acquisition_never_mutates_business(
    pricing_workspace,
    tmp_path,
    changes,
):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    migrate_proposals(reader.repository, tmp_path / "invalid-backup.sqlite3")
    before = reader.get_business_state({"workspace_id": workspace})
    with pytest.raises((BusinessRuleError, ValidationError)):
        propose_acquisition(reader, workspace, ApprovalService(reader.repository), **changes)
    assert reader.get_business_state({"workspace_id": workspace}) == before


def test_reported_acquisition_refuses_direct_write_even_without_s14_migration(pricing_workspace):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    before = database.read_bytes()
    stock = reader.get_inventory_snapshot({"workspace_id": workspace})["data"]["items"][0]
    result = reader.record_inventory_acquisition(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=reader.get_business_state({"workspace_id": workspace})["revision"],
            ingredient_id=stock["id"],
            available_quantity={"value": "500", "unit": "g"},
            acquired_quantity={"value": "1000", "unit": "g"},
            acquisition_total="20.00",
            basis="HISTORICAL_ACQUISITION",
            context="Declaração não atestada pelo operador.",
            evidence=pricing_evidence("Paguei vinte reais por mil gramas."),
        )
    )
    assert result["error"]["code"] == "AUTHORIZATION_REQUIRED"
    assert database.read_bytes() == before


def test_reported_stock_and_shared_complement_keep_one_disbursement_and_cost_each_origin(
    shared_plan,
    tmp_path,
):
    p = shared_plan(amounts=("400", "300"), complement=True)
    reader, workspace = p["service"], p["workspace"]
    migrate_proposals(reader.repository, tmp_path / "shared-backup.sqlite3")
    local = ApprovalService(reader.repository)
    reported = propose_acquisition(
        reader, workspace, local, ingredient_id=p["quote"]["ingredient_id"]
    )
    local.approve(workspace, reported["id"], reported["hash"], attest=True)
    resolved = local_decision(
        reader,
        workspace,
        local,
        "resolve_recipe_ingredient",
        recipe_id=p["recipes"][0]["id"],
        recipe_version=p["recipes"][0]["version"],
        line_id=p["recipes"][0]["ingredients"][0]["line_id"],
        existing_ingredient_id=p["quote"]["ingredient_id"],
    )
    p["recipes"][0] = resolved["data"]["candidate"]
    for recipe in p["recipes"]:
        local_decision(
            reader,
            workspace,
            local,
            "record_recipe_feedback",
            recipe_id=recipe["id"],
            feedback="INTERESTED",
        )
    quote = p["quote"]
    local_decision(
        reader,
        workspace,
        local,
        "confirm_complement_quote",
        quote_id=quote["id"],
        quote_version=1,
        scope=dict(
            package_quantity=quote["package_quantity"],
            package_price="20.00",
            purchase_extra_total="0.00",
            extra_conditions=quote["extra_conditions"],
            availability_context=quote["availability_context"],
            supplier=quote["supplier"],
            packages=1,
        ),
    )
    for order, expected in [((0, 1), ["8.00", "6.00"]), ((1, 0), ["6.00", "8.00"])]:
        planned = local_decision(
            reader,
            workspace,
            local,
            "set_production_plan",
            items=[
                dict(
                    recipe_id=p["recipes"][i]["id"],
                    recipe_version=p["recipes"][i]["version"],
                    position=position,
                    batches=1,
                )
                for position, i in enumerate(order)
            ],
            quote_selections=[
                dict(ingredient_id=quote["ingredient_id"], quote_id=quote["id"], quote_version=1)
            ],
        )
        state = reader.get_business_state({"workspace_id": workspace})["data"]
        prior = next(
            (f for f in state["kitchen_facts"] if f["key"] == "production_arrangement"), None
        )
        plan = planned["data"]["plan"]
        local_decision(
            reader,
            workspace,
            local,
            "record_kitchen_facts",
            facts=[
                dict(
                    category="OPERATION",
                    key="production_arrangement",
                    value="SEQUENTIAL",
                    context=f"{plan['id']}:{plan['version']}",
                    replaces_fact_id=prior["id"] if prior else None,
                )
            ],
        )
        evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
        assert evaluation["financial_readiness"]["status"] == "READY"
        assert evaluation["disbursement"] == "20.00"
        assert evaluation["demand"][0]["purchase"]["packages"] == 1
        assert evaluation["demand"][0]["purchase"]["planned_surplus"] == "800"
        costs = []
        for item in plan["items"]:
            evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
            accepted = local_decision(
                reader,
                workspace,
                local,
                "accept_recipe",
                recipe_id=item["recipe_id"],
                plan_item_id=item["plan_item_id"],
                evaluation_id=evaluation["evaluation_id"],
            )["data"]["acceptance"]
            result = p["command"](
                "calculate_pricing_scenarios",
                recipe_id=item["recipe_id"],
                acceptance_id=accepted["id"],
            )
            assert result["ok"], result
            costs.append(result["data"]["calculation"]["cmv_production"])
        assert costs == expected
    assert reader.get_inventory_snapshot({"workspace_id": workspace})["data"] == p["original"]
    assert BusinessStateReader(SQLiteWorkspaceRepository(p["database"])).get_business_state(
        {"workspace_id": workspace}
    )["ok"]


def test_concurrent_financial_reviews_have_one_winner_and_replay_is_read_only(
    pricing_workspace,
    tmp_path,
):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    migrate_proposals(reader.repository, tmp_path / "concurrency-backup.sqlite3")
    local = ApprovalService(reader.repository)
    proposals = [
        propose_acquisition(reader, workspace, local, acquisition_total=price)
        for price in ("20.00", "30.00")
    ]

    def approve(proposal):
        try:
            return local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
        except BusinessRuleError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, proposals))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "STALE_REVISION" in results
    winner = next(i for i, result in enumerate(results) if isinstance(result, dict))
    before = database.read_bytes()
    assert approve(proposals[winner]) == results[winner]
    assert database.read_bytes() == before
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    state = reopened.get_business_state({"workspace_id": workspace})["data"]
    assert len(state["inventory_acquisitions"]) == 1
    assert state["evaluation"]["financial_readiness"]["status"] == "READY"


def test_failed_financial_transaction_rolls_back_and_preserves_pending_proposal(
    pricing_workspace,
    tmp_path,
):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    migrate_proposals(reader.repository, tmp_path / "rollback-backup.sqlite3")
    local = ApprovalService(reader.repository)
    proposal = propose_acquisition(reader, workspace, local)
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TRIGGER synthetic_failure BEFORE INSERT ON decisions "
            "WHEN NEW.kind='RECORD_INVENTORY_ACQUISITION' "
            "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    before = reader.get_business_state({"workspace_id": workspace})
    with pytest.raises(sqlite3.DatabaseError, match="synthetic failure"):
        local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert reader.get_business_state({"workspace_id": workspace}) == before
    assert local.inspect(workspace, proposal["id"])["status"] == "PENDING"
    with sqlite3.connect(database) as db:
        db.execute("DROP TRIGGER synthetic_failure")
    assert local.approve(workspace, proposal["id"], proposal["hash"], attest=True)["ok"]


@pytest.mark.parametrize("corruption", ["foreign", "scope", "missing_version"])
def test_invalid_financial_provenance_is_preserved_and_refused_on_reopening(
    pricing_workspace,
    tmp_path,
    corruption,
):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    migrate_proposals(reader.repository, tmp_path / "corruption-backup.sqlite3")
    local = ApprovalService(reader.repository)
    proposal = propose_acquisition(reader, workspace, local)
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    with sqlite3.connect(database) as db:
        state = json.loads(
            db.execute("SELECT state_json FROM workspaces WHERE id=?", (workspace,)).fetchone()[0]
        )
        if corruption == "foreign":
            state["inventory_acquisitions"][0]["workspace_id"] = str(uuid4())
        elif corruption == "scope":
            state["inventory_acquisitions"][0]["sources"]["acquisition_total"]["information_ref"][
                "field"
            ] = "available_quantity"
        else:
            state.pop("financial_data_version")
        db.execute("UPDATE workspaces SET state_json=? WHERE id=?", (json.dumps(state), workspace))
    before = database.read_bytes()
    result = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert database.read_bytes() == before


@settings(
    max_examples=8, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(available=st.integers(min_value=500, max_value=1000))
def test_availability_does_not_change_the_purchase_denominator(
    pricing_workspace, tmp_path, available
):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    migrate_proposals(reader.repository, tmp_path / f"property-backup-{uuid4()}.sqlite3")
    local = ApprovalService(reader.repository)
    proposal = propose_acquisition(
        reader, workspace, local, available_quantity={"value": str(available), "unit": "g"}
    )
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    # Exemplo independente: 100g consumidos de uma aquisição de 1000g por R$20 custam R$2.
    assert evaluation["demand"][0]["historical_consumed_cost"] == "2.00"
    assert evaluation["financial_readiness"]["status"] == "READY"
    assert evaluation["disbursement"] == "0.00"


def test_reported_base_quantity_composes_with_existing_historical_conversion(
    clarification, tmp_path
):
    reader, workspace, command, candidate, chocolate, _, _, _ = clarification
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    command(
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=1, position=0, batches=1)],
        evidence=pricing_evidence("Confirmo esta produção."),
    )
    converted = command(
        "record_ingredient_conversion",
        ingredient_id=chocolate["id"],
        from_unit="un",
        to_unit="g",
        factor="1000",
        context="Embalagem histórica desta fotografia.",
        scope="HISTORICAL_PACKAGE",
        evidence=pricing_evidence("Confirmo que a embalagem comprada contém 1000g."),
    )
    assert converted["ok"], converted
    migrate_proposals(reader.repository, tmp_path / "conversion-backup.sqlite3")
    local = ApprovalService(reader.repository)
    proposal = propose_acquisition(reader, workspace, local, ingredient_id=chocolate["id"])
    approved = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    line = next(line for line in evaluation["demand"] if line["ingredient_id"] == chocolate["id"])
    assert line["stock_available"] == "500"
    assert line["unit"] == "g"
    assert line["historical_consumed_cost"] == "2.00"
    incompatible = propose_acquisition(
        reader,
        workspace,
        local,
        ingredient_id=chocolate["id"],
        available_quantity={"value": "1", "unit": "un"},
        acquired_quantity={"value": "1", "unit": "un"},
        replaces_acquisition_id=approved["data"]["acquisition"]["id"],
    )
    with pytest.raises(BusinessRuleError) as refused:
        local.approve(workspace, incompatible["id"], incompatible["hash"], attest=True)
    assert refused.value.code == "UNIT_CONVERSION_REQUIRED"


def test_attendance_inventory_uses_the_historical_conversion_before_acquisition(clarification):
    reader, workspace, command, _, chocolate, _, _, database = clarification
    converted = command(
        "record_ingredient_conversion",
        ingredient_id=chocolate["id"],
        from_unit="un",
        to_unit="g",
        factor="1000",
        context="Embalagem histórica desta fotografia.",
        scope="HISTORICAL_PACKAGE",
        evidence=pricing_evidence("Confirmo que a embalagem comprada contém 1000g."),
    )
    assert converted["ok"], converted
    original = reader.get_inventory_snapshot({"workspace_id": workspace})
    projected = AttendanceService(database, workspace, "ATTENDANCE").call(
        "get_inventory_snapshot", {"ingredients": [2]}
    )
    assert projected["ok"], projected
    item = projected["data"]["items"][0]
    assert item["available_quantity"] == {"value": "1000", "unit": "g"}
    assert item["unit_cost"] == "0.0799"
    assert reader.get_inventory_snapshot({"workspace_id": workspace}) == original


def test_operational_resource_purpose_can_be_corrected_without_leaving_two_current_uses(
    pricing_workspace,
    tmp_path,
):
    reader, workspace, recipe, _, _, database = pricing_workspace(accept=False)
    migrate_proposals(reader.repository, tmp_path / "resource-backup.sqlite3")
    local = ApprovalService(reader.repository)
    payload = dict(
        recipe_id=recipe["id"],
        recipe_version=1,
        resource_name="Água",
        purpose="Limpeza dos utensílios.",
        classification="EXTERNAL_OPERATIONAL_RESOURCE",
        quantity={"value": "2", "unit": "L"},
        cost_gap="Conta não informada.",
        context="Atividade externa.",
    )
    first = local_decision(reader, workspace, local, "record_operational_resource", **payload)[
        "data"
    ]["operational_resource"]
    changed = local_decision(
        reader,
        workspace,
        local,
        "record_operational_resource",
        **(
            payload
            | dict(
                purpose="Limpeza da bancada.",
                replaces_resource_id=first["id"],
            )
        ),
    )["data"]["operational_resource"]
    assert changed["version"] == 2
    state = reader.get_business_state({"workspace_id": workspace})["data"]
    assert len(state["operational_resources"]) == 2
    assert len(state["evaluation"]["operational_resources"]) == 1
    assert state["evaluation"]["operational_resources"][0]["purpose"] == "Limpeza da bancada."
