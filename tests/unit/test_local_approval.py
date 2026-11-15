"""S14: propostas e atestação local, com SQLite exclusivamente temporário."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import AttendanceService, BusinessStateReader
from dona_maria.candidates import CandidateInput
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.planning import BusinessRuleError


@pytest.fixture
def approval_workspace(tmp_path, inventory_file):
    database = tmp_path / "approval.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "before-s14.sqlite3")
    clock = [datetime(2026, 11, 14, 12, tzinfo=UTC)]
    service = ApprovalService(repository, clock=lambda: clock[0])
    return service, workspace, database, clock


def business_rows(database):
    # Inspeção de segurança solicitada: ausência de efeitos nas tabelas de negócio.
    with sqlite3.connect(database) as db:
        return {
            table: db.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("workspaces", "inventory_snapshots", "decisions", "operations")
        }


def fact_proposal(service, workspace, **changes):
    request = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=0,
        command={
            "kind": "record_kitchen_facts",
            "payload": {"facts": [{"category": "EQUIPMENT", "key": "stove", "value": True}]},
        },
    )
    request.update(changes)
    return service.propose(request)


def test_proposal_is_persistent_but_does_not_confirm_any_business_fact(approval_workspace):
    service, workspace, database, clock = approval_workspace
    before = business_rows(database)

    proposal = fact_proposal(service, workspace)

    assert proposal["status"] == "PENDING"
    assert proposal["expires_at"] == "2026-11-14T12:10:00+00:00"
    assert len(proposal["hash"]) == 64
    assert proposal["expected_revision"] == 0
    assert "stove" in proposal["summary"]
    assert service.inspect(workspace, proposal["id"]) == proposal
    assert business_rows(database) == before


@pytest.mark.parametrize("legacy_term", ["comida  caseira", "ｃｏｍｉｄａ　ｃａｓｅｉｒａ"])
def test_reconfirmed_equivalent_preference_no_longer_requires_legacy_review(
    tmp_path, inventory_file, legacy_term
):
    database = tmp_path / "preference.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    saved = reader.record_user_preferences(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=0,
            preferences=[
                dict(
                    category="OTHER",
                    term=legacy_term,
                    value="LIKE",
                    evidence=dict(
                        turn_ref="legacy-preference",
                        statement="Prefiro comida caseira",
                        captured_at="2026-11-14T12:00:00Z",
                    ),
                )
            ],
        )
    )
    assert saved["ok"], saved
    migrate_proposals(reader.repository, tmp_path / "before-preference.sqlite3")
    public = AttendanceService(database, workspace, "ATTENDANCE")
    assert public.call("get_business_state", {})["data"]["requires_local_review"]
    local = ApprovalService(reader.repository)
    local.propose_bound(
        workspace,
        dict(
            operation_id=str(uuid4()),
            command=dict(
                kind="record_user_preferences",
                payload=dict(
                    preferences=[
                        dict(
                            category="OTHER",
                            term="comida caseira",
                            value="LIKE",
                            replaces_preference_id=1,
                        )
                    ]
                ),
            ),
        ),
    )
    proposal = local.list(workspace)[0]
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)

    current = public.call("get_business_state", {})["data"]
    assert current["preferences"] == [
        {"category": "OTHER", "term": "comida caseira", "value": "LIKE"}
    ]
    assert current["pending_preferences"] == []
    assert current["requires_local_review"] is False
    history = reader.get_business_state({"workspace_id": workspace})["data"]["preferences"]
    assert [p["term"] for p in history] == [legacy_term, "comida caseira"]


def test_exact_local_attestation_applies_once_and_replay_survives_restart(approval_workspace):
    service, workspace, database, clock = approval_workspace
    proposal = fact_proposal(service, workspace)

    result = service.approve(workspace, proposal["id"], proposal["hash"], attest=True)

    assert result["ok"] is True
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    state = reader.get_business_state({"workspace_id": workspace})
    assert state["revision"] == 1
    fact = state["data"]["kitchen_facts"][0]
    assert (fact["key"], fact["value"]) == ("stove", True)
    assert fact["evidence"]["turn_ref"].startswith("local:")
    assert fact["evidence"]["captured_at"] == "2026-11-14T12:00:00Z"
    after = business_rows(database)
    restarted = ApprovalService(SQLiteWorkspaceRepository(database), clock=lambda: clock[0])
    assert restarted.approve(workspace, proposal["id"], proposal["hash"], attest=True) == result
    assert business_rows(database) == after
    assert restarted.inspect(workspace, proposal["id"])["status"] == "APPROVED"


@pytest.mark.parametrize(
    "attack", ["expiry", "early", "hash", "revision", "payload", "context", "attestation"]
)
def test_approval_rejects_changed_or_unattested_scope_without_any_partial_effect(
    approval_workspace, attack
):
    service, workspace, database, clock = approval_workspace
    proposal = fact_proposal(service, workspace)
    target, digest, attest = workspace, proposal["hash"], True
    if attack == "expiry":
        clock[0] += timedelta(minutes=10)
    elif attack == "early":
        clock[0] -= timedelta(seconds=1)
    elif attack == "hash":
        digest = "0" * 64
    elif attack == "revision":
        with sqlite3.connect(database) as db:
            db.execute("UPDATE workspaces SET revision=1")
    elif attack == "payload":
        with sqlite3.connect(database) as db:
            document = json.loads(
                db.execute("SELECT document_json FROM user_change_proposals").fetchone()[0]
            )
            document["command"]["payload"]["facts"][0]["value"] = False
            db.execute("UPDATE user_change_proposals SET document_json=?", (json.dumps(document),))
    elif attack == "context":
        target = str(uuid4())
    else:
        attest = False
    before = business_rows(database)
    with pytest.raises(BusinessRuleError):
        service.approve(target, proposal["id"], digest, attest=attest)
    assert business_rows(database) == before
    with sqlite3.connect(database) as db:
        assert db.execute(
            "SELECT status, event_json, result_json FROM user_change_proposals"
        ).fetchall() == [("PENDING", None, None)]


@pytest.mark.parametrize(
    "attack",
    ["fabricated_evidence", "unknown_command", "bool_coercion", "oversized", "nested_collection"],
)
def test_invalid_or_excessive_payload_cannot_even_persist_a_proposal(approval_workspace, attack):
    service, workspace, database, _ = approval_workspace
    command = {
        "kind": "record_kitchen_facts",
        "payload": {"facts": [{"category": "EQUIPMENT", "key": "stove", "value": True}]},
    }
    if attack == "fabricated_evidence":
        command["payload"]["facts"][0]["evidence"] = {
            "turn_ref": "local:fake",
            "statement": "Confirmado pelo modelo",
            "captured_at": "2026-11-14T12:00:00Z",
        }
    elif attack == "unknown_command":
        command["kind"] = "approve"
    elif attack == "bool_coercion":
        command["payload"]["facts"][0]["value"] = 1
    elif attack == "oversized":
        command["padding"] = "x" * (256 * 1024)
    else:
        command["payload"]["facts"] *= 201
    before = business_rows(database)
    with pytest.raises((ValidationError, BusinessRuleError)):
        fact_proposal(service, workspace, command=command)
    assert business_rows(database) == before
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM user_change_proposals").fetchone()[0] == 0


def test_preferences_feedback_plan_acceptance_and_price_each_require_an_exact_local_step(
    pricing_workspace, tmp_path
):
    reader, workspace, recipe, legacy_acceptance, _, database = pricing_workspace()
    migrate_proposals(reader.repository, tmp_path / "legacy-backup.sqlite3")
    local = ApprovalService(reader.repository, clock=reader.clock)

    def decide(kind, payload):
        before = reader.get_business_state({"workspace_id": workspace})
        proposal = local.propose(
            dict(
                workspace_id=workspace,
                operation_id=str(uuid4()),
                expected_revision=before["revision"],
                command={"kind": kind, "payload": payload},
            )
        )
        assert reader.get_business_state({"workspace_id": workspace}) == before
        return local.approve(workspace, proposal["id"], proposal["hash"], attest=True)

    decide(
        "record_user_preferences",
        {"preferences": [{"category": "OTHER", "term": "caseiro", "value": "LIKE"}]},
    )
    decide("record_recipe_feedback", {"recipe_id": recipe["id"], "feedback": "INTERESTED"})
    plan = decide(
        "set_production_plan",
        {
            "items": [
                {
                    "recipe_id": recipe["id"],
                    "recipe_version": recipe["version"],
                    "position": 0,
                    "batches": 1,
                }
            ]
        },
    )["data"]["plan"]
    evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    accepted = decide(
        "accept_recipe",
        {
            "recipe_id": recipe["id"],
            "plan_item_id": plan["items"][0]["plan_item_id"],
            "evaluation_id": evaluation["evaluation_id"],
        },
    )
    acceptance = accepted["data"]["acceptance"]
    assert acceptance["id"] != legacy_acceptance["id"]
    calculated = reader.calculate_pricing_scenarios(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=accepted["revision"],
            recipe_id=recipe["id"],
            acceptance_id=acceptance["id"],
        )
    )
    assert calculated["ok"], calculated
    calculation = calculated["data"]["calculation"]
    selected = decide(
        "save_menu_decision",
        {
            "recipe_id": recipe["id"],
            "acceptance_id": acceptance["id"],
            "calculation_id": calculation["id"],
            "scenario_id": "M20",
        },
    )
    assert selected["data"]["decision"]["price"] == "14.29"
    assert local.inspect(workspace, local.list(workspace)[-1]["id"])["status"] == "APPROVED"


def test_legacy_history_and_replay_remain_readable_but_cannot_authorize_current_decisions(
    pricing_workspace, tmp_path
):
    reader, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculated = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    calculation = calculated["data"]["calculation"]
    arguments = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=calculated["revision"],
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence={
            "turn_ref": "legacy-model-assertion",
            "statement": "Escolho M20",
            "captured_at": "2026-11-11T00:00:00Z",
        },
    )
    historical_result = reader.save_menu_decision(arguments)
    assert historical_result["ok"]
    original = business_rows(database)
    migrate_proposals(reader.repository, tmp_path / "transition-backup.sqlite3")
    assert business_rows(database) == original
    assert reader.save_menu_decision(arguments) == historical_result
    assert business_rows(database) == original

    refused = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    assert refused["ok"] is False
    assert refused["error"]["code"] == "AUTHORIZATION_REQUIRED"
    assert business_rows(database) == original
    public = AttendanceService(database, workspace, "ATTENDANCE").call("get_business_state", {})
    assert public["ok"]
    assert public["data"]["menu"] == []
    assert public["data"]["requires_local_review"] is True
    assert public["data"]["recipes"][0]["status"] == "AWAITING_LOCAL_RECONFIRMATION"


def test_model_evidence_cannot_use_a_direct_decision_path_after_migration(approval_workspace):
    service, workspace, database, _ = approval_workspace
    reader = BusinessStateReader(service.repository)
    before = business_rows(database)
    result = reader.record_kitchen_facts(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=0,
            facts=[
                {
                    "category": "EQUIPMENT",
                    "key": "stove",
                    "value": True,
                    "evidence": {
                        "turn_ref": "local:invented-by-model",
                        "statement": "Dona Maria confirmou",
                        "captured_at": "2026-11-14T12:00:00Z",
                    },
                }
            ],
        )
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "AUTHORIZATION_REQUIRED"
    assert business_rows(database) == before


def test_two_independent_connections_apply_one_decision_and_one_local_audit(approval_workspace):
    service, workspace, database, clock = approval_workspace
    proposal = fact_proposal(service, workspace)
    before = business_rows(database)

    def approve(_):
        independent = ApprovalService(SQLiteWorkspaceRepository(database), clock=lambda: clock[0])
        return independent.approve(workspace, proposal["id"], proposal["hash"], attest=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, range(2)))
    assert results[0] == results[1]
    rows = business_rows(database)
    assert len(rows["operations"]) == len(before["operations"]) + 1
    assert len(rows["decisions"]) == len(before["decisions"]) + 2
    assert rows["workspaces"][0][1] == 1


def test_failure_while_consuming_proposal_rolls_back_effect_audit_and_operation(approval_workspace):
    service, workspace, database, _ = approval_workspace
    proposal = fact_proposal(service, workspace)
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TRIGGER fail_consume BEFORE UPDATE ON user_change_proposals "
            "BEGIN SELECT RAISE(ABORT, 'synthetic failure before commit'); END"
        )
    before = business_rows(database)
    with pytest.raises(sqlite3.Error):
        service.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert business_rows(database) == before
    assert service.inspect(workspace, proposal["id"])["status"] == "PENDING"


def test_local_rejection_is_final_without_business_effect_and_is_visible_after_restart(
    approval_workspace,
):
    service, workspace, database, clock = approval_workspace
    proposal = fact_proposal(service, workspace)
    before = business_rows(database)
    rejected = service.reject(workspace, proposal["id"], proposal["hash"])
    assert rejected["status"] == "REJECTED"
    assert service.reject(workspace, proposal["id"], proposal["hash"]) == rejected
    restarted = ApprovalService(SQLiteWorkspaceRepository(database), clock=lambda: clock[0])
    assert restarted.list(workspace)[0]["status"] == "REJECTED"
    with pytest.raises(BusinessRuleError):
        restarted.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert business_rows(database) == before


@pytest.mark.parametrize(
    "kind",
    [
        "record_ingredient_conversion",
        "resolve_recipe_ingredient",
        "confirm_complement_quote",
        "register_complement_quote",
        "register_recipe_candidate",
    ],
)
def test_existing_material_changes_also_go_through_local_review(pricing_workspace, tmp_path, kind):
    reader, workspace, recipe, acceptance, command, database = pricing_workspace()
    ingredient = recipe["ingredients"][0]["ingredient_id"]
    quote_input = dict(
        ingredient_id=ingredient,
        description="Arroz sintético",
        package_quantity={"value": "1000", "unit": "g"},
        package_price="20.00",
        purchase_extra_total="0.00",
        extra_conditions="Retirada gratuita",
        availability="AVAILABLE",
        availability_context="Retirada hoje",
        max_packages=3,
        supplier="Fixture offline",
        source=recipe["sources"][0],
    )
    quote = command("register_complement_quote", quote=quote_input)["data"]["quote"]
    if kind == "record_ingredient_conversion":
        payload = dict(
            ingredient_id=ingredient,
            from_unit="g",
            to_unit="g",
            factor="1.00",
            context="Medida humana sintética",
            scope="RECIPE_MEASURE",
            recipe_id=recipe["id"],
            recipe_version=1,
            line_id=recipe["ingredients"][0]["line_id"],
        )
    elif kind == "resolve_recipe_ingredient":
        payload = dict(
            recipe_id=recipe["id"],
            recipe_version=1,
            line_id=recipe["ingredients"][0]["line_id"],
            existing_ingredient_id=ingredient,
        )
    elif kind == "confirm_complement_quote":
        payload = dict(
            quote_id=quote["id"],
            quote_version=1,
            scope={
                "package_quantity": {"value": "1000", "unit": "g"},
                "package_price": "20.00",
                "purchase_extra_total": "0.00",
                "extra_conditions": "Retirada gratuita",
                "availability_context": "Retirada hoje",
                "supplier": "Fixture offline",
                "packages": 1,
            },
        )
    elif kind == "register_complement_quote":
        payload = dict(
            quote_id=quote["id"],
            expected_quote_version=1,
            quote=quote_input | {"package_price": "21.00"},
        )
    else:
        candidate = {
            key: deepcopy(value)
            for key, value in recipe.items()
            if key in CandidateInput.model_fields
        }
        for line in candidate["ingredients"]:
            line.pop("line_id", None)
        candidate["ingredients"][0]["quantity"]["value"] = "200"
        for review in candidate["category_reviews"]:
            review["method_version"] = 2
        payload = dict(recipe_id=recipe["id"], expected_recipe_version=1, candidate=candidate)
    migrate_proposals(reader.repository, tmp_path / "before-material-change.sqlite3")
    local = ApprovalService(reader.repository, clock=reader.clock)
    before = business_rows(database)
    proposal = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=reader.get_business_state({"workspace_id": workspace})["revision"],
            command={"kind": kind, "payload": payload},
        )
    )
    assert business_rows(database) == before
    applied = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    if kind == "record_ingredient_conversion":
        assert proposal["command"]["payload"]["factor"] == "1"
    assert applied["ok"]
    assert business_rows(database)["inventory_snapshots"] == before["inventory_snapshots"]
    assert len(business_rows(database)["decisions"]) == len(before["decisions"]) + 2
    if kind in ("resolve_recipe_ingredient", "register_recipe_candidate"):
        historical = reader.get_business_state({"workspace_id": workspace})["data"]["acceptances"]
        assert any(
            a["id"] == acceptance["id"] and a["validity"] == "INVALIDATED" for a in historical
        )


def test_bound_proposals_use_numeric_references_and_local_summary_shows_the_exact_business_scope(
    pricing_workspace, tmp_path
):
    reader, workspace, recipe, _, _, database = pricing_workspace()
    migrate_proposals(reader.repository, tmp_path / "references-backup.sqlite3")
    public = AttendanceService(database, workspace, "ATTENDANCE")
    request = {
        "operation_id": str(uuid4()),
        "command": {
            "kind": "set_production_plan",
            "payload": {
                "items": [{"recipe_id": 1, "position": 0, "batches": 3, "requested_servings": 5}]
            },
        },
    }
    proposed = public.call("propose_user_change", request)
    assert proposed["ok"], proposed
    local = ApprovalService(reader.repository)
    proposal = local.list(workspace)[0]
    assert recipe["title"] in proposal["summary"]
    assert "porção" in proposal["summary"]
    assert '"servings":6' in proposal["summary"]
    assert '"surplus_servings":1' in proposal["summary"]
    applied = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert applied["data"]["plan"]["items"][0]["batches"] == 3
    assert public.call("propose_user_change", request)["data"]["status"] == "APPLIED_HISTORICAL"
    before = business_rows(database)
    other = deepcopy(request)
    other["operation_id"] = str(uuid4())
    other["command"]["payload"]["items"][0]["recipe_id"] = 2
    assert not public.call("propose_user_change", other)["ok"]
    assert len(local.list(workspace)) == 1
    assert business_rows(database) == before


def test_attendance_prices_only_after_new_local_acceptance_and_never_selects_the_price(
    pricing_workspace, tmp_path
):
    reader, workspace, recipe, _, _, database = pricing_workspace()
    migrate_proposals(reader.repository, tmp_path / "financial-review-backup.sqlite3")
    public = AttendanceService(database, workspace, "ATTENDANCE")
    local = ApprovalService(reader.repository)
    calculation_request = {"operation_id": str(uuid4()), "recipe": 1}
    before = business_rows(database)
    assert not public.call("calculate_pricing_scenarios", calculation_request)["ok"]
    assert business_rows(database) == before

    def decide(kind, payload):
        response = public.call(
            "propose_user_change",
            {"operation_id": str(uuid4()), "command": {"kind": kind, "payload": payload}},
        )
        assert response["ok"], response
        proposal = local.list(workspace)[-1]
        return local.approve(workspace, proposal["id"], proposal["hash"], attest=True)

    decide("record_recipe_feedback", {"recipe_id": 1, "feedback": "INTERESTED"})
    decide("set_production_plan", {"items": [{"recipe_id": 1, "position": 0, "batches": 1}]})
    decide("accept_recipe", {"recipe_id": 1})
    calculated = public.call("calculate_pricing_scenarios", calculation_request)
    assert calculated["ok"], calculated
    assert calculated["data"]["minimum_price"] == "11.12"
    assert [s["price"] for s in calculated["data"]["scenarios"]] == ["12.50", "14.29", "16.67"]
    assert public.call("get_business_state", {})["data"]["menu"] == []
    after_calculation = business_rows(database)
    assert public.call("calculate_pricing_scenarios", calculation_request) == calculated
    assert business_rows(database) == after_calculation
    decide("save_menu_decision", {"recipe_id": 1, "scenario_id": "M20"})
    menu = public.call("get_business_state", {})["data"]["menu"]
    assert menu[0]["price"] == "14.29"
    assert public.call("get_business_state", {})["data"]["requires_local_review"] is False
    for secret in (workspace, recipe["id"], "fingerprint", "acceptance_id", "calculation_id"):
        assert secret not in json.dumps(calculated)
    decide("set_production_plan", {"items": []})
    invalidated = business_rows(database)
    assert not public.call("calculate_pricing_scenarios", calculation_request)["ok"]
    assert public.call("get_business_state", {})["data"]["menu"] == []
    assert business_rows(database) == invalidated


def test_pending_operation_replay_is_exact_and_a_conflict_does_not_create_another_proposal(
    approval_workspace,
):
    local, workspace, database, _ = approval_workspace
    operation = str(uuid4())
    first = fact_proposal(local, workspace, operation_id=operation)
    before = business_rows(database)
    assert fact_proposal(local, workspace, operation_id=operation) == first
    with pytest.raises(BusinessRuleError, match="Operação"):
        fact_proposal(
            local,
            workspace,
            operation_id=operation,
            command={
                "kind": "record_kitchen_facts",
                "payload": {"facts": [{"category": "EQUIPMENT", "key": "stove", "value": False}]},
            },
        )
    assert len(local.list(workspace)) == 1
    assert business_rows(database) == before


def test_corrupted_consumed_proposal_cannot_sustain_current_authorization(approval_workspace):
    local, workspace, database, _ = approval_workspace
    proposal = fact_proposal(local, workspace)
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    public = AttendanceService(database, workspace, "ATTENDANCE")
    with sqlite3.connect(database) as db:
        document = json.loads(
            db.execute("SELECT document_json FROM user_change_proposals").fetchone()[0]
        )
        document["command"]["payload"]["facts"][0]["value"] = False
        db.execute("UPDATE user_change_proposals SET document_json=?", (json.dumps(document),))
    before = business_rows(database)
    assert not public.call("get_business_state", {})["ok"]
    with pytest.raises(BusinessRuleError):
        local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert business_rows(database) == before


def test_domain_references_from_another_workspace_are_rejected_before_proposal_persistence(
    pricing_workspace, tmp_path
):
    reader, workspace, _, _, _, database = pricing_workspace()
    migrate_proposals(reader.repository, tmp_path / "scope-backup.sqlite3")
    local = ApprovalService(reader.repository)
    before = business_rows(database)
    with pytest.raises(BusinessRuleError):
        local.propose(
            dict(
                workspace_id=workspace,
                operation_id=str(uuid4()),
                expected_revision=reader.get_business_state({"workspace_id": workspace})[
                    "revision"
                ],
                command={
                    "kind": "record_recipe_feedback",
                    "payload": {"recipe_id": str(uuid4()), "feedback": "INTERESTED"},
                },
            )
        )
    assert local.list(workspace) == []
    assert business_rows(database) == before


def test_service_enforces_exact_size_and_collection_limits_before_validation(approval_workspace):
    local, workspace, database, _ = approval_workspace
    before = business_rows(database)
    at_limit = {"padding": "x" * (256 * 1024 - len('{"padding":""}'))}
    with pytest.raises(ValidationError):
        local.propose(at_limit)
    with pytest.raises(BusinessRuleError) as oversized:
        local.propose({"padding": at_limit["padding"] + "x"})
    assert oversized.value.code == "INPUT_LIMIT"
    with pytest.raises(BusinessRuleError) as collection:
        local.propose({"nested": {"values": list(range(201))}})
    assert collection.value.code == "INPUT_LIMIT"
    assert local.list(workspace) == []
    assert business_rows(database) == before


def test_consumed_proposal_replay_cannot_return_a_changed_stored_result(approval_workspace):
    local, workspace, database, _ = approval_workspace
    proposal = fact_proposal(local, workspace)
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE user_change_proposals SET result_json='{}'")
    before = business_rows(database)
    with pytest.raises(sqlite3.DatabaseError):
        local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert business_rows(database) == before


def test_migration_backup_includes_wal_and_keeps_legacy_rows_byte_exact(
    pricing_workspace, tmp_path
):
    reader, workspace, recipe, acceptance, command, database = pricing_workspace()
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("BEGIN")
        connection.execute("SELECT COUNT(*) FROM operations").fetchone()
        command(
            "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
        )
        assert database.with_name(database.name + "-wal").exists()
        original = business_rows(database)
        backup = tmp_path / "wal-backup.sqlite3"
        migrate_proposals(reader.repository, backup)
        assert business_rows(database) == original
        assert business_rows(backup) == original
        with sqlite3.connect(backup) as saved:
            assert saved.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]
            assert saved.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        with sqlite3.connect(database) as migrated:
            assert migrated.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall() == [(1,), (2,)]


@pytest.mark.parametrize("invalid", ["future", "corrupt", "commit_failure"])
def test_migration_failure_preserves_original_and_does_not_create_a_partial_schema(
    tmp_path, inventory_file, invalid
):
    database = tmp_path / "migration.sqlite3"
    bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    if invalid == "corrupt":
        database.write_bytes(b"synthetic corrupt SQLite")
    else:
        with sqlite3.connect(database) as db:
            if invalid == "future":
                db.execute("UPDATE schema_migrations SET version=99")
            else:
                db.execute(
                    "CREATE TRIGGER fail_migration BEFORE INSERT ON schema_migrations "
                    "BEGIN SELECT RAISE(ABORT, 'synthetic migration failure'); END"
                )
    before = database.read_bytes()
    backup = tmp_path / "migration-backup.sqlite3"
    with pytest.raises(sqlite3.Error):
        migrate_proposals(SQLiteWorkspaceRepository(database), backup)
    assert database.read_bytes() == before
    if invalid != "commit_failure":
        assert not backup.exists()
    else:
        with sqlite3.connect(database) as db:
            assert (
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name='user_change_proposals'"
                ).fetchone()
                is None
            )


def test_legacy_conversion_review_keeps_old_acceptance_invalidated(pricing_workspace, tmp_path):
    reader, workspace, recipe, old_acceptance, command, database = pricing_workspace()
    conversion_payload = dict(
        ingredient_id=recipe["ingredients"][0]["ingredient_id"],
        from_unit="g",
        to_unit="g",
        factor="1",
        context="Fixture de medida",
        scope="RECIPE_MEASURE",
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][0]["line_id"],
    )
    old = command(
        "record_ingredient_conversion",
        **conversion_payload,
        evidence={
            "turn_ref": "legacy-conversion",
            "statement": "Medi esta quantidade",
            "captured_at": "2026-11-11T00:00:00Z",
        },
    )["data"]["conversion"]
    migrate_proposals(reader.repository, tmp_path / "conversion-backup.sqlite3")
    local = ApprovalService(reader.repository, clock=reader.clock)

    def decide(kind, payload):
        proposal = local.propose(
            dict(
                workspace_id=workspace,
                operation_id=str(uuid4()),
                expected_revision=reader.get_business_state({"workspace_id": workspace})[
                    "revision"
                ],
                command={"kind": kind, "payload": payload},
            )
        )
        return local.approve(workspace, proposal["id"], proposal["hash"], attest=True)

    decide("record_recipe_feedback", {"recipe_id": recipe["id"], "feedback": "INTERESTED"})
    plan = decide(
        "set_production_plan",
        {"items": [{"recipe_id": recipe["id"], "recipe_version": 1, "position": 0, "batches": 1}]},
    )["data"]["plan"]
    decide(
        "record_ingredient_conversion", conversion_payload | {"replaces_conversion_id": old["id"]}
    )
    evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
    accepted = decide(
        "accept_recipe",
        {
            "recipe_id": recipe["id"],
            "plan_item_id": plan["items"][0]["plan_item_id"],
            "evaluation_id": evaluation["evaluation_id"],
        },
    )
    assert accepted["data"]["acceptance"]["id"] != old_acceptance["id"]
    state = reader.repository.load(workspace)[1]
    assert len(state.ingredient_conversions) == 2
    assert state.ingredient_conversions[0].evidence.turn_ref == "legacy-conversion"
    assert any(str(a) == old_acceptance["id"] for a in state.invalidated_acceptance_ids)


@pytest.mark.parametrize("field", ["url", "excerpt", "retrieved_at"])
def test_candidate_revision_cannot_smuggle_a_new_web_source_before_the_provenance_slice(
    pricing_workspace, tmp_path, field
):
    reader, workspace, recipe, _, _, database = pricing_workspace()
    migrate_proposals(reader.repository, tmp_path / "source-backup.sqlite3")
    local = ApprovalService(reader.repository)
    candidate = {
        key: deepcopy(value) for key, value in recipe.items() if key in CandidateInput.model_fields
    }
    for line in candidate["ingredients"]:
        line.pop("line_id", None)
    candidate["ingredients"][0]["source"][field] = {
        "url": "https://example.org/new-unobserved-source",
        "excerpt": "Novo trecho não observado na fonte histórica",
        "retrieved_at": "2026-11-12T12:00:00Z",
    }[field]
    if field == "url":
        candidate["sources"].append(deepcopy(candidate["ingredients"][0]["source"]))
    before = business_rows(database)
    with pytest.raises(BusinessRuleError) as refused:
        local.propose(
            dict(
                workspace_id=workspace,
                operation_id=str(uuid4()),
                expected_revision=reader.get_business_state({"workspace_id": workspace})[
                    "revision"
                ],
                command={
                    "kind": "register_recipe_candidate",
                    "payload": {
                        "recipe_id": recipe["id"],
                        "expected_recipe_version": 1,
                        "candidate": candidate,
                    },
                },
            )
        )
    assert refused.value.code == "SOURCE_NOT_LINKED"
    assert local.list(workspace) == []
    assert business_rows(database) == before


def test_concurrent_different_proposals_require_a_new_review_after_the_first_commit(
    approval_workspace,
):
    local, workspace, database, clock = approval_workspace
    proposals = [fact_proposal(local, workspace) for _ in range(2)]
    before = business_rows(database)

    def apply(proposal):
        service = ApprovalService(SQLiteWorkspaceRepository(database), clock=lambda: clock[0])
        try:
            service.approve(workspace, proposal["id"], proposal["hash"], attest=True)
            return "APPLIED"
        except BusinessRuleError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(apply, proposals))
    assert sorted(outcomes) == ["APPLIED", "STALE_REVISION"]
    rows = business_rows(database)
    assert len(rows["decisions"]) == len(before["decisions"]) + 2
    assert len(rows["operations"]) == len(before["operations"]) + 1


def test_attendance_exposes_legacy_facts_as_pending_and_can_reconfirm_them_by_numeric_reference(
    pricing_workspace, tmp_path
):
    reader, workspace, _, _, command, database = pricing_workspace()
    command(
        "record_kitchen_facts",
        facts=[
            {
                "category": "EQUIPMENT",
                "key": "stove",
                "value": True,
                "evidence": {
                    "turn_ref": "legacy-fact",
                    "statement": "Tenho fogão",
                    "captured_at": "2026-11-11T00:00:00Z",
                },
            }
        ],
    )
    migrate_proposals(reader.repository, tmp_path / "facts-backup.sqlite3")
    public = AttendanceService(database, workspace, "ATTENDANCE")
    data = public.call("get_business_state", {})["data"]
    assert data["kitchen_facts"] == []
    pending = data["pending_kitchen_facts"][0]
    assert pending == {
        "fact": 1,
        "category": "EQUIPMENT",
        "key": "stove",
        "value": True,
        "unit": None,
    }
    proposed = public.call(
        "propose_user_change",
        {
            "operation_id": str(uuid4()),
            "command": {
                "kind": "record_kitchen_facts",
                "payload": {
                    "facts": [
                        {
                            "category": "EQUIPMENT",
                            "key": "stove",
                            "value": True,
                            "replaces_fact_id": pending["fact"],
                        }
                    ]
                },
            },
        },
    )
    assert proposed["ok"], proposed
    local = ApprovalService(reader.repository)
    proposal = local.list(workspace)[0]
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    resumed = public.call("get_business_state", {})["data"]
    assert resumed["pending_kitchen_facts"] == []
    assert resumed["kitchen_facts"][0]["key"] == "stove"


def test_attendance_exposes_the_references_needed_to_reconfirm_conversion_and_quote(
    pricing_workspace, tmp_path
):
    reader, workspace, recipe, _, command, database = pricing_workspace()
    ingredient = recipe["ingredients"][0]["ingredient_id"]
    command(
        "record_ingredient_conversion",
        ingredient_id=ingredient,
        from_unit="g",
        to_unit="g",
        factor="1",
        context="Medida sintética",
        scope="RECIPE_MEASURE",
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][0]["line_id"],
        evidence={
            "turn_ref": "legacy-measure",
            "statement": "Medi",
            "captured_at": "2026-11-11T00:00:00Z",
        },
    )
    command(
        "register_complement_quote",
        quote=dict(
            ingredient_id=ingredient,
            description="Arroz sintético",
            package_quantity={"value": "1000", "unit": "g"},
            package_price="20.00",
            purchase_extra_total="0.00",
            extra_conditions="Retirada gratuita",
            availability="AVAILABLE",
            availability_context="Retirada hoje",
            max_packages=3,
            supplier="Fixture offline",
            source=recipe["sources"][0],
        ),
    )
    migrate_proposals(reader.repository, tmp_path / "review-refs-backup.sqlite3")
    public = AttendanceService(database, workspace, "ATTENDANCE")
    local = ApprovalService(reader.repository)
    state = public.call("get_business_state", {})["data"]
    conversion = state["conversions"][0]
    quote = state["quotes"][0]
    assert (
        conversion["conversion"],
        conversion["recipe"],
        conversion["line"],
        conversion["ingredient"],
    ) == (1, 1, 1, 1)
    assert conversion["requires_local_review"] is True
    assert quote["quote"] == 1 and quote["status"] == "ESTIMATED"
    assert quote["package_price"] == "20.00"

    def decide(kind, payload):
        result = public.call(
            "propose_user_change",
            {"operation_id": str(uuid4()), "command": {"kind": kind, "payload": payload}},
        )
        assert result["ok"], result
        proposal = local.list(workspace)[-1]
        return local.approve(workspace, proposal["id"], proposal["hash"], attest=True)

    decide(
        "record_ingredient_conversion",
        {
            "ingredient_id": conversion["ingredient"],
            "recipe_id": conversion["recipe"],
            "line_id": conversion["line"],
            "replaces_conversion_id": conversion["conversion"],
            **{
                k: conversion[k]
                for k in (
                    "from_unit",
                    "to_unit",
                    "factor",
                    "context",
                    "scope",
                    "from_preparation_basis",
                )
            },
        },
    )
    decide(
        "confirm_complement_quote",
        {
            "quote_id": quote["quote"],
            "scope": {
                "packages": 1,
                **{
                    k: quote[k]
                    for k in (
                        "package_quantity",
                        "package_price",
                        "purchase_extra_total",
                        "extra_conditions",
                        "availability_context",
                        "supplier",
                    )
                },
            },
        },
    )
    resumed = public.call("get_business_state", {})["data"]
    assert resumed["conversions"][0]["requires_local_review"] is False
    assert resumed["quotes"][0]["status"] == "CONFIRMED"
    for private in (workspace, recipe["id"], "turn_ref", "retrieved_at", "fingerprint"):
        assert private not in json.dumps(resumed)


def test_corrupt_local_event_is_a_storage_refusal_without_new_effect(approval_workspace):
    local, workspace, database, _ = approval_workspace
    proposal = fact_proposal(local, workspace)
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE user_change_proposals SET event_json='[]'")
    before = business_rows(database)
    reader = BusinessStateReader(local.repository)
    result = reader.calculate_pricing_scenarios(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=1,
            recipe_id=str(uuid4()),
            acceptance_id=str(uuid4()),
        )
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert business_rows(database) == before


def test_legacy_quote_confirmation_is_not_presented_as_current_approval(
    pricing_workspace, tmp_path
):
    from dona_maria.quotes import ConfirmationScope, quote_confirmation_statement

    reader, workspace, recipe, _, command, database = pricing_workspace()
    now = datetime.now(UTC)
    reader.clock = lambda: now
    ingredient = recipe["ingredients"][0]["ingredient_id"]
    quote = command(
        "register_complement_quote",
        quote=dict(
            ingredient_id=ingredient,
            description="Arroz sintético",
            package_quantity={"value": "1000", "unit": "g"},
            package_price="20.00",
            purchase_extra_total="0.00",
            extra_conditions="Retirada gratuita",
            availability="AVAILABLE",
            availability_context="Retirada hoje",
            max_packages=3,
            supplier="Fixture offline",
            source=recipe["sources"][0],
        ),
    )["data"]["quote"]
    scope = dict(
        package_quantity={"value": "1000", "unit": "g"},
        package_price="20.00",
        purchase_extra_total="0.00",
        extra_conditions="Retirada gratuita",
        availability_context="Retirada hoje",
        supplier="Fixture offline",
        packages=1,
    )
    evidence = {
        "turn_ref": "legacy-quote",
        "statement": quote_confirmation_statement(ConfirmationScope.model_validate(scope)),
        "captured_at": now.isoformat(),
    }
    command(
        "confirm_complement_quote",
        quote_id=quote["id"],
        quote_version=1,
        scope=scope,
        evidence=evidence,
    )
    command(
        "set_production_plan",
        items=[{"recipe_id": recipe["id"], "recipe_version": 1, "position": 0, "batches": 1}],
        quote_selections=[
            {"ingredient_id": ingredient, "quote_id": quote["id"], "quote_version": 1}
        ],
        evidence=evidence | {"statement": "Confirmo esta produção"},
    )
    assert (
        reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]["purchase_status"]
        == "CONFIRMED"
    )
    migrate_proposals(reader.repository, tmp_path / "quote-trust-backup.sqlite3")
    before = business_rows(database)
    public = AttendanceService(database, workspace, "ATTENDANCE")
    purchase = public.call("evaluate_purchase_plan", {})
    assert purchase["data"]["purchase_status"] == "PENDING"
    assert purchase["data"]["requires_local_review"] is True
    assert public.call("get_business_state", {})["data"]["quotes"][0]["status"] == "REVIEW_REQUIRED"
    assert (
        public.call("evaluate_recipe_feasibility", {"recipe": 1, "plan_item": 1})["data"]["status"]
        == "PENDING"
    )
    assert business_rows(database) == before
