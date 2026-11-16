"""S15: receita própria nas fronteiras públicas de proposta e consulta."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import AttendanceService, BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.planning import BusinessRuleError


@pytest.fixture
def human_recipe(recipe_candidate):
    def replace(value):
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            if value.get("kind") == "WEB":
                return {"kind": "USER_PROVIDED"}
            return {key: replace(item) for key, item in value.items()}
        return value

    recipe = replace(deepcopy(recipe_candidate))
    recipe["title"] = "Receita minha de arroz"
    recipe["origin"] = {"source": {"kind": "USER_PROVIDED"}}
    return recipe


@pytest.fixture
def human_workspace(tmp_path, inventory_file):
    database = tmp_path / "human.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "backup.sqlite3")
    return ApprovalService(repository), workspace, database


def propose_recipe(local, workspace, recipe):
    reader = BusinessStateReader(local.repository)
    return local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=reader.get_business_state({"workspace_id": workspace})["revision"],
            command={"kind": "register_recipe_candidate", "payload": {"candidate": recipe}},
        )
    )


def test_human_recipe_without_url_requires_local_approval_and_survives_restart(
    human_workspace, human_recipe
):
    local, workspace, database = human_workspace
    reader = BusinessStateReader(local.repository)
    before = reader.get_business_state({"workspace_id": workspace})
    proposal = propose_recipe(local, workspace, human_recipe)
    assert reader.get_business_state({"workspace_id": workspace}) == before
    assert local.inspect(workspace, proposal["id"])["command"]["payload"]["candidate"][
        "method_source"
    ] == {"kind": "USER_PROVIDED"}

    result = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert result["ok"], result
    current = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )
    recipe = current["data"]["candidates"][0]
    assert recipe["title"] == "Receita minha de arroz"
    assert recipe["provenance_version"] == "2.0"
    source = recipe["ingredients"][0]["original_measure"]["source"]
    assert source["kind"] == "USER_PROVIDED"
    assert source["evidence"]["turn_ref"].startswith("local:")
    assert source["information_ref"]["field"] == "ingredients/0/original_measure/source"
    assert "url" not in source
    assert recipe["complete"] is False
    assert recipe["yield_per_batch"] is None
    assert recipe["requirements"] == []
    assert current["data"]["menu"] == []
    assert local.approve(workspace, proposal["id"], proposal["hash"], attest=True) == result


def test_source_from_another_field_cannot_confirm_modified_information(
    human_workspace, human_recipe
):
    local, workspace, database = human_workspace
    proposal = propose_recipe(local, workspace, human_recipe)
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    # Corrupção sintética na fronteira SQLite: mesmo evento, informação não atestada.
    with sqlite3.connect(database) as db:
        state = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        recipe = state["candidates"][0]
        recipe["method"] = "Método não declarado pela cozinheira"
        recipe["method_source"] = recipe["ingredients"][0]["source"]
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(state),))
    result = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )
    assert result["ok"] is False
    assert result["data"] is None


def test_normalized_quantity_is_derived_by_server_from_attested_measure(
    human_workspace, human_recipe
):
    local, workspace, _ = human_workspace
    human_recipe["ingredients"][0]["original_measure"].update(
        value="0.1", unit_label="kg", raw_text="0,1 kg de arroz"
    )
    proposal = propose_recipe(local, workspace, human_recipe)
    result = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    ingredient = result["data"]["candidate"]["ingredients"][0]
    assert ingredient["quantity"] == {"value": "100", "unit": "g"}
    assert ingredient["quantity_source"]["kind"] == "DERIVED"
    assert ingredient["quantity_source"]["rule"] == "STANDARD_UNIT"
    assert ingredient["quantity_source"]["rule_version"] == "1.0"
    assert (
        ingredient["quantity_source"]["inputs"][0]["field"]
        == "ingredients/0/original_measure/source"
    )


def test_human_recipe_needs_no_recipe_wide_source_list(human_workspace, human_recipe):
    local, workspace, _ = human_workspace
    human_recipe["sources"] = []
    proposal = propose_recipe(local, workspace, human_recipe)
    assert local.approve(workspace, proposal["id"], proposal["hash"], attest=True)["ok"]


@pytest.mark.parametrize(
    "damage", ["version", "event", "context", "field", "evidence", "legacy_downgrade"]
)
def test_corrupted_provenance_is_not_recovered_as_confirmed(
    human_workspace, human_recipe, recipe_candidate, damage
):
    local, workspace, database = human_workspace
    proposal = propose_recipe(local, workspace, human_recipe)
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    with sqlite3.connect(database) as db:
        state = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        recipe = state["candidates"][0]
        source = recipe["method_source"]
        if damage == "version":
            recipe.pop("provenance_version")
        elif damage == "event":
            source["local_event_id"] = str(uuid4())
        elif damage == "context":
            source["information_ref"]["entity_id"] = str(uuid4())
        elif damage == "field":
            source["information_ref"]["field"] = "yield_per_batch/source"
        elif damage == "legacy_downgrade":
            from dona_maria.provenance import source_fields

            recipe.pop("provenance_version")
            recipe.pop("origin")
            for ingredient in recipe["ingredients"]:
                ingredient.pop("quantity_source", None)
            for _, source in source_fields(recipe):
                source.clear()
                source.update(recipe_candidate["sources"][0])
            recipe["method"] = "Método nunca aprovado."
        else:
            source["evidence"] = None
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(state),))
    assert not BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )["ok"]


def test_proposal_refuses_unattested_authority_and_unavailable_source_flows(
    human_workspace, human_recipe
):
    local, workspace, _ = human_workspace
    reader = BusinessStateReader(local.repository)
    before = reader.get_business_state({"workspace_id": workspace})
    for fake_source in (
        {"kind": "USER_PROVIDED", "local_event_id": str(uuid4())},
        {"kind": "USER_PROVIDED", "url": "https://example.org/fake"},
        {"kind": "DERIVED", "rule": "O modelo confirma"},
        {"kind": "USER_SIMULATION", "scenario": "Simulação"},
        {
            "kind": "USER_REPORTED_MEASUREMENT",
            "method": "Balança",
            "context": "Casa",
            "local_event_id": str(uuid4()),
        },
        {
            "kind": "WEB",
            "research_result_id": str(uuid4()),
            "segment": "1",
            "url": "https://example.org/fake",
            "title": "Falsa",
            "excerpt": "Não pesquisada",
            "retrieved_at": "2026-11-15T12:00:00Z",
        },
    ):
        candidate = deepcopy(human_recipe)
        candidate["method_source"] = fake_source
        with pytest.raises((BusinessRuleError, ValidationError)):
            propose_recipe(local, workspace, candidate)
    assert local.list(workspace) == []
    assert reader.get_business_state({"workspace_id": workspace}) == before


@pytest.mark.parametrize(
    ("column", "document"),
    [
        ("event_json", {}),
        ("result_json", {"data": {"candidate": [1]}}),
        ("result_json", {"data": {"candidate": {"id": "x", "version": 1}}}),
        ("result_json", {"data": {"conversion": [1]}}),
    ],
)
def test_malformed_provenance_audit_is_refused_without_rewriting_database(
    human_workspace, human_recipe, column, document
):
    local, workspace, database = human_workspace
    proposal = propose_recipe(local, workspace, human_recipe)
    assert local.approve(workspace, proposal["id"], proposal["hash"], attest=True)["ok"]
    with sqlite3.connect(database) as db:
        db.execute(f"UPDATE user_change_proposals SET {column}=?", (json.dumps(document),))
    before = database.read_bytes()
    refused = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )
    assert not refused["ok"]
    assert refused["data"] is None
    assert database.read_bytes() == before


def test_direct_human_write_cannot_bypass_local_channel(human_workspace, human_recipe):
    local, workspace, _ = human_workspace
    reader = BusinessStateReader(local.repository)
    result = reader.register_recipe_candidate(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=0,
            candidate=human_recipe,
        )
    )
    assert not result["ok"]
    assert reader.get_business_state({"workspace_id": workspace})["revision"] == 0


def test_invalid_quantity_rolls_back_recipe_and_local_authorization(human_workspace, human_recipe):
    local, workspace, database = human_workspace
    human_recipe["ingredients"][0]["quantity"]["value"] = "999"
    proposal = propose_recipe(local, workspace, human_recipe)
    before = BusinessStateReader(local.repository).get_business_state({"workspace_id": workspace})
    with pytest.raises(ValueError, match="diverge"):
        local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert local.inspect(workspace, proposal["id"])["status"] == "PENDING"
    assert (
        BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
            {"workspace_id": workspace}
        )
        == before
    )


def test_legacy_read_migration_and_old_replay_preserve_bytes(
    tmp_path, inventory_file, recipe_candidate
):
    database = tmp_path / "legacy.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    request = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=0,
        candidate=recipe_candidate,
    )
    original = reader.register_recipe_candidate(request)
    assert original["ok"]

    def rows():
        with sqlite3.connect(database) as db:
            return {
                name: db.execute(f"SELECT * FROM {name}").fetchall()
                for name in ("workspaces", "inventory_snapshots", "operations", "decisions")
            }

    before = rows()
    migrate_proposals(reader.repository, tmp_path / "consistent-backup.sqlite3")
    reopened = BusinessStateReader(SQLiteWorkspaceRepository(database))
    assert reopened.register_recipe_candidate(request) == original
    legacy = reopened.get_business_state({"workspace_id": workspace})["data"]["candidates"][0]
    assert "provenance_version" not in legacy
    assert "quantity_source" not in legacy["ingredients"][0]
    assert legacy["sources"][0] == recipe_candidate["sources"][0]
    assert rows() == before
    with sqlite3.connect(tmp_path / "consistent-backup.sqlite3") as db:
        assert db.execute("SELECT * FROM decisions").fetchall() == before["decisions"]


def test_existing_financial_decisions_remain_historical_after_new_human_recipe(
    pricing_workspace, human_recipe, tmp_path
):
    reader, workspace, _, acceptance, _, database = pricing_workspace()
    with sqlite3.connect(database) as db:
        historical = db.execute("SELECT * FROM decisions").fetchall()
        operations = db.execute("SELECT * FROM operations").fetchall()
    migrate_proposals(reader.repository, tmp_path / "legacy-decisions.sqlite3")
    local = ApprovalService(reader.repository)
    proposal = propose_recipe(local, workspace, human_recipe)
    local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM decisions").fetchall()[: len(historical)] == historical
        assert db.execute("SELECT * FROM operations").fetchall()[: len(operations)] == operations
    current = reader.get_business_state({"workspace_id": workspace})
    assert current["ok"], current
    assert current["data"]["acceptances"][0]["id"] == acceptance["id"]


@pytest.mark.parametrize("damage", [None, "missing_source", "downgraded_factor"])
def test_contextual_conversion_keeps_human_origin_and_server_derived_quantity(
    human_workspace, human_recipe, damage
):
    local, workspace, database = human_workspace
    reader = BusinessStateReader(local.repository)
    stock = reader.get_inventory_snapshot({"workspace_id": workspace})["data"]["items"][0]
    line = human_recipe["ingredients"][0]
    line.update(ingredient_id=stock["id"], quantity=None, quantity_gap="Falta converter a xícara.")
    line["original_measure"].update(
        raw_text="1 xícara de arroz cru", value="1", unit_label="xícara"
    )
    proposal = propose_recipe(local, workspace, human_recipe)
    recipe = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)["data"][
        "candidate"
    ]
    conversion = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=1,
            command=dict(
                kind="record_ingredient_conversion",
                payload=dict(
                    ingredient_id=stock["id"],
                    recipe_id=recipe["id"],
                    recipe_version=1,
                    line_id=recipe["ingredients"][0]["line_id"],
                    scope="RECIPE_MEASURE",
                    from_unit="xícara",
                    to_unit="g",
                    factor="100",
                    context="Xícara declarada nesta receita.",
                ),
            ),
        )
    )
    local.approve(workspace, conversion["id"], conversion["hash"], attest=True)
    state = reader.get_business_state({"workspace_id": workspace})
    assert state["ok"], state
    source = state["data"]["ingredient_conversions"][0]["source"]
    assert source["kind"] == "USER_PROVIDED"
    effective = state["data"]["candidates"][0]["ingredients"][0]
    assert effective["quantity"] == {"value": "100", "unit": "g"}
    assert effective["quantity_source"]["kind"] == "DERIVED"
    assert [ref["entity"] for ref in effective["quantity_source"]["inputs"]] == [
        "RECIPE",
        "CONVERSION",
    ]
    if damage is not None:
        with sqlite3.connect(database) as db:
            stored = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
            conversion = stored["ingredient_conversions"][0]
            conversion.pop("source")
            if damage == "downgraded_factor":
                conversion["factor"] = "900"
            db.execute("UPDATE workspaces SET state_json=?", (json.dumps(stored),))
        before = database.read_bytes()
        refused = reader.get_business_state({"workspace_id": workspace})
        assert not refused["ok"]
        assert refused["data"] is None
        assert database.read_bytes() == before


def test_human_approval_is_atomic_on_storage_failure_and_replay_is_concurrent(
    human_workspace, human_recipe
):
    local, workspace, database = human_workspace
    proposal = propose_recipe(local, workspace, human_recipe)
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TRIGGER refuse_recipe BEFORE INSERT ON operations "
            "BEGIN SELECT RAISE(ABORT, 'synthetic'); END"
        )
    with pytest.raises(sqlite3.Error):
        local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert local.inspect(workspace, proposal["id"])["status"] == "PENDING"
    assert (
        BusinessStateReader(local.repository).get_business_state({"workspace_id": workspace})[
            "revision"
        ]
        == 0
    )
    with sqlite3.connect(database) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM decisions WHERE kind='LOCAL_APPROVAL'").fetchone()[0]
            == 0
        )
        db.execute("DROP TRIGGER refuse_recipe")

    def approve(_):
        return ApprovalService(SQLiteWorkspaceRepository(database)).approve(
            workspace, proposal["id"], proposal["hash"], attest=True
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, range(2)))
    assert results[0] == results[1]
    assert (
        BusinessStateReader(local.repository).get_business_state({"workspace_id": workspace})[
            "revision"
        ]
        == 1
    )


def test_stale_human_recipe_proposal_cannot_reuse_approval(human_workspace, human_recipe):
    local, workspace, _ = human_workspace
    first = propose_recipe(local, workspace, human_recipe)
    second = propose_recipe(local, workspace, human_recipe)
    local.approve(workspace, first["id"], first["hash"], attest=True)
    with pytest.raises(BusinessRuleError, match="Estado alterado"):
        local.approve(workspace, second["id"], second["hash"], attest=True)
    assert local.inspect(workspace, second["id"])["status"] == "PENDING"


@settings(
    max_examples=12, database=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(event=st.uuids())
def test_arbitrary_event_never_grants_human_authority(human_workspace, human_recipe, event):
    local, workspace, _ = human_workspace
    candidate = deepcopy(human_recipe)
    candidate["method_source"]["local_event_id"] = str(event)
    with pytest.raises(BusinessRuleError):
        propose_recipe(local, workspace, candidate)
    assert local.list(workspace) == []


def test_s15_cannot_turn_historical_web_recipe_into_mixed_adaptation(pricing_workspace, tmp_path):
    from dona_maria.candidates import CandidateInput

    reader, workspace, recipe, _, _, database = pricing_workspace()
    migrate_proposals(reader.repository, tmp_path / "before-adaptation.sqlite3")
    local = ApprovalService(reader.repository)
    candidate = {k: deepcopy(v) for k, v in recipe.items() if k in CandidateInput.model_fields}
    for line in candidate["ingredients"]:
        line.pop("line_id", None)
    candidate["origin"] = {"source": {"kind": "USER_PROVIDED"}}
    candidate["method_source"] = {"kind": "USER_PROVIDED"}
    with pytest.raises(BusinessRuleError, match="Adaptação"):
        local.propose(
            dict(
                workspace_id=workspace,
                operation_id=str(uuid4()),
                expected_revision=reader.get_business_state({"workspace_id": workspace})[
                    "revision"
                ],
                command=dict(
                    kind="register_recipe_candidate",
                    payload=dict(
                        recipe_id=recipe["id"],
                        expected_recipe_version=1,
                        candidate=candidate,
                    ),
                ),
            )
        )
    assert local.list(workspace) == []


@pytest.mark.parametrize("output_field", [False, True])
def test_legacy_direct_api_refuses_expanded_sources_without_poisoning_database(
    tmp_path, inventory_file, recipe_candidate, output_field
):
    database = tmp_path / "unmigrated.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    before = reader.get_business_state({"workspace_id": workspace})
    if output_field:
        recipe_candidate["ingredients"][0]["quantity_source"] = recipe_candidate["sources"][0]
    else:
        recipe_candidate["method_source"] = {
            "kind": "USER_SIMULATION",
            "scenario": "Não autorizado",
        }
    result = reader.register_recipe_candidate(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=0,
            candidate=recipe_candidate,
        )
    )
    assert result["ok"] is False
    assert reader.get_business_state({"workspace_id": workspace}) == before


def test_legacy_web_without_explicit_kind_keeps_old_operation_replay(
    tmp_path, inventory_file, recipe_candidate
):
    database = tmp_path / "implicit-web.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    request = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=0,
        candidate=recipe_candidate,
    )
    committed = reader.register_recipe_candidate(request)
    assert committed["ok"]
    recipe_candidate["sources"][0].pop("kind")
    assert reader.register_recipe_candidate(request) == committed


def test_recipe_source_collection_accepts_200_and_refuses_201_without_partial_effect(
    human_workspace, human_recipe
):
    local, workspace, database = human_workspace
    attendance = AttendanceService(database, workspace, "ATTENDANCE")
    human_recipe["sources"] = [{"kind": "USER_PROVIDED"} for _ in range(200)]
    request = dict(
        operation_id=str(uuid4()),
        command=dict(kind="register_recipe_candidate", payload=dict(candidate=human_recipe)),
    )
    assert attendance.call("propose_user_change", request)["ok"]
    human_recipe["sources"].append({"kind": "USER_PROVIDED"})
    request["operation_id"] = str(uuid4())
    refused = attendance.call("propose_user_change", request)
    assert not refused["ok"]
    assert refused["data"] is None
    assert len(local.list(workspace)) == 1
    assert (
        BusinessStateReader(local.repository).get_business_state({"workspace_id": workspace})[
            "revision"
        ]
        == 0
    )
