import json
import sqlite3
import sys
from contextlib import closing
from copy import deepcopy
from uuid import uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from dona_maria.bootstrap import bootstrap_workspace


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_locally_imported_workspace_can_be_resumed_over_mcp(tmp_path, inventory_file):
    database = tmp_path / "state.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    with anyio.fail_after(15):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_business_state",
                    {
                        "workspace_id": created["workspace_id"],
                    },
                )

    state = result.structured_content
    assert result.is_error is False
    assert state["ok"] is True
    assert state["revision"] == 0
    assert state["data"]["budget_initial"] == "80.00"
    assert state["data"]["budget_remaining"] == "80.00"
    assert state["data"]["candidates"] == []
    assert state["data"]["inventory_snapshot_id"] == created["snapshot_id"]


@pytest.mark.anyio
async def test_inventory_can_be_filtered_without_changing_the_snapshot(tmp_path, inventory_file):
    database = tmp_path / "state.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    with anyio.fail_after(15):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                arguments = {"workspace_id": created["workspace_id"]}
                result = await session.call_tool("get_inventory_snapshot", arguments)
                item = result.structured_content["data"]["items"][0]
                filtered = await session.call_tool(
                    "get_inventory_snapshot",
                    arguments
                    | {
                        "ingredient_ids": [item["id"]],
                    },
                )
                assert filtered.structured_content == result.structured_content

    assert item["name_normalized"] == "arroz"
    assert item["unit_cost"] == "0.00498"
    assert item["stock_quantity_base"] == "5000"
    assert result.structured_content["revision"] == 0


@pytest.mark.anyio
async def test_incomplete_candidate_is_registered_and_recovered_after_server_restart(
    tmp_path, inventory_file, recipe_candidate
):
    database = tmp_path / "state.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    arguments = {
        "workspace_id": created["workspace_id"],
        "operation_id": str(uuid4()),
        "expected_revision": 0,
        "candidate": recipe_candidate,
    }
    with anyio.fail_after(20):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                inventory_before = await session.call_tool(
                    "get_inventory_snapshot",
                    {
                        "workspace_id": created["workspace_id"],
                    },
                )
                result = await session.call_tool("register_recipe_candidate", arguments)
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resumed = await session.call_tool(
                    "get_business_state",
                    {
                        "workspace_id": created["workspace_id"],
                    },
                )
                inventory_after = await session.call_tool(
                    "get_inventory_snapshot",
                    {
                        "workspace_id": created["workspace_id"],
                    },
                )
    saved = result.structured_content
    assert saved["ok"] is True
    assert saved["revision"] == 1
    candidate = saved["data"]["candidate"]
    assert candidate["complete"] is False
    assert "Fonte não informa rendimento." in candidate["gaps"]
    assert candidate["interest"] == "UNDECIDED"
    assert candidate["category_status"] == {
        "EQUIPMENT": "UNREVIEWED",
        "SKILL": "UNREVIEWED",
        "OPERATION": "UNREVIEWED",
    }
    assert resumed.structured_content["data"]["candidates"] == [candidate]
    assert inventory_after.structured_content["data"] == inventory_before.structured_content["data"]
    assert resumed.structured_content["data"]["budget_remaining"] == "80.00"


