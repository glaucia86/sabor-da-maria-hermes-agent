import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader, SQLiteWorkspaceRepository


@pytest.mark.parametrize("damage", ["header", "truncated"])
def test_corrupt_database_refuses_bootstrap_and_commands_without_recreation(
    tmp_path, inventory_file, recipe_candidate, damage
):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    contents = database.read_bytes()
    database.write_bytes(b"synthetic corrupt SQLite" if damage == "header" else contents[:100])
    before = database.read_bytes()
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    responses = [
        reader.get_business_state({"workspace_id": created["workspace_id"]}),
        reader.register_recipe_candidate(
            dict(
                workspace_id=created["workspace_id"],
                operation_id=str(uuid4()),
                expected_revision=0,
                candidate=recipe_candidate,
            )
        ),
    ]
    assert all(response["error"]["code"] == "STORAGE_UNAVAILABLE" for response in responses)
    with pytest.raises(sqlite3.DatabaseError):
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert database.read_bytes() == before


def test_reset_creates_separate_workspace_and_preserves_previous_menu(
    tmp_path, inventory_file, pricing_workspace
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    chosen = command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence=dict(
            turn_ref="synthetic-reset", statement="Escolho M20.", captured_at="2026-11-13T12:00:00Z"
        ),
    )
    assert chosen["ok"]
    before = service.get_business_state({"workspace_id": workspace})
    original_inventory = service.get_inventory_snapshot({"workspace_id": workspace})["data"]
    reset = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert reset["workspace_id"] != workspace
    assert reset["snapshot_id"] == original_inventory["id"]
    assert service.get_business_state({"workspace_id": workspace}) == before
    new = service.get_business_state({"workspace_id": reset["workspace_id"]})
    assert new["revision"] == 0
    assert new["data"]["menu"] == []
    assert new["data"]["candidates"] == []
    assert new["data"]["budget_remaining"] == "80.00"
    assert (
        service.get_inventory_snapshot({"workspace_id": reset["workspace_id"]})["data"]
        == original_inventory
    )


def test_bootstrap_reuses_snapshot_and_never_replaces_an_existing_workspace(
    tmp_path, inventory_file
):
    database = tmp_path / "synthetic.sqlite3"
    first = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    original = reader.get_inventory_snapshot({"workspace_id": first["workspace_id"]})
    repeated = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, workspace_id=first["workspace_id"]
    )
    second = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert repeated == first
    assert second["workspace_id"] != first["workspace_id"]
    assert second["snapshot_id"] == first["snapshot_id"]

    book = load_workbook(inventory_file)
    book["Despensa"]["B2"] = 1
    book.save(inventory_file)
    book.close()
    with pytest.raises(ValueError, match="fotografia diferente"):
        bootstrap_workspace(
            database, inventory_file, allowed_directory=tmp_path, workspace_id=first["workspace_id"]
        )
    third = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert third["snapshot_id"] != first["snapshot_id"]
    assert reader.get_inventory_snapshot({"workspace_id": first["workspace_id"]}) == original
    assert (
        reader.get_inventory_snapshot({"workspace_id": third["workspace_id"]})["data"]["items"][0][
            "unit_cost"
        ]
        == "0.00498"
    )


def test_newer_database_schema_is_refused_without_recreation(tmp_path, inventory_file):
    database = tmp_path / "synthetic.sqlite3"
    first = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    with closing(sqlite3.connect(database)) as db:
        db.execute("UPDATE schema_migrations SET version=2")
        db.commit()
    before = database.read_bytes()
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    response = reader.get_business_state({"workspace_id": first["workspace_id"]})
    assert response["error"]["code"] == "STORAGE_UNAVAILABLE"
    with pytest.raises(sqlite3.DatabaseError):
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert database.read_bytes() == before


def test_duplicate_keys_in_persisted_state_are_not_silently_resolved(tmp_path, inventory_file):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    with closing(sqlite3.connect(database)) as db:
        state = db.execute("SELECT state_json FROM workspaces").fetchone()[0]
        state = state.replace(
            '"budget_initial":"80.00"', '"budget_initial":"999.00","budget_initial":"80.00"'
        )
        db.execute("UPDATE workspaces SET state_json=?", (state,))
        db.commit()
    before = database.read_bytes()
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
    response = reader.get_business_state({"workspace_id": created["workspace_id"]})
    assert response["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert database.read_bytes() == before


@pytest.mark.parametrize("corruption", ["hash", "policy", "duplicate_identity"])
def test_inconsistent_snapshot_blocks_reads_and_writes_without_changing_storage(
    tmp_path, inventory_file, recipe_candidate, corruption
):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    with closing(sqlite3.connect(database)) as db:
        snapshot = json.loads(
            db.execute("SELECT payload_json FROM inventory_snapshots").fetchone()[0]
        )
        if corruption == "hash":
            snapshot["source_sha256"] = "0" * 64
        elif corruption == "policy":
            db.execute("UPDATE inventory_snapshots SET import_policy_version='unsupported'")
        else:
            snapshot["items"].append(snapshot["items"][0])
        db.execute("UPDATE inventory_snapshots SET payload_json=?", (json.dumps(snapshot),))
        db.commit()
    before = database.read_bytes()
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))

    responses = [
        reader.get_business_state({"workspace_id": created["workspace_id"]}),
        reader.get_inventory_snapshot({"workspace_id": created["workspace_id"]}),
        reader.register_recipe_candidate(
            {
                "workspace_id": created["workspace_id"],
                "operation_id": str(uuid4()),
                "expected_revision": 0,
                "candidate": recipe_candidate,
            }
        ),
    ]

    assert [response["error"]["code"] if response["error"] else None for response in responses] == [
        "STORAGE_UNAVAILABLE"
    ] * 3
    with pytest.raises(sqlite3.DatabaseError):
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert database.read_bytes() == before
