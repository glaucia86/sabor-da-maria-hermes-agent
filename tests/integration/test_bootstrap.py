import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader, SQLiteWorkspaceRepository


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
