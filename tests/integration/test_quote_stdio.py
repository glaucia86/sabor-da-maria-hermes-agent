"""S05: identidade → oferta estimada → seleção → simulação pelo MCP real."""

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
async def test_estimated_complement_roundtrip_and_replay_over_stdio(clarification, tmp_path):
    _, workspace, _, candidate, _, original, path, database = clarification
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
                assert "register_complement_quote" in tools
                assert "confirm_complement_quote" in tools
                tool = tools["register_complement_quote"]
                assert tool.input_schema["additionalProperties"] is False
                assert tool.annotations.read_only_hint is False
                assert tool.annotations.idempotent_hint is True

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
                    turn_ref="synthetic-s05-human",
                    statement="Confirmo esta produção.",
                    captured_at="2026-11-12T12:00:00Z",
                )
                candidate["ingredients"] = candidate["ingredients"][:1]
                candidate["ingredients"][0].update(
                    description="Mel", ingredient_id=None, quantity=dict(value="200", unit="g")
                )
                recipe = (await call("register_recipe_candidate", candidate=candidate))["candidate"]
                resolved = await call(
                    "resolve_recipe_ingredient",
                    recipe_id=recipe["id"],
                    recipe_version=1,
                    line_id=recipe["ingredients"][0]["line_id"],
                    new_ingredient=dict(name="Mel", dimension="g"),
                    evidence=evidence,
                )
                ingredient = resolved["ingredient_id"]
                offer = dict(
                    ingredient_id=ingredient,
                    description="Mel 1000 g — fixture sintética",
                    package_quantity=dict(value="1000", unit="g"),
                    package_price="20.00",
                    purchase_extra_total="0.00",
                    extra_conditions="Retirada grátis da fixture.",
                    supplier="Fornecedor sintético",
                    availability="UNKNOWN",
                    availability_context="Disponibilidade não publicada.",
                    source=candidate["sources"][0],
                )
                request = dict(
                    workspace_id=workspace,
                    operation_id=str(uuid4()),
                    expected_revision=revision,
                    quote=offer,
                )
                for bad, expected in [
                    (
                        offer | {"package_quantity": dict(value="1000", unit="ml")},
                        "UNIT_CONVERSION_REQUIRED",
                    ),
                    (offer | {"status": "CONFIRMED"}, "VALIDATION_ERROR"),
                ]:
                    refused = await session.call_tool(
                        "register_complement_quote", request | {"quote": bad}
                    )
                    assert refused.is_error is True
                    assert refused.structured_content["error"]["code"] == expected
                    assert json.loads(refused.content[0].text) == refused.structured_content
                saved = await session.call_tool("register_complement_quote", request)
                assert saved.is_error is False
                saved_envelope = saved.structured_content
                revision = saved_envelope["revision"]
                quote = saved_envelope["data"]["quote"]
                assert quote["status"] == "ESTIMATED"
                plan = (
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
                        quote_selections=[
                            dict(ingredient_id=ingredient, quote_id=quote["id"], quote_version=1)
                        ],
                        evidence=evidence,
                    )
                )["plan"]
                await call(
                    "record_recipe_feedback",
                    recipe_id=recipe["id"],
                    feedback="INTERESTED",
                    evidence=evidence | {"statement": "Tenho interesse."},
                )
                evaluation = await session.call_tool(
                    "evaluate_purchase_plan", {"workspace_id": workspace}
                )
                assert evaluation.is_error is False
                data = evaluation.structured_content["data"]
                assert data["purchase_status"] == "PENDING"
                assert data["is_simulation"] is True
                assert data["disbursement"] == "20.00"
                assert data["demand"][0]["purchase"]["planned_surplus"] == "800"
                refused = await session.call_tool(
                    "accept_recipe",
                    dict(
                        workspace_id=workspace,
                        operation_id=str(uuid4()),
                        expected_revision=revision,
                        recipe_id=recipe["id"],
                        plan_item_id=plan["items"][0]["plan_item_id"],
                        evaluation_id=data["evaluation_id"],
                        evidence=evidence | {"statement": "Aceito este prato."},
                    ),
                )
                assert refused.is_error is True
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                replay = await session.call_tool("register_complement_quote", request)
                assert replay.structured_content == saved_envelope
                state = (
                    await session.call_tool("get_business_state", {"workspace_id": workspace})
                ).structured_content
                assert state["revision"] == revision
                assert state["data"]["acceptances"] == []
                assert len(state["data"]["complement_quotes"]) == 1
                assert state["data"]["evaluation"] == data
                snapshot = (
                    await session.call_tool("get_inventory_snapshot", {"workspace_id": workspace})
                ).structured_content
                assert snapshot["data"] == original
    assert path.read_bytes() == source_bytes
