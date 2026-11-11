"""Guards S02 por processo MCP oficial, sem host/modelo simulado."""

import json
import sqlite3
import sys
from contextlib import closing
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
async def test_direct_acceptance_cannot_bypass_gaps_and_mcp_exposes_safe_contracts(
    tmp_path,
    inventory_file,
    recipe_candidate,
):
    database = tmp_path / "stdio.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    evidence = dict(
        turn_ref="fixture-human-1",
        statement="Aceito este prato.",
        captured_at="2026-11-11T00:00:00Z",
    )
    with anyio.fail_after(20):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                assert {
                    "record_recipe_feedback",
                    "record_kitchen_facts",
                    "set_production_plan",
                    "evaluate_recipe_feasibility",
                    "evaluate_purchase_plan",
                    "accept_recipe",
                } <= tools.keys()
                assert tools["accept_recipe"].annotations.read_only_hint is False
                assert tools["evaluate_purchase_plan"].annotations.read_only_hint is True
                assert tools["accept_recipe"].input_schema["additionalProperties"] is False
                assert tools["accept_recipe"].output_schema["additionalProperties"] is False
                registered = (
                    await session.call_tool(
                        "register_recipe_candidate",
                        dict(
                            workspace_id=workspace,
                            operation_id=str(uuid4()),
                            expected_revision=0,
                            candidate=recipe_candidate,
                        ),
                    )
                ).structured_content
                recipe = registered["data"]["candidate"]
                plan = (
                    await session.call_tool(
                        "set_production_plan",
                        dict(
                            workspace_id=workspace,
                            operation_id=str(uuid4()),
                            expected_revision=1,
                            items=[
                                dict(
                                    recipe_id=recipe["id"], recipe_version=1, position=0, batches=1
                                )
                            ],
                            evidence=evidence | {"statement": "Confirmo um lote para avaliação."},
                        ),
                    )
                ).structured_content
                assert plan["ok"] is True
                before = (
                    await session.call_tool("get_business_state", {"workspace_id": workspace})
                ).structured_content
                evaluation = (
                    await session.call_tool("evaluate_purchase_plan", {"workspace_id": workspace})
                ).structured_content
                command = dict(
                    workspace_id=workspace,
                    operation_id=str(uuid4()),
                    expected_revision=2,
                    recipe_id=recipe["id"],
                    plan_item_id=plan["data"]["plan"]["items"][0]["plan_item_id"],
                    evaluation_id=evaluation["data"]["evaluation_id"],
                    evidence=evidence,
                )
                refused = await session.call_tool("accept_recipe", command)
                assert refused.is_error is True
                assert refused.structured_content["error"]["code"] == "MISSING_INFORMATION"
                assert json.loads(refused.content[0].text) == refused.structured_content
                for extra in ("approved", "status", "remaining_budget", "cmv"):
                    invalid = await session.call_tool("accept_recipe", command | {extra: True})
                    assert invalid.is_error is True
                    assert invalid.structured_content["error"]["code"] == "VALIDATION_ERROR"
                for field in ("turn_ref", "statement"):
                    invalid = await session.call_tool(
                        "record_kitchen_facts",
                        dict(
                            workspace_id=workspace,
                            operation_id=str(uuid4()),
                            expected_revision=2,
                            facts=[
                                dict(
                                    category="EQUIPMENT",
                                    key="oven",
                                    value=True,
                                    evidence=evidence | {field: "\t\u00a0 "},
                                )
                            ],
                        ),
                    )
                    assert invalid.is_error is True
                    assert invalid.structured_content["error"]["code"] == "VALIDATION_ERROR"
                after = (
                    await session.call_tool("get_business_state", {"workspace_id": workspace})
                ).structured_content
                assert after == before


