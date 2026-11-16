"""S07: dois pratos, invalidação/reaceite e retirada pelo MCP stdio real."""

import sys
from decimal import Decimal
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
async def test_shared_plan_order_reacceptance_and_removal_survive_stdio_restart(
    shared_plan, tmp_path
):
    p = shared_plan()
    server = StdioServerParameters(
        command=sys.executable,
        args=OPERATOR_STDIO_ARGS,
        env={"DONA_MARIA_DB_PATH": str(p["database"])},
        cwd=tmp_path,
    )
    revision = p["service"].get_business_state({"workspace_id": p["workspace"]})["revision"]
    with anyio.fail_after(45):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def call(tool, *, error=None, **payload):
                    nonlocal revision
                    result = await session.call_tool(
                        tool,
                        dict(
                            workspace_id=p["workspace"],
                            operation_id=str(uuid4()),
                            expected_revision=revision,
                        )
                        | payload,
                    )
                    body = result.structured_content
                    assert result.is_error is bool(error), body
                    if error:
                        assert body["error"]["code"] == error
                    else:
                        revision = body["revision"]
                    return body["data"]

                async def current():
                    result = await session.call_tool(
                        "get_business_state", {"workspace_id": p["workspace"]}
                    )
                    assert not result.is_error, result.structured_content
                    assert result.structured_content["revision"] == revision
                    return result.structured_content["data"]

                async def plan(order):
                    return await call(
                        "set_production_plan",
                        items=[
                            dict(
                                recipe_id=p["recipes"][i]["id"],
                                recipe_version=1,
                                position=position,
                                batches=1,
                            )
                            for position, i in enumerate(order)
                        ],
                        quote_selections=[
                            dict(
                                ingredient_id=p["quote"]["ingredient_id"],
                                quote_id=p["quote"]["id"],
                                quote_version=1,
                            )
                        ],
                        evidence=p["evidence"],
                    )

                async def choose_all():
                    state = await current()
                    previous = next(
                        (f for f in state["kitchen_facts"] if f["key"] == "production_arrangement"),
                        None,
                    )
                    await call(
                        "record_kitchen_facts",
                        facts=[
                            dict(
                                category="OPERATION",
                                key="production_arrangement",
                                value="SEQUENTIAL",
                                context=f"{state['plan']['id']}:{state['plan']['version']}",
                                replaces_fact_id=previous["id"] if previous else None,
                                evidence=p["evidence"],
                            )
                        ],
                    )
                    costs = []
                    for item in state["plan"]["items"]:
                        evaluated = await session.call_tool(
                            "evaluate_purchase_plan", {"workspace_id": p["workspace"]}
                        )
                        accepted = (
                            await call(
                                "accept_recipe",
                                recipe_id=item["recipe_id"],
                                plan_item_id=item["plan_item_id"],
                                evaluation_id=evaluated.structured_content["data"]["evaluation_id"],
                                evidence=p["evidence"] | {"statement": "Aceito este prato."},
                            )
                        )["acceptance"]
                        calculation = (
                            await call(
                                "calculate_pricing_scenarios",
                                recipe_id=item["recipe_id"],
                                acceptance_id=accepted["id"],
                            )
                        )["calculation"]
                        await call(
                            "save_menu_decision",
                            recipe_id=item["recipe_id"],
                            acceptance_id=accepted["id"],
                            calculation_id=calculation["id"],
                            scenario_id="M20",
                            evidence=p["evidence"] | {"statement": "Escolho M20."},
                        )
                        costs.append(Decimal(calculation["cmv_production"]))
                    return costs

                created = await plan((0, 1))
                assert created["summary"]["disbursement"] == "30.00"
                assert await choose_all() == [Decimal("19.92"), Decimal("16.98")]
                previous = await current()
                reordered = await plan((1, 0))
                assert set(reordered["invalidated_decisions"]) == {
                    a["id"] for a in previous["acceptances"]
                }
                assert reordered["summary"]["remaining_budget"] == "50.00"
                invalidated = await current()
                assert invalidated["menu"] == []
                assert all(a["validity"] == "INVALIDATED" for a in invalidated["acceptances"])
                old = previous["pricing_calculations"][0]
                await call(
                    "save_menu_decision",
                    recipe_id=old["recipe_id"],
                    acceptance_id=old["acceptance_id"],
                    calculation_id=old["id"],
                    scenario_id="M20",
                    error="STALE_EVALUATION",
                    evidence=p["evidence"] | {"statement": "Escolho M20."},
                )
                assert await current() == invalidated
                assert await choose_all() == [Decimal("14.94"), Decimal("21.96")]
                assert len((await current())["menu"]) == 2
                removed = await plan((0,))
                assert removed["summary"]["disbursement"] == "0.00"
                assert removed["summary"]["remaining_budget"] == "80.00"
                assert (await current())["menu"] == []
                assert await choose_all() == [Decimal("19.92")]
                final = await current()
                assert len(final["menu"]) == 1
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_business_state", {"workspace_id": p["workspace"]}
                )
                assert not result.is_error, result.structured_content
                assert result.structured_content["revision"] == revision
                assert result.structured_content["data"] == final
                stock = await session.call_tool(
                    "get_inventory_snapshot", {"workspace_id": p["workspace"]}
                )
                assert stock.structured_content["data"] == p["original"]