@pytest.mark.anyio
async def test_replay_does_not_duplicate_and_recipe_revision_requires_current_versions(
    tmp_path, inventory_file, recipe_candidate
):
    created = bootstrap_workspace(
        tmp_path / "state.sqlite3", inventory_file, allowed_directory=tmp_path
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(tmp_path / "state.sqlite3")},
        cwd=tmp_path,
    )
    command = {
        "workspace_id": created["workspace_id"],
        "operation_id": str(uuid4()),
        "expected_revision": 0,
        "candidate": recipe_candidate,
    }
    with anyio.fail_after(20):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                first = (
                    await session.call_tool("register_recipe_candidate", command)
                ).structured_content
                replay = (
                    await session.call_tool("register_recipe_candidate", command)
                ).structured_content
                assert replay == first
                changed = recipe_candidate | {"title": "Revisão — fixture offline"}
                conflict = await session.call_tool(
                    "register_recipe_candidate", command | {"candidate": changed}
                )
                assert conflict.structured_content["error"]["code"] == "IDEMPOTENCY_CONFLICT"
                revision_command = command | {
                    "operation_id": str(uuid4()),
                    "expected_revision": 1,
                    "candidate": changed,
                    "recipe_id": first["data"]["candidate"]["id"],
                    "expected_recipe_version": 1,
                }
                revised = (
                    await session.call_tool("register_recipe_candidate", revision_command)
                ).structured_content
                assert revised["ok"] is True
                assert revised["revision"] == 2
                assert revised["data"]["candidate"]["version"] == 2
                stale = await session.call_tool(
                    "register_recipe_candidate",
                    revision_command
                    | {
                        "operation_id": str(uuid4()),
                        "expected_revision": 2,
                    },
                )
                assert stale.structured_content["error"]["code"] == "STALE_REVISION"
                state = (
                    await session.call_tool(
                        "get_business_state",
                        {
                            "workspace_id": created["workspace_id"],
                        },
                    )
                ).structured_content
    assert state["revision"] == 2
    assert state["data"]["candidates"] == [revised["data"]["candidate"]]


@pytest.mark.anyio
async def test_candidate_identity_is_validated_against_its_workspace(
    tmp_path, inventory_file, recipe_candidate
):
    created = bootstrap_workspace(
        tmp_path / "state.sqlite3", inventory_file, allowed_directory=tmp_path
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(tmp_path / "state.sqlite3")},
        cwd=tmp_path,
    )
    with anyio.fail_after(15):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for ingredient_id, unit, code in [
                    (str(uuid4()), "g", "NOT_FOUND"),
                ]:
                    candidate = deepcopy(recipe_candidate)
                    candidate["ingredients"][0].update(
                        ingredient_id=ingredient_id, quantity={"value": "100", "unit": unit}
                    )
                    result = await session.call_tool(
                        "register_recipe_candidate",
                        {
                            "workspace_id": created["workspace_id"],
                            "operation_id": str(uuid4()),
                            "expected_revision": 0,
                            "candidate": candidate,
                        },
                    )
                    assert result.structured_content["error"]["code"] == code
                state = (
                    await session.call_tool(
                        "get_business_state",
                        {
                            "workspace_id": created["workspace_id"],
                        },
                    )
                ).structured_content
    assert state["revision"] == 0
    assert state["data"]["candidates"] == []


@pytest.mark.anyio
async def test_untrusted_candidate_fields_and_missing_sources_cannot_mutate_state(
    tmp_path, inventory_file, recipe_candidate
):
    created = bootstrap_workspace(
        tmp_path / "state.sqlite3", inventory_file, allowed_directory=tmp_path
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(tmp_path / "state.sqlite3")},
        cwd=tmp_path,
    )
    cases = []
    candidate = deepcopy(recipe_candidate)
    candidate["ingredients"][0]["line_id"] = str(uuid4())
    cases.append((candidate, "VALIDATION_ERROR"))
    cases.extend(
        (recipe_candidate | {key: value}, "VALIDATION_ERROR")
        for key, value in [
            ("complete", True),
            ("approved", True),
            ("remaining_budget", "999.00"),
        ]
    )
    cases.append((recipe_candidate | {"sources": []}, "SOURCE_REQUIRED"))
    for value in [100, True, "0", "1e2", "NaN"]:
        candidate = deepcopy(recipe_candidate)
        candidate["ingredients"][0]["quantity"]["value"] = value
        cases.append((candidate, "VALIDATION_ERROR"))
    candidate = deepcopy(recipe_candidate)
    candidate["sources"][0]["url"] = "file:///private"
    cases.append((candidate, "VALIDATION_ERROR"))
    for url in [
        "ftp://example.org/receita",
        "javascript:alert(1)",
        "https://example.org/" + "x" * 2048,
        "https://synthetic-user:synthetic-password@example.org/receita",
        "https://synthetic-user@example.org/receita",
        "https://:synthetic-password@example.org/receita",
    ]:
        candidate = deepcopy(recipe_candidate)
        candidate["sources"][0]["url"] = url
        cases.append((candidate, "VALIDATION_ERROR"))
    for field, value in [("title", "x" * 201), ("excerpt", "x" * 4001)]:
        candidate = deepcopy(recipe_candidate)
        candidate["sources"][0][field] = value
        cases.append((candidate, "VALIDATION_ERROR"))
    cases.append((recipe_candidate | {"method": "x" * 12001}, "VALIDATION_ERROR"))
    with anyio.fail_after(20):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for payload, code in cases:
                    result = await session.call_tool(
                        "register_recipe_candidate",
                        {
                            "workspace_id": created["workspace_id"],
                            "operation_id": str(uuid4()),
                            "expected_revision": 0,
                            "candidate": payload,
                        },
                    )
                    assert result.is_error is True
                    assert result.structured_content["error"]["code"] == code
                state = (
                    await session.call_tool(
                        "get_business_state",
                        {
                            "workspace_id": created["workspace_id"],
                        },
                    )
                ).structured_content
    assert state["revision"] == 0
    assert state["data"]["candidates"] == []


