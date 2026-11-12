"""S03 em processos MCP reais, com banco sintético temporário."""

import json
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
async def test_pricing_guards_choice_and_replay_after_process_restart(pricing_workspace, tmp_path):
    service, workspace, recipe, acceptance, _, database = pricing_workspace()
    meta = dict(
        workspace_id=workspace,
        expected_revision=service.get_business_state({"workspace_id": workspace})["revision"],
    )
    request = meta | dict(
        operation_id=str(uuid4()), recipe_id=recipe["id"], acceptance_id=acceptance["id"]
    )
    with anyio.fail_after(30):
        async with client(database, tmp_path) as session:
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert {"calculate_pricing_scenarios", "save_menu_decision"} <= tools.keys()
            assert tools["calculate_pricing_scenarios"].annotations.read_only_hint is False
            assert tools["calculate_pricing_scenarios"].annotations.idempotent_hint is True
            assert tools["save_menu_decision"].input_schema["additionalProperties"] is False
            refused = await session.call_tool(
                "calculate_pricing_scenarios", request | {"acceptance_id": str(uuid4())}
            )
            assert refused.is_error is True
            assert refused.structured_content["error"]["code"] == "ACCEPTANCE_REQUIRED"
            calculated = await session.call_tool("calculate_pricing_scenarios", request)
            assert calculated.is_error is False
            assert json.loads(calculated.content[0].text) == calculated.structured_content
            calculation = calculated.structured_content["data"]["calculation"]
            assert calculation["minimum"]["price"] == "11.12"
            choice = dict(
                workspace_id=workspace,
                expected_revision=calculated.structured_content["revision"],
                operation_id=str(uuid4()),
                recipe_id=recipe["id"],
                acceptance_id=acceptance["id"],
                calculation_id=calculation["id"],
                custom_price="11.11",
                evidence=dict(
                    turn_ref="synthetic-user-choice",
                    statement="Escolho o preço de R$ 11.11.",
                    captured_at="2026-11-11T00:00:00Z",
                ),
            )
            refused = await session.call_tool("save_menu_decision", choice)
            assert refused.is_error is True
            assert refused.structured_content["error"]["code"] == "PRICE_BELOW_MINIMUM"
            choice.pop("custom_price")
            choice.update(
                scenario_id="M20", evidence=choice["evidence"] | {"statement": "Escolho M20."}
            )
            for extra in (
                {"cmv": "0"},
                {"approved": True},
                {"custom_price": "20.00"},
                {"target_margin": "0.90"},
            ):
                invalid = await session.call_tool("save_menu_decision", choice | extra)
                assert invalid.is_error is True
                assert invalid.structured_content["error"]["code"] == "VALIDATION_ERROR"
            saved = await session.call_tool("save_menu_decision", choice)
            assert saved.is_error is False
            original = saved.structured_content
        async with client(database, tmp_path) as session:
            assert (
                await session.call_tool("calculate_pricing_scenarios", request)
            ).structured_content == calculated.structured_content
            assert (
                await session.call_tool("save_menu_decision", choice)
            ).structured_content == original
            conflict = await session.call_tool(
                "save_menu_decision", choice | {"scenario_id": "M30"}
            )
            assert conflict.structured_content["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            state = (
                await session.call_tool("get_business_state", {"workspace_id": workspace})
            ).structured_content
            assert state["revision"] == original["revision"]
            assert state["data"]["menu"] == [original["data"]["decision"]]
            assert state["data"]["acceptances"][0]["validity"] == "VALID"
            assert state["data"]["budget_remaining"] == "80.00"
            # Mudança por ferramenta existente torna o cálculo antigo impróprio para nova decisão.
            changed = await session.call_tool(
                "set_production_plan",
                dict(
                    workspace_id=workspace,
                    expected_revision=state["revision"],
                    operation_id=str(uuid4()),
                    items=[],
                    evidence=choice["evidence"] | {"statement": "Confirmo limpar o plano."},
                ),
            )
            stale = await session.call_tool(
                "save_menu_decision",
                choice
                | dict(
                    operation_id=str(uuid4()),
                    expected_revision=changed.structured_content["revision"],
                ),
            )
            assert stale.is_error is True
            assert stale.structured_content["error"]["code"] == "STALE_EVALUATION"
