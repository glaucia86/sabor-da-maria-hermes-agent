"""S08 pelo transporte real, com SQLite sintético e reinício do servidor."""

import sys
from contextlib import asynccontextmanager
from uuid import uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@asynccontextmanager
async def client(database, cwd):
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=cwd,
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@pytest.mark.anyio
async def test_preference_refusal_replay_and_history_survive_stdio_restart(
    pricing_workspace, tmp_path
):
    service, workspace, recipe, acceptance, command, database = pricing_workspace()
    calculation = command(
        "calculate_pricing_scenarios", recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )["data"]["calculation"]
    choice = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=service.get_business_state({"workspace_id": workspace})["revision"],
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
        evidence=dict(
            turn_ref="synthetic-s08-choice",
            statement="Escolho M20.",
            captured_at="2026-11-13T12:00:00Z",
        ),
    )
    with anyio.fail_after(40):
        async with client(database, tmp_path) as session:
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert "record_user_preferences" in tools
            tool = tools["record_user_preferences"]
            assert tool.annotations.idempotent_hint is True
            assert tool.annotations.read_only_hint is False
            assert tool.input_schema["additionalProperties"] is False
            selected = (await session.call_tool("save_menu_decision", choice)).structured_content
            assert selected["ok"], selected
            request = dict(
                workspace_id=workspace,
                operation_id=str(uuid4()),
                expected_revision=selected["revision"],
                preferences=[
                    dict(
                        category="INGREDIENT",
                        term="Arroz",
                        value="AVOID",
                        evidence=dict(
                            turn_ref="synthetic-s08-refusal",
                            statement="Não quero arroz no cardápio.",
                            captured_at="2026-11-13T12:01:00Z",
                        ),
                    )
                ],
            )
            saved = (await session.call_tool("record_user_preferences", request)).structured_content
            assert saved["ok"], saved
            assert saved["data"]["removed_recipe_ids"] == [recipe["id"]]
            assert saved["data"]["invalidated_calculation_ids"] == [calculation["id"]]
            assert saved["data"]["invalidated_menu_decision_ids"] == [
                selected["data"]["decision"]["id"]
            ]
        async with client(database, tmp_path) as session:
            for tool, payload, original in [
                ("save_menu_decision", choice, selected),
                ("record_user_preferences", request, saved),
            ]:
                replay = await session.call_tool(tool, payload)
                assert replay.structured_content == original
            state = (
                await session.call_tool("get_business_state", {"workspace_id": workspace})
            ).structured_content
            assert state["revision"] == saved["revision"]
            assert state["data"]["plan"]["items"] == []
            assert state["data"]["menu"] == []
            assert state["data"]["preferences"][0]["value"] == "AVOID"
            assert state["data"]["acceptances"][0]["validity"] == "INVALIDATED"
            assert len(state["data"]["menu_decisions"]) == 1
            conflict = await session.call_tool(
                "record_user_preferences", request | {"preferences": []}
            )
            assert conflict.structured_content["error"]["code"] == "VALIDATION_ERROR"