@pytest.mark.parametrize("failure_point", ["workspaces", "decisions", "operations", "commit"])
@pytest.mark.anyio
async def test_failed_transaction_never_confirms_and_can_be_retried_without_partial_state(
    tmp_path, inventory_file, recipe_candidate, failure_point
):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    # Injeção na fronteira SQLite; resultados são observados somente pela API MCP.
    with closing(sqlite3.connect(database)) as db:
        if failure_point == "commit":
            db.execute(
                "CREATE TABLE fault_gate (id TEXT REFERENCES inventory_snapshots(id) "
                "DEFERRABLE INITIALLY DEFERRED)"
            )
            db.execute(
                "CREATE TRIGGER inject_fault AFTER INSERT ON operations BEGIN "
                "INSERT INTO fault_gate VALUES ('absent-synthetic-id'); END"
            )
        else:
            event = "UPDATE" if failure_point == "workspaces" else "INSERT"
            db.execute(
                f"CREATE TRIGGER inject_fault BEFORE {event} ON {failure_point} "
                "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
            )
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    command = {
        "workspace_id": created["workspace_id"],
        "operation_id": str(uuid4()),
        "expected_revision": 0,
        "candidate": recipe_candidate,
    }
    with anyio.fail_after(20):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                failed = (
                    await session.call_tool("register_recipe_candidate", command)
                ).structured_content
                assert failed["ok"] is False
                assert failed["data"] is None
                assert failed["error"]["code"] == "STORAGE_UNAVAILABLE"
                state = (
                    await session.call_tool(
                        "get_business_state",
                        {
                            "workspace_id": created["workspace_id"],
                        },
                    )
                ).structured_content
                assert state["revision"] == 0
                assert state["data"]["candidates"] == []
                with closing(sqlite3.connect(database)) as db:
                    db.execute("DROP TRIGGER inject_fault")
                recovered = await session.call_tool("register_recipe_candidate", command)
                assert recovered.structured_content["ok"] is True
                assert recovered.structured_content["revision"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize("refused", [False, True])
async def test_tool_logs_are_correlated_json_without_recipe_payload(
    tmp_path, inventory_file, recipe_candidate, refused
):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    recipe_candidate["title"] = "SYNTHETIC_PRIVATE_MARKER_MUST_NOT_APPEAR_IN_LOG"
    if refused:
        recipe_candidate["sources"] = []
    operation_id = str(uuid4())
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    log_path = tmp_path / "private-stderr.log"
    with anyio.fail_after(15), log_path.open("w", encoding="utf-8") as log:
        async with stdio_client(server, errlog=log) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "register_recipe_candidate",
                    {
                        "workspace_id": created["workspace_id"],
                        "operation_id": operation_id,
                        "expected_revision": 0,
                        "candidate": recipe_candidate,
                    },
                )
                assert result.structured_content["ok"] is not refused
    text = log_path.read_text("utf-8")
    assert recipe_candidate["title"] not in text
    events = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
    calls = [event for event in events if event.get("event") == "mcp_call"]
    assert len(calls) == 1
    assert calls[0]["correlation_id"] == operation_id
    assert calls[0]["tool"] == "register_recipe_candidate"
    assert calls[0]["result"] == ("SOURCE_REQUIRED" if refused else "SUCCESS")
    assert calls[0]["revision"] == (None if refused else 1)
    assert calls[0]["duration_ms"] >= 0


