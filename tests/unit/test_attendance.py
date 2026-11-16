"""Contratos públicos do atendimento vinculado, sempre com dados sintéticos."""

import json
import subprocess
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import AttendanceService
from dona_maria.launcher import main as launch_attendance


def test_opening_and_restart_use_the_operator_binding_without_identifiers(tmp_path, inventory_file):
    database = tmp_path / "private.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    before = database.read_bytes()
    service = AttendanceService(database, workspace, "ATTENDANCE")

    opening = service.call("get_business_state", {})
    resumed = AttendanceService(database, workspace, "ATTENDANCE").call("get_business_state", {})

    assert opening == resumed
    assert opening["ok"] is True
    assert opening["data"]["remaining_budget"] == "80.00"
    assert opening["data"]["recipes"] == []
    assert workspace not in json.dumps(opening)
    assert str(database) not in json.dumps(opening)
    assert database.read_bytes() == before
    with pytest.raises(FrozenInstanceError):
        service.workspace_id = "00000000-0000-4000-8000-000000000002"


@pytest.mark.parametrize("invalid", ["relative", "missing", "corrupt", "other", "mode", "uuid"])
def test_invalid_binding_fails_closed_without_creating_or_changing_database(
    tmp_path, inventory_file, invalid
):
    database = tmp_path / "private-canary.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    mode = "ATTENDANCE"
    if invalid == "relative":
        database = database.relative_to(tmp_path)
    elif invalid == "missing":
        database = tmp_path / "never-created.sqlite3"
    elif invalid == "corrupt":
        database.write_bytes(b"PRIVATE-CANARY-INVALID-SQLITE")
    elif invalid == "other":
        workspace = "00000000-0000-4000-8000-000000000002"
    elif invalid == "mode":
        mode = "DIAGNOSTIC"
    else:
        workspace = "not a uuid"
    before = database.read_bytes() if database.exists() else None

    with pytest.raises(ValueError, match="Atendimento indisponível") as error:
        AttendanceService(database, workspace, mode)

    assert "canary" not in str(error.value)
    assert "sqlite" not in str(error.value)
    assert (database.read_bytes() if database.exists() else None) == before


def test_only_four_bound_reads_are_available_and_extras_cannot_change_context(pricing_workspace):
    reader, workspace, recipe, _, _, database = pricing_workspace()
    service = AttendanceService(database, workspace, "ATTENDANCE")
    before = reader.get_business_state({"workspace_id": workspace})
    snapshot = database.read_bytes()

    inventory = service.call("get_inventory_snapshot", {})
    assert inventory["ok"] is True
    assert inventory["data"]["items"][0]["name"] == "Arroz"
    assert service.call("evaluate_purchase_plan", {})["ok"] is True
    assert service.call("evaluate_recipe_feasibility", {"recipe": 1, "plan_item": 1})["ok"]
    opening = service.call("get_business_state", {})
    assert opening["data"]["recipes"][0]["title"] == recipe["title"]
    for name, arguments in [
        ("get_business_state", {"workspace_id": workspace}),
        ("get_business_state", {"mode": "DIAGNOSTIC"}),
        ("get_business_state", {"database": str(database)}),
        ("get_inventory_snapshot", {"ingredients": [2]}),
        ("evaluate_recipe_feasibility", {"recipe": 2, "plan_item": 1}),
        ("evaluate_recipe_feasibility", {"recipe": True, "plan_item": 1}),
        ("accept_recipe", {}),
        ("calculate_pricing_scenarios", {}),
        ("execute_sql", {}),
    ]:
        result = service.call(name, arguments)
        assert result["ok"] is False, (name, arguments)
        assert result["data"] is None
        assert "workspace" not in json.dumps(result)
    assert reader.get_business_state({"workspace_id": workspace}) == before
    assert database.read_bytes() == snapshot
    text = json.dumps([opening, inventory])
    for private in (workspace, recipe["id"], str(database), "fingerprint", "source_sha256"):
        assert private not in text


def test_input_limits_are_explicit_at_boundary_and_do_not_change_state(pricing_workspace):
    _, workspace, _, _, _, database = pricing_workspace()
    service = AttendanceService(database, workspace, "ATTENDANCE")
    before = database.read_bytes()
    assert service.call("get_inventory_snapshot", {"ingredients": [1] * 200})["ok"]
    assert not service.call("get_inventory_snapshot", {"ingredients": [1] * 201})["ok"]
    # A chave desconhecida é recusada estruturalmente; acima do limite, antes do schema.
    at_limit = {"padding": "x" * (256 * 1024 - len('{"padding":""}'))}
    assert "excede" not in service.call("get_business_state", at_limit)["message"]
    at_limit["padding"] += "x"
    result = service.call("get_business_state", at_limit)
    assert not result["ok"]
    assert "excede" in result["message"]
    assert database.read_bytes() == before


