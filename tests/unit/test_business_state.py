import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from dona_maria.business_state import BusinessStateReader, SQLiteWorkspaceRepository


@pytest.mark.parametrize("layout", ["empty_database", "empty_table", "other_workspace"])
def test_missing_workspace_returns_an_error_without_inventing_business_state(tmp_path, layout):
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/s00_missing_workspace.json").read_text("utf-8")
    )
    database = tmp_path / "synthetic.sqlite3"
    with sqlite3.connect(database) as db:
        if layout != "empty_database":
            db.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY)")
        if layout == "other_workspace":
            db.execute(
                "INSERT INTO workspaces VALUES (?)", ("00000000-0000-4000-8000-000000000002",)
            )
    db.close()
    before = database.read_bytes()
    reader = BusinessStateReader(
        SQLiteWorkspaceRepository(database),
        clock=lambda: datetime.fromisoformat(fixture["checked_at"]),
    )

    result = reader.get_business_state({"workspace_id": fixture["workspace_id"]})

    assert result["ok"] is False
    assert result["data"] is None
    assert result["revision"] is None
    assert result["workspace_id"] == fixture["workspace_id"]
    assert result["schema_version"] == "1.0"
    assert result["operation_id"] is None
    assert result["warnings"] == []
    assert result["error"] == {
        "code": "NOT_FOUND",
        "message": "Workspace não encontrado.",
        "details": {"checked_at": "2026-11-11T12:00:00Z"},
        "retryable": False,
        "next_action": "CONFIGURE_WORKSPACE",
    }
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"workspace_id": "not-a-uuid"},
        {"workspace_id": 123},
        {"workspace_id": True},
        {"workspace_id": None},
        {"workspace_id": "' OR 1=1 --"},
        {"workspace_id": ["00000000-0000-4000-8000-000000000001"]},
        {"workspace_id": {"value": "00000000-0000-4000-8000-000000000001"}},
        {"workspace_id": "00000000-0000-4000-8000-000000000001", "confirmed": True},
    ],
)
def test_invalid_request_is_rejected_before_accessing_storage(tmp_path, arguments):
    database = tmp_path / "must-not-be-created.sqlite3"
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))

    result = reader.get_business_state(arguments)

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert result["error"]["retryable"] is False
    assert result["error"]["next_action"] == "CORRECT_INPUT"
    assert not database.exists()


@pytest.mark.parametrize("storage", ["missing", "corrupt", "existing_workspace"])
def test_unavailable_or_unsupported_storage_returns_a_safe_error(tmp_path, storage):
    database = tmp_path / "private-path-must-not-leak.sqlite3"
    workspace_id = "00000000-0000-4000-8000-000000000001"
    if storage == "corrupt":
        database.write_bytes(b"synthetic invalid SQLite fixture")
    elif storage == "existing_workspace":
        # Somente a identidade; não é bootstrap nem schema de negócio de S01.
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY)")
            db.execute("INSERT INTO workspaces VALUES (?)", (workspace_id,))
        db.close()
    before = database.read_bytes() if database.exists() else None
    reader = BusinessStateReader(SQLiteWorkspaceRepository(database))

    result = reader.get_business_state({"workspace_id": workspace_id})

    assert result["ok"] is False
    assert result["data"] is None
    assert result["revision"] is None
    assert result["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert result["error"]["next_action"] == "CHECK_STORAGE"
    assert "private-path" not in json.dumps(result)
    assert "Traceback" not in json.dumps(result)
    assert (database.read_bytes() if database.exists() else None) == before
