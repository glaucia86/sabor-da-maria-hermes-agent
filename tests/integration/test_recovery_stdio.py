"""Falhas de transporte/armazenamento observadas pelo cliente MCP oficial."""

import sqlite3
import stat
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import anyio
import pytest
from conftest import OPERATOR_STDIO_ARGS
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError

from dona_maria.bootstrap import bootstrap_workspace


@pytest.mark.anyio
async def test_disconnected_calculation_keeps_acceptance_and_can_resume_with_same_command(
    tmp_path, pricing_workspace
):
    service, workspace, recipe, acceptance, _, database = pricing_workspace()
    before = service.get_business_state({"workspace_id": workspace})
    command = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=before["revision"],
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-X",
            "utf8",
            "-B",
            str(Path(__file__).parents[2] / "evals/stdio_fault.py"),
            "--database",
            str(database),
            "--marker",
            str(tmp_path / "fault.json"),
            "--fault",
            "disconnect-calculation",
        ],
        cwd=tmp_path,
    )
    with anyio.fail_after(20):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                observed = await session.call_tool(
                    "get_business_state", {"workspace_id": workspace}
                )
                assert observed.structured_content == before
                with pytest.raises(MCPError):
                    await session.call_tool("calculate_pricing_scenarios", command)
        assert service.get_business_state({"workspace_id": workspace}) == before
        server.args = OPERATOR_STDIO_ARGS
        server.env = {"DONA_MARIA_DB_PATH": str(database)}
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                recovered = await session.call_tool("calculate_pricing_scenarios", command)
                assert recovered.structured_content["ok"] is True
                assert recovered.structured_content["revision"] == before["revision"] + 1
                replay = await session.call_tool("calculate_pricing_scenarios", command)
                assert replay.structured_content == recovered.structured_content


@pytest.mark.anyio
async def test_read_only_database_refuses_write_and_same_command_recovers(
    tmp_path, pricing_workspace
):
    service, workspace, recipe, acceptance, _, database = pricing_workspace()
    before = service.get_business_state({"workspace_id": workspace})
    contents = database.read_bytes()
    command = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=before["revision"],
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=OPERATOR_STDIO_ARGS,
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    mode = database.stat().st_mode
    try:
        database.chmod(stat.S_IREAD)
        with anyio.fail_after(20):
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    observed = await session.call_tool(
                        "get_business_state", {"workspace_id": workspace}
                    )
                    assert observed.structured_content == before
                    failed = await session.call_tool("calculate_pricing_scenarios", command)
                    assert failed.is_error is True
                    error = failed.structured_content
                    assert error["data"] is None
                    assert error["operation_id"] == command["operation_id"]
                    assert error["error"]["code"] == "STORAGE_UNAVAILABLE"
                    assert error["error"]["retryable"] is False
                    assert error["error"]["next_action"] == "CHECK_STORAGE"
                    assert database.read_bytes() == contents
                    database.chmod(mode)
                    recovered = await session.call_tool("calculate_pricing_scenarios", command)
                    assert recovered.structured_content["ok"] is True
                    assert recovered.structured_content["revision"] == before["revision"] + 1
                    replay = await session.call_tool("calculate_pricing_scenarios", command)
                    assert replay.structured_content == recovered.structured_content
    finally:
        database.chmod(mode)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool",
    [
        "get_business_state",
        "get_inventory_snapshot",
        "evaluate_purchase_plan",
        "evaluate_recipe_feasibility",
    ],
)
async def test_locked_read_is_retryable_and_preserves_state(tmp_path, inventory_file, tool):
    database = tmp_path / "synthetic.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    server = StdioServerParameters(
        command=sys.executable,
        args=OPERATOR_STDIO_ARGS,
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    with anyio.fail_after(20):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                arguments = {"workspace_id": workspace}
                before = await session.call_tool("get_business_state", arguments)
                query = arguments
                if tool == "evaluate_recipe_feasibility":
                    query = arguments | {"recipe_id": str(uuid4()), "plan_item_id": str(uuid4())}
                with closing(sqlite3.connect(database)) as blocker:
                    blocker.execute("BEGIN EXCLUSIVE")
                    try:
                        failed = await session.call_tool(tool, query)
                    finally:
                        blocker.rollback()
                assert failed.is_error is True
                assert failed.structured_content["error"]["code"] == "STORAGE_BUSY"
                assert failed.structured_content["error"]["retryable"] is True
                recovered = await session.call_tool("get_business_state", arguments)
                assert recovered.structured_content == before.structured_content


@pytest.mark.anyio
async def test_lost_success_after_commit_is_resolved_by_same_command_after_restart(
    tmp_path, pricing_workspace
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    before = service.get_business_state({"workspace_id": workspace})
    inventory = service.get_inventory_snapshot({"workspace_id": workspace})
    payload = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=before["revision"],
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence=dict(
            turn_ref="synthetic-user-price",
            statement="Escolho M20.",
            captured_at="2026-11-13T12:00:00Z",
        ),
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-X",
            "utf8",
            "-B",
            str(Path(__file__).parents[2] / "evals/stdio_fault.py"),
            "--database",
            str(database),
            "--marker",
            str(tmp_path / "fault.json"),
        ],
        cwd=tmp_path,
    )
    with anyio.fail_after(30):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                with pytest.raises(MCPError, match="Resultado incerto"):
                    await session.call_tool("save_menu_decision", payload)
                observed = await session.call_tool(
                    "get_business_state", {"workspace_id": workspace}
                )
                assert observed.structured_content["revision"] == before["revision"] + 1
                assert len(observed.structured_content["data"]["menu_decisions"]) == 1
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                replay = await session.call_tool("save_menu_decision", payload)
                assert replay.structured_content["ok"] is True
                assert replay.structured_content["revision"] == before["revision"] + 1
                assert (
                    service.get_business_state({"workspace_id": workspace})
                    == observed.structured_content
                )
                assert (
                    service.get_inventory_snapshot({"workspace_id": workspace})["data"]
                    == inventory["data"]
                )
                conflict = await session.call_tool(
                    "save_menu_decision", payload | {"scenario_id": "M30"}
                )
                assert conflict.structured_content["error"]["code"] == "IDEMPOTENCY_CONFLICT"
                other_tool = await session.call_tool(
                    "calculate_pricing_scenarios",
                    {
                        key: payload[key]
                        for key in (
                            "workspace_id",
                            "operation_id",
                            "expected_revision",
                            "recipe_id",
                            "acceptance_id",
                        )
                    },
                )
                assert other_tool.structured_content["error"]["code"] == "IDEMPOTENCY_CONFLICT"
                assert (
                    service.get_business_state({"workspace_id": workspace})
                    == observed.structured_content
                )