def test_storage_errors_and_internal_provenance_never_reach_attendance(
    pricing_workspace, recipe_candidate
):
    recipe_candidate["sources"][0]["excerpt"] = "PRIVATE-CANARY /operator/private.sqlite3"
    _, workspace, _, _, _, database = pricing_workspace()
    service = AttendanceService(database, workspace, "ATTENDANCE")
    text = json.dumps(service.call("get_business_state", {}))
    assert "PRIVATE-CANARY" not in text
    assert "private.sqlite3" not in text
    database.write_bytes(b"PRIVATE-CANARY invalid SQLite")
    failure = service.call("get_business_state", {})
    assert failure["ok"] is False
    assert failure["data"] is None
    for private in ("PRIVATE-CANARY", str(database), "Traceback", "SELECT", "details"):
        assert private not in json.dumps(failure)


@pytest.mark.parametrize("custom", [False, True])
def test_resume_reuses_current_facts_preferences_and_price_without_new_decisions(
    pricing_workspace, custom, reconfirm_attendance
):
    reader, workspace, recipe, acceptance, command, database = pricing_workspace(batches=2)
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    decision = command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        **({"custom_price": "25.00"} if custom else {"scenario_id": "M20"}),
        evidence={
            "statement": "Escolho o preço de R$ 25,00." if custom else "Escolho o cenário M20.",
            "turn_ref": "synthetic-choice",
            "captured_at": "2026-11-11T00:00:00Z",
        },
    )
    assert decision["ok"]
    reconfirm_attendance(reader, workspace, database)
    before = reader.get_business_state({"workspace_id": workspace})
    service = AttendanceService(database, workspace, "ATTENDANCE")

    data = service.call("get_business_state", {})["data"]

    assert data["kitchen_facts"][0]["value"] == "SEQUENTIAL"
    assert data["plan"][0] == {"plan_item": 1, "recipe": 1, "batches": 2, "servings": 4}
    assert data["menu"][0]["price"] == decision["data"]["decision"]["price"]
    assert data["menu"][0]["ingredient_cost_per_serving"] == calculation["cmv_per_serving"]
    expected = decision["data"]["chosen_option"]["display"]
    assert data["menu"][0]["fee"] == expected["fee"]
    assert data["menu"][0]["surplus_after_fee"] == expected["result"]
    assert data["recipes"][0]["interest"] == "INTERESTED"
    assert data["recipes"][0]["status"] == "MENU_SELECTED"
    assert "operational_costs" in data["menu"][0]
    assert reader.get_business_state({"workspace_id": workspace}) == before
    for private in (workspace, calculation["id"], acceptance["id"], "fingerprint", "evidence"):
        assert private not in json.dumps(data)


@pytest.mark.parametrize("remove_plan", [False, True])
def test_resume_omits_outdated_plan_confirmation_and_preserves_other_facts(
    pricing_workspace, remove_plan, reconfirm_attendance
):
    reader, workspace, recipe, _, command, database = pricing_workspace(batches=2)
    recorded = command(
        "record_kitchen_facts",
        facts=[
            {
                "category": "EQUIPMENT",
                "key": "oven",
                "value": "AVAILABLE",
                "evidence": {
                    "statement": "Tenho forno disponível.",
                    "turn_ref": "synthetic-oven",
                    "captured_at": "2026-11-11T00:00:00Z",
                },
            }
        ],
    )
    assert recorded["ok"]
    decide = reconfirm_attendance(reader, workspace, database)
    service = AttendanceService(database, workspace, "ATTENDANCE")
    opening = service.call("get_business_state", {})
    assert any(fact["key"] == "production_arrangement" for fact in opening["data"]["kitchen_facts"])
    changed = decide(
        "set_production_plan",
        items=[]
        if remove_plan
        else [{"recipe_id": recipe["id"], "recipe_version": 1, "batches": 3, "position": 1}],
    )
    assert changed["ok"]
    before = reader.get_business_state({"workspace_id": workspace})
    contents = database.read_bytes()
    resumed = service.call("get_business_state", {})
    assert resumed["ok"]
    assert resumed == AttendanceService(database, workspace, "ATTENDANCE").call(
        "get_business_state", {}
    )
    assert resumed["data"]["kitchen_facts"] == [
        {"category": "EQUIPMENT", "key": "oven", "value": "AVAILABLE", "unit": None}
    ]
    assert any(fact["key"] == "production_arrangement" for fact in before["data"]["kitchen_facts"])
    assert reader.get_business_state({"workspace_id": workspace}) == before
    assert database.read_bytes() == contents
    assert workspace not in json.dumps(resumed)
    if not remove_plan:
        feasibility = service.call("evaluate_recipe_feasibility", {"recipe": 1, "plan_item": 1})
        assert feasibility["data"]["status"] == "PENDING"
        assert any("plano atual" in gap for gap in feasibility["data"]["missing_information"])