@pytest.mark.anyio
async def test_locked_storage_returns_retryable_error_with_the_same_operation_id(
    tmp_path, inventory_file, recipe_candidate
):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    operation_id = str(uuid4())
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
                command = {
                    "workspace_id": created["workspace_id"],
                    "operation_id": operation_id,
                    "expected_revision": 0,
                    "candidate": recipe_candidate,
                }
                with closing(sqlite3.connect(database)) as blocker:
                    blocker.execute("BEGIN IMMEDIATE")
                    failed = (
                        await session.call_tool("register_recipe_candidate", command)
                    ).structured_content
                    blocker.rollback()
                assert failed["ok"] is False
                assert failed["error"]["code"] == "STORAGE_BUSY"
                assert failed["error"]["retryable"] is True
                assert failed["operation_id"] == operation_id
                recovered = await session.call_tool("register_recipe_candidate", command)
                assert recovered.structured_content["revision"] == 1


@pytest.mark.anyio
async def test_two_clients_cannot_commit_the_same_workspace_revision(
    tmp_path, inventory_file, recipe_candidate
):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    results = []

    async def register():
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "register_recipe_candidate",
                    {
                        "workspace_id": created["workspace_id"],
                        "operation_id": str(uuid4()),
                        "expected_revision": 0,
                        "candidate": recipe_candidate,
                    },
                )
                results.append(result.structured_content)

    with anyio.fail_after(20):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(register)
            tasks.start_soon(register)
    assert sum(result["ok"] for result in results) == 1
    assert [result["error"]["code"] for result in results if not result["ok"]] == ["STALE_REVISION"]


@pytest.mark.anyio
async def test_missing_measure_and_unknown_requirement_remain_explicit(
    tmp_path, inventory_file, recipe_candidate
):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    ingredient = recipe_candidate["ingredients"][0]
    ingredient["quantity"] = None
    ingredient["quantity_gap"] = "Medida a gosto exige esclarecimento."
    ingredient["original_measure"].update(
        value=None, raw_text="Arroz a gosto", unit_label="a gosto"
    )
    recipe_candidate["requirements"] = [
        {
            "category": "EQUIPMENT",
            "key": "panela",
            "condition": "PRESENT",
            "value": True,
            "reason": "Necessária para o método da fixture.",
            "source": recipe_candidate["sources"][0],
        }
    ]
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    with anyio.fail_after(15):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "register_recipe_candidate",
                    {
                        "workspace_id": created["workspace_id"],
                        "operation_id": str(uuid4()),
                        "expected_revision": 0,
                        "candidate": recipe_candidate,
                    },
                )
    candidate = result.structured_content["data"]["candidate"]
    assert candidate["complete"] is False
    assert candidate["ingredients"][0]["quantity"] is None
    assert "Medida a gosto exige esclarecimento." in candidate["gaps"]
    assert candidate["requirements"][0]["status"] == "UNKNOWN"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "retrieved_at,expected",
    [
        ("2026-11-11T15:00:00+03:00", "2026-11-11T12:00:00Z"),
        (1794427200, None),
        ("2026-11-11T12:00:00", None),
    ],
)
async def test_source_retrieval_time_is_persisted_in_utc(
    tmp_path, inventory_file, recipe_candidate, retrieved_at, expected
):
    database = tmp_path / "synthetic.sqlite3"
    created = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    recipe_candidate["sources"][0]["retrieved_at"] = retrieved_at
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    with anyio.fail_after(15):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "register_recipe_candidate",
                    {
                        "workspace_id": created["workspace_id"],
                        "operation_id": str(uuid4()),
                        "expected_revision": 0,
                        "candidate": recipe_candidate,
                    },
                )
    if expected is None:
        assert result.structured_content["error"]["code"] == "VALIDATION_ERROR"
    else:
        candidate = result.structured_content["data"]["candidate"]
        assert candidate["sources"][0]["retrieved_at"] == expected
