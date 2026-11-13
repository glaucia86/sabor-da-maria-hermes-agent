"""S06: confirmação → aceite → cálculo → escolha pelo transporte MCP real."""

import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_confirmation_pricing_replay_and_expired_resume_over_stdio(clarification, tmp_path):
    service, workspace, command, candidate, _, original, _, database = clarification
    candidate["ingredients"] = candidate["ingredients"][:1]
    candidate["ingredients"][0]["quantity"]["value"] = "5200"
    recipe = command("register_recipe_candidate", candidate=candidate)["data"]["candidate"]
    stamp = datetime.now(UTC)
    evidence = dict(
        turn_ref="synthetic-s06-stdio",
        statement="Confirmo esta produção.",
        captured_at=stamp.isoformat(),
    )
    quote = command(
        "register_complement_quote",
        quote=dict(
            ingredient_id=recipe["ingredients"][0]["ingredient_id"],
            description="Arroz — fixture",
            package_quantity=dict(value="1000", unit="g"),
            package_price="20.00",
            purchase_extra_total="0.00",
            extra_conditions="Retirada gratuita",
            availability="AVAILABLE",
            availability_context="Retirada hoje",
            max_packages=1,
            supplier="Fornecedor sintético",
            source=candidate["sources"][0],
        ),
    )["data"]["quote"]
    command(
        "record_recipe_feedback", recipe_id=recipe["id"], feedback="INTERESTED", evidence=evidence
    )
    plan = command(
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=1, position=0, batches=1)],
        quote_selections=[
            dict(ingredient_id=quote["ingredient_id"], quote_id=quote["id"], quote_version=1)
        ],
        evidence=evidence,
    )["data"]["plan"]
    revision = service.get_business_state({"workspace_id": workspace})["revision"]
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    confirmation_request = dict(
        workspace_id=workspace,
        operation_id=str(uuid4()),
        expected_revision=revision,
        quote_id=quote["id"],
        quote_version=1,
        scope=dict(
            package_quantity=dict(value="1000", unit="g"),
            package_price="20.00",
            purchase_extra_total="0.00",
            extra_conditions="Retirada gratuita",
            availability_context="Retirada hoje",
            supplier="Fornecedor sintético",
            packages=1,
        ),
        evidence=evidence
        | {
            "statement": "Confirmo 1 pacote de 1000 g a R$ 20,00 por pacote, "
            "encargos R$ 0,00, Retirada gratuita, disponível em "
            "Fornecedor sintético: Retirada hoje."
        },
    )
    with anyio.fail_after(40):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {t.name: t for t in (await session.list_tools()).tools}
                assert "confirm_complement_quote" in tools
                assert (
                    tools["confirm_complement_quote"].input_schema["additionalProperties"] is False
                )

                async def call(tool, **payload):
                    nonlocal revision
                    result = await session.call_tool(
                        tool,
                        dict(
                            workspace_id=workspace,
                            expected_revision=revision,
                            operation_id=str(uuid4()),
                        )
                        | payload,
                    )
                    assert result.is_error is False, result.structured_content
                    revision = result.structured_content["revision"]
                    return result.structured_content["data"]

                confirmed = await session.call_tool(
                    "confirm_complement_quote", confirmation_request
                )
                assert confirmed.is_error is False, confirmed.structured_content
                revision = confirmed.structured_content["revision"]
                evaluated = await session.call_tool(
                    "evaluate_purchase_plan", {"workspace_id": workspace}
                )
                evaluation = evaluated.structured_content["data"]
                assert evaluation["purchase_status"] == "CONFIRMED"
                accepted = (
                    await call(
                        "accept_recipe",
                        recipe_id=recipe["id"],
                        plan_item_id=plan["items"][0]["plan_item_id"],
                        evaluation_id=evaluation["evaluation_id"],
                        evidence=evidence | {"statement": "Aceito este prato."},
                    )
                )["acceptance"]
                calculation = (
                    await call(
                        "calculate_pricing_scenarios",
                        recipe_id=recipe["id"],
                        acceptance_id=accepted["id"],
                    )
                )["calculation"]
                assert calculation["cmv_per_serving"] == "14.45000"
                decision = await call(
                    "save_menu_decision",
                    recipe_id=recipe["id"],
                    acceptance_id=accepted["id"],
                    calculation_id=calculation["id"],
                    scenario_id="M20",
                    evidence=evidence | {"statement": "Escolho M20."},
                )
                assert decision["decision"]["price"] == "20.65"
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                replay = await session.call_tool("confirm_complement_quote", confirmation_request)
                assert replay.structured_content == confirmed.structured_content
                state = (
                    await session.call_tool("get_business_state", {"workspace_id": workspace})
                ).structured_content
                assert state["revision"] == revision
                assert len(state["data"]["acceptances"]) == 1
                assert state["data"]["menu"][0]["price"] == "20.65"
                assert state["data"]["budget_remaining"] == "60.00"
        # Novo processo com relógio controlado, injetado somente no harness de teste.
        script = tmp_path / "expired_server.py"
        script.write_text(
            "import asyncio\nfrom pathlib import Path\nfrom datetime import datetime\n"
            "from mcp.server.stdio import stdio_server\n"
            "from dona_maria.mcp_server import create_server\n"
            "from dona_maria.business_state import BusinessStateReader\n"
            "from dona_maria.persistence import SQLiteWorkspaceRepository\n"
            f"repository=SQLiteWorkspaceRepository(Path({str(database)!r}))\n"
            f"clock=lambda:datetime.fromisoformat({(stamp + timedelta(hours=25)).isoformat()!r})\n"
            "server=create_server(BusinessStateReader(repository, clock=clock))\n"
            "async def main():\n    async with stdio_server() as (read,write):\n"
            "        await server.run(read,write,server.create_initialization_options())\n"
            "asyncio.run(main())\n",
            encoding="utf-8",
        )
        expired_server = StdioServerParameters(
            command=sys.executable, args=["-B", str(script)], cwd=tmp_path
        )
        async with stdio_client(expired_server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                state = (
                    await session.call_tool("get_business_state", {"workspace_id": workspace})
                ).structured_content
                assert state["data"]["menu"] == []
                assert state["data"]["evaluation"]["purchase_status"] == "PENDING"
                refused = await session.call_tool(
                    "save_menu_decision",
                    dict(
                        workspace_id=workspace,
                        operation_id=str(uuid4()),
                        expected_revision=revision,
                        recipe_id=recipe["id"],
                        acceptance_id=accepted["id"],
                        calculation_id=calculation["id"],
                        scenario_id="M10",
                        evidence=evidence | {"statement": "Escolho M10."},
                    ),
                )
                assert refused.is_error is True
                assert refused.structured_content["error"]["code"] == "STALE_EVALUATION"
                snapshot = await session.call_tool(
                    "get_inventory_snapshot", {"workspace_id": workspace}
                )
                assert snapshot.structured_content["data"] == original