@pytest.mark.parametrize(
    "condition,category,key,required,unit,available",
    [
        ("MIN_CAPACITY", "EQUIPMENT", "pot", "2", "L", "1"),
        ("MIN_AVAILABLE_TIME", "OPERATION", "time", "30", "min", "29"),
        ("EXPLICIT_CONDITION", "OPERATION", "storage", "refrigerado", None, "ambiente"),
        ("EXPLICIT_CONDITION", "OPERATION", "cooled", True, None, False),
    ],
)
def test_resume_preserves_requirement_thresholds_to_explain_a_block(
    pricing_workspace, recipe_candidate, condition, category, key, required, unit, available
):
    reader, workspace, recipe, _, command, database = pricing_workspace()
    recipe_candidate["requirements"] = [
        {
            "category": category,
            "key": key,
            "condition": condition,
            "value": required,
            "unit": unit,
            "reason": "Condição necessária para este preparo.",
            "source": recipe_candidate["sources"][0],
        }
    ]
    for review in recipe_candidate["category_reviews"]:
        review["requirement_keys"] = [key] if review["category"] == category else []
        if review["category"] == category:
            review["not_applicable_reason"] = None
    revised = command(
        "register_recipe_candidate",
        recipe_id=recipe["id"],
        expected_recipe_version=recipe["version"],
        candidate=recipe_candidate,
    )
    assert revised["ok"]
    plan = command(
        "set_production_plan",
        items=[
            {
                "recipe_id": recipe["id"],
                "recipe_version": revised["data"]["candidate"]["version"],
                "batches": 1,
                "position": 0,
            }
        ],
        evidence={
            "statement": "Confirmo o plano revisado.",
            "turn_ref": "synthetic-threshold-plan",
            "captured_at": "2026-11-11T00:00:00Z",
        },
    )
    assert plan["ok"]
    recorded = command(
        "record_kitchen_facts",
        facts=[
            {
                "category": category,
                "key": key,
                "value": available,
                "unit": unit,
                "evidence": {
                    "statement": "Informo esta condição da minha cozinha.",
                    "turn_ref": "synthetic-threshold-fact",
                    "captured_at": "2026-11-11T00:00:00Z",
                },
            }
        ],
    )
    assert recorded["ok"]
    before = reader.get_business_state({"workspace_id": workspace})
    contents = database.read_bytes()
    service = AttendanceService(database, workspace, "ATTENDANCE")
    opening = service.call("get_business_state", {})
    assert opening["ok"]
    requirement = opening["data"]["recipes"][0]["conditions"][0]
    assert requirement == {
        "category": category,
        "key": key,
        "condition": condition,
        "value": required,
        "unit": unit,
        "status": "BLOCKED",
        "reason": "Condição necessária para este preparo.",
    }
    assert type(requirement["value"]) is type(required)
    assert (
        AttendanceService(database, workspace, "ATTENDANCE").call("get_business_state", {})
        == opening
    )
    feasibility = service.call("evaluate_recipe_feasibility", {"recipe": 1, "plan_item": 1})
    assert feasibility["data"]["status"] == "BLOCKED"
    assert feasibility["data"]["conditions"][0]["question"] is None
    assert reader.get_business_state({"workspace_id": workspace}) == before
    assert database.read_bytes() == contents
    for private in (workspace, recipe["id"], "source_sha256", "fingerprint", "evidence"):
        assert private not in json.dumps(opening)


def test_purchase_read_explains_shortage_without_internal_references(pricing_workspace):
    _, workspace, recipe, _, command, database = pricing_workspace()
    plan = command(
        "set_production_plan",
        items=[
            {
                "recipe_id": recipe["id"],
                "recipe_version": 1,
                "batches": 100,
                "position": 1,
                "requested_servings": 200,
            }
        ],
        evidence={
            "statement": "Confirmo esta produção.",
            "turn_ref": "synthetic-plan",
            "captured_at": "2026-11-11T00:00:00Z",
        },
    )
    assert plan["ok"], plan
    result = AttendanceService(database, workspace, "ATTENDANCE").call("evaluate_purchase_plan", {})
    assert result["ok"]
    line = result["data"]["demand"][0]
    assert line["name"] == "Arroz"
    assert line["required"] == "10000"
    assert line["shortage"] == "5000"
    assert line["unit"] == "g"
    assert result["data"]["questions"]
    assert "Arroz" in json.dumps(result["data"]["questions"])
    assert "ingredient_id" not in json.dumps(result)


def test_stdio_launcher_does_not_pass_provider_secrets_to_business_process(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC-ENV-CANARY")
    monkeypatch.setenv("UNRELATED_PRIVATE_SETTING", "SYNTHETIC-ENV-CANARY")
    monkeypatch.setenv("DONA_MARIA_MODE", "ATTENDANCE")
    observed = []

    def spawn(command, *, env, check):
        observed.append(env)
        return SimpleNamespace(returncode=0)

    # Fronteira do sistema operacional; MCP real do launcher é verificado em integração.
    monkeypatch.setattr(subprocess, "run", spawn)
    with pytest.raises(SystemExit) as exited:
        launch_attendance()
    assert exited.value.code == 0
    assert observed[0]["DONA_MARIA_MODE"] == "ATTENDANCE"
    assert "OPENAI_API_KEY" not in observed[0]
    assert "UNRELATED_PRIVATE_SETTING" not in observed[0]
    assert "SYNTHETIC-ENV-CANARY" not in observed[0].values()
