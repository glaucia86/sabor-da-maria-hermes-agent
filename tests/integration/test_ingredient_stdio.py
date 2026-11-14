"""S04 atravessa transporte MCP real e dois processos sobre SQLite temporário."""

import json
import sys
from uuid import uuid4

import anyio
import pytest
from conftest import OPERATOR_STDIO_ARGS
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_clarification_overlay_acceptance_and_replay_over_stdio(clarification, tmp_path):
    service, workspace, command, candidate, chocolate, original, path, database = clarification
    source_bytes = path.read_bytes()
    server = StdioServerParameters(
        command=sys.executable,
        args=OPERATOR_STDIO_ARGS,
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    revision = 0
    with anyio.fail_after(30):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {t.name: t for t in (await session.list_tools()).tools}
                for tool in ("resolve_recipe_ingredient", "record_ingredient_conversion"):
                    assert tools[tool].input_schema["additionalProperties"] is False
                    assert tools[tool].annotations.read_only_hint is False
                    assert tools[tool].annotations.idempotent_hint is True

                async def call(tool, **payload):
                    nonlocal revision
                    result = await session.call_tool(
                        tool,
                        dict(
                            workspace_id=workspace,
                            operation_id=str(uuid4()),
                            expected_revision=revision,
                        )
                        | payload,
                    )
                    assert result.is_error is False, result.structured_content
                    assert json.loads(result.content[0].text) == result.structured_content
                    revision = result.structured_content["revision"]
                    return result.structured_content["data"]

                evidence = dict(
                    turn_ref="synthetic-human-s04",
                    statement="Confirmo esta produção.",
                    captured_at="2026-11-12T12:00:00Z",
                )
                candidate["ingredients"][1]["ingredient_id"] = None
                recipe = (await call("register_recipe_candidate", candidate=candidate))["candidate"]
                resolved = await call(
                    "resolve_recipe_ingredient",
                    recipe_id=recipe["id"],
                    recipe_version=1,
                    line_id=recipe["ingredients"][1]["line_id"],
                    existing_ingredient_id=chocolate["id"],
                    evidence=evidence | {"statement": "A cobertura é a de chocolate da despensa."},
                )
                item = (
                    await call(
                        "set_production_plan",
                        items=[
                            dict(
                                recipe_id=recipe["id"],
                                recipe_version=resolved["candidate"]["version"],
                                position=0,
                                batches=1,
                            )
                        ],
                        evidence=evidence,
                    )
                )["plan"]["items"][0]
                before = (
                    await session.call_tool("evaluate_purchase_plan", {"workspace_id": workspace})
                ).structured_content
                assert before["data"]["purchase_status"] == "PENDING"
                overlay_request = dict(
                    workspace_id=workspace,
                    operation_id=str(uuid4()),
                    expected_revision=revision,
                    ingredient_id=chocolate["id"],
                    from_unit="un",
                    to_unit="g",
                    factor="1000",
                    scope="HISTORICAL_PACKAGE",
                    context="Embalagem comprada desta fotografia",
                    evidence=evidence
                    | {"statement": "Confirmo: a embalagem comprada tinha 1000 g."},
                )
                refused = await session.call_tool(
                    "record_ingredient_conversion", overlay_request | {"factor": 1000}
                )
                assert refused.is_error is True
                assert refused.structured_content["error"]["code"] == "VALIDATION_ERROR"
                overlay = (
                    await session.call_tool("record_ingredient_conversion", overlay_request)
                ).structured_content
                assert overlay["ok"], overlay
                revision = overlay["revision"]
                await call(
                    "record_recipe_feedback",
                    recipe_id=recipe["id"],
                    feedback="INTERESTED",
                    evidence=evidence,
                )
                evaluation = (
                    await session.call_tool("evaluate_purchase_plan", {"workspace_id": workspace})
                ).structured_content["data"]
                assert evaluation["purchase_status"] == "CONFIRMED"
                assert evaluation["fingerprint"] != before["data"]["fingerprint"]
                accepted = await call(
                    "accept_recipe",
                    recipe_id=recipe["id"],
                    plan_item_id=item["plan_item_id"],
                    evaluation_id=evaluation["evaluation_id"],
                    evidence=evidence | {"statement": "Aceito este prato."},
                )
                assert accepted["acceptance"]["validity"] == "VALID"
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                replay = (
                    await session.call_tool("record_ingredient_conversion", overlay_request)
                ).structured_content
                assert replay == overlay
                snapshot = (
                    await session.call_tool("get_inventory_snapshot", {"workspace_id": workspace})
                ).structured_content["data"]
                assert snapshot == original
                state = (
                    await session.call_tool("get_business_state", {"workspace_id": workspace})
                ).structured_content
                assert state["revision"] == revision
                assert state["data"]["acceptances"][0]["validity"] == "VALID"
                assert len(state["data"]["ingredient_conversions"]) == 1
    assert path.read_bytes() == source_bytes
