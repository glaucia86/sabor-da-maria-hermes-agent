"""Replay deve recusar resultados persistidos corrompidos sem alterar o banco."""

import json
import sqlite3
import sys
from contextlib import closing
from uuid import uuid4

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


@pytest.fixture(params=["register_recipe_candidate", "set_production_plan"])
def stored_operation(tmp_path, inventory_file, recipe_candidate, request):
    database = tmp_path / "synthetic.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    service = BusinessStateReader(SQLiteWorkspaceRepository(database))
    command = dict(
        workspace_id=workspace["workspace_id"], operation_id=str(uuid4()), expected_revision=0
    )
    if request.param == "register_recipe_candidate":
        command["candidate"] = recipe_candidate
    else:
        command.update(
            items=[],
            evidence=dict(
                turn_ref="synthetic-plan",
                statement="Confirmo o plano vazio.",
                captured_at="2026-11-13T12:00:00Z",
            ),
        )
    handler = getattr(service, request.param)
    committed = handler(command)
    assert committed["ok"]
    return service, handler, command, committed, database


@pytest.mark.parametrize(
    "damage",
    [
        "null",
        "list",
        "missing_field",
        "wrong_workspace",
        "wrong_operation",
        "wrong_revision",
        "future_revision",
        "failed",
        "missing_data",
        "invalid_warnings",
        "extra_field",
    ],
)
def test_corrupted_replay_is_a_safe_storage_error_and_preserves_database(stored_operation, damage):
    service, handler, command, committed, database = stored_operation
    changed = committed.copy()
    if damage in ("null", "list"):
        changed = None if damage == "null" else []
    elif damage == "missing_field":
        del changed["warnings"]
    else:
        changed.update(
            {
                "wrong_workspace": {"workspace_id": str(uuid4())},
                "wrong_operation": {"operation_id": str(uuid4())},
                "wrong_revision": {"revision": 0},
                "future_revision": {"revision": 999},
                "failed": {"ok": False},
                "missing_data": {"data": None},
                "invalid_warnings": {"warnings": [123]},
                "extra_field": {"untrusted": True},
            }[damage]
        )
    revision = 999 if damage == "future_revision" else committed["revision"]
    with closing(sqlite3.connect(database)) as db:
        db.execute(
            "UPDATE operations SET result_json=?, committed_revision=? WHERE operation_id=?",
            (json.dumps(changed), revision, command["operation_id"]),
        )
        db.commit()
    contents = database.read_bytes()
    state = service.get_business_state({"workspace_id": command["workspace_id"]})
    replay = handler(command)
    assert isinstance(replay, dict)
    assert replay["ok"] is False
    assert replay["workspace_id"] == command["workspace_id"]
    assert replay["operation_id"] == command["operation_id"]
    assert replay["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert replay["error"]["retryable"] is False
    assert database.read_bytes() == contents
    assert service.get_business_state({"workspace_id": command["workspace_id"]}) == state


def test_valid_replay_returns_original_result_after_later_revisions(stored_operation):
    service, handler, command, committed, database = stored_operation
    later = service.set_production_plan(
        dict(
            workspace_id=command["workspace_id"],
            operation_id=str(uuid4()),
            expected_revision=committed["revision"],
            items=[],
            evidence=dict(
                turn_ref="synthetic-later-plan",
                statement="Confirmo o plano vazio.",
                captured_at="2026-11-13T12:00:00Z",
            ),
        )
    )
    assert later["ok"] and later["revision"] > committed["revision"]
    contents = database.read_bytes()
    assert handler(command) == committed
    assert database.read_bytes() == contents


@pytest.mark.anyio
async def test_corrupted_replay_remains_a_structured_error_over_stdio(stored_operation, tmp_path):
    _, handler, command, _, database = stored_operation
    with closing(sqlite3.connect(database)) as db:
        db.execute(
            "UPDATE operations SET result_json='null' WHERE operation_id=?",
            (command["operation_id"],),
        )
        db.commit()
    contents = database.read_bytes()
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    with anyio.fail_after(20):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                replay = await session.call_tool(handler.__name__, command)
                assert replay.is_error is True
                assert replay.structured_content["error"]["code"] == "STORAGE_UNAVAILABLE"
                assert replay.structured_content["operation_id"] == command["operation_id"]
                assert replay.structured_content["data"] is None
                await session.send_ping()
    assert database.read_bytes() == contents