@pytest.mark.parametrize("failure_point", [None, "workspaces", "decisions", "operations", "commit"])
@pytest.mark.anyio
async def test_acceptance_commits_atomically_and_replays_after_restart(
    tmp_path,
    inventory_file,
    recipe_candidate,
    failure_point,
):
    database = tmp_path / "acceptance.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    evidence = dict(
        turn_ref="synthetic-turn-1",
        statement="Confirmo um lote desta receita.",
        captured_at="2026-11-11T00:00:00Z",
    )
    source = recipe_candidate["sources"][0]
    recipe_candidate.pop("yield_gap")
    recipe_candidate.pop("context_gap")
    recipe_candidate.update(
        yield_per_batch=dict(servings_per_batch=5, sale_unit_label="porção", source=source),
        operational_context="Fixture sem prazo máximo ou armazenamento posterior.",
        context_source=source,
        requirements=[
            dict(
                category="EQUIPMENT",
                key="stove",
                condition="PRESENT",
                reason="O método usa fogão.",
                source=source,
            )
        ],
        category_reviews=[
            dict(
                category=c,
                requirement_keys=["stove"] if c == "EQUIPMENT" else [],
                method_version=1,
                source=source,
                not_applicable_reason=None
                if c == "EQUIPMENT"
                else "Método sintético não exige condição específica nesta categoria.",
            )
            for c in ("EQUIPMENT", "SKILL", "OPERATION")
        ],
    )
    revision = 0
    with anyio.fail_after(30):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def write_command(tool, **payload):
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
                    revision = result.structured_content["revision"]
                    return result.structured_content["data"]

                inventory = (
                    await session.call_tool("get_inventory_snapshot", {"workspace_id": workspace})
                ).structured_content["data"]
                recipe_candidate["ingredients"][0]["ingredient_id"] = inventory["items"][0]["id"]
                recipe = (
                    await write_command("register_recipe_candidate", candidate=recipe_candidate)
                )["candidate"]
                await write_command(
                    "record_recipe_feedback",
                    recipe_id=recipe["id"],
                    feedback="INTERESTED",
                    evidence=evidence | {"statement": "Tenho interesse nesta receita."},
                )
                await write_command(
                    "record_kitchen_facts",
                    facts=[
                        dict(
                            category="EQUIPMENT",
                            key="stove",
                            value=True,
                            evidence=evidence | {"statement": "Tenho fogão disponível."},
                        )
                    ],
                )
                plan = (
                    await write_command(
                        "set_production_plan",
                        items=[
                            dict(recipe_id=recipe["id"], recipe_version=1, position=0, batches=1)
                        ],
                        evidence=evidence,
                    )
                )["plan"]
                evaluation = (
                    await session.call_tool("evaluate_purchase_plan", {"workspace_id": workspace})
                ).structured_content["data"]
                command = dict(
                    workspace_id=workspace,
                    expected_revision=revision,
                    operation_id=str(uuid4()),
                    recipe_id=recipe["id"],
                    plan_item_id=plan["items"][0]["plan_item_id"],
                    evaluation_id=evaluation["evaluation_id"],
                    evidence=evidence | {"statement": "Aceito este prato."},
                )
                before = (
                    await session.call_tool("get_business_state", {"workspace_id": workspace})
                ).structured_content
                if failure_point:
                    # Falha injetada na fronteira SQLite; assertions pela API pública.
                    with closing(sqlite3.connect(database)) as db:
                        if failure_point == "commit":
                            db.execute(
                                "CREATE TABLE fault_gate (id TEXT "
                                "REFERENCES inventory_snapshots(id) DEFERRABLE INITIALLY DEFERRED)"
                            )
                            db.execute(
                                "CREATE TRIGGER inject_fault AFTER INSERT ON operations BEGIN "
                                "INSERT INTO fault_gate VALUES ('absent-fixture'); END"
                            )
                        else:
                            event = "UPDATE" if failure_point == "workspaces" else "INSERT"
                            db.execute(
                                f"CREATE TRIGGER inject_fault BEFORE {event} ON {failure_point} "
                                "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
                            )
                    failed = await session.call_tool("accept_recipe", command)
                    assert failed.is_error is True
                    assert failed.structured_content["error"]["code"] == "STORAGE_UNAVAILABLE"
                    unchanged = (
                        await session.call_tool("get_business_state", {"workspace_id": workspace})
                    ).structured_content
                    assert unchanged == before
                    with closing(sqlite3.connect(database)) as db:
                        db.execute("DROP TRIGGER inject_fault")
                accepted = await session.call_tool("accept_recipe", command)
                assert accepted.is_error is False
                assert accepted.structured_content["revision"] == revision + 1
                assert accepted.structured_content["data"]["acceptance"]["validity"] == "VALID"
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                replay = await session.call_tool("accept_recipe", command)
                assert replay.structured_content == accepted.structured_content
                conflict = await session.call_tool(
                    "accept_recipe", command | {"evidence": evidence}
                )
                assert conflict.structured_content["error"]["code"] == "IDEMPOTENCY_CONFLICT"
                state = (
                    await session.call_tool("get_business_state", {"workspace_id": workspace})
                ).structured_content
                assert len(state["data"]["acceptances"]) == 1
                assert state["data"]["acceptances"][0]["validity"] == "VALID"
                assert state["data"]["budget_remaining"] == "80.00"
                final_inventory = (
                    await session.call_tool("get_inventory_snapshot", {"workspace_id": workspace})
                ).structured_content["data"]
                assert final_inventory == inventory
