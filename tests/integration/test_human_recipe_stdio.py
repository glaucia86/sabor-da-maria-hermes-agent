"""Jornada S15 sintética pelo catálogo real, com atestação em processo separado."""

import json
import subprocess
import sys
from uuid import uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


@pytest.fixture
def anyio_backend():
    return "asyncio"


def own_recipe():
    source = {"kind": "USER_PROVIDED"}
    keys = {"EQUIPMENT": "pilao", "SKILL": "triturar", "OPERATION": "local_seco"}
    return dict(
        title="Arroz triturado — receita própria sintética",
        origin={"source": source},
        sources=[source],
        ingredients=[
            dict(
                description="Arroz",
                ingredient_id=1,
                original_measure=dict(
                    raw_text="100 g de arroz cru", value="100", unit_label="g", source=source
                ),
                quantity=dict(value="100", unit="g"),
                preparation_basis="RAW",
                source=source,
            )
        ],
        method="Triture o arroz no pilão e divida em duas porções.",
        method_source=source,
        yield_per_batch=dict(servings_per_batch=2, sale_unit_label="porção", source=source),
        operational_context="Preparo manual, em local seco, de um lote por vez.",
        context_source=source,
        requirements=[
            dict(
                category=category,
                key=key,
                condition={
                    "EQUIPMENT": "PRESENT",
                    "SKILL": "SKILL_KNOWN",
                    "OPERATION": "EXPLICIT_CONDITION",
                }[category],
                value=True,
                reason="Condição declarada para este preparo sintético.",
                source=source,
            )
            for category, key in keys.items()
        ],
        category_reviews=[
            dict(category=category, requirement_keys=[key], source=source)
            for category, key in keys.items()
        ],
    )


@pytest.mark.anyio
async def test_own_recipe_restarts_confirms_conditions_and_recovers_valid_price(
    tmp_path, inventory_file
):
    database = tmp_path / "own-recipe.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "backup.sqlite3")
    local = ApprovalService(repository)
    reader = BusinessStateReader(repository)
    inventory_before = reader.get_inventory_snapshot({"workspace_id": workspace})["data"]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.launcher"],
        env={
            "DONA_MARIA_DB_PATH": str(database),
            "DONA_MARIA_WORKSPACE_ID": workspace,
            "DONA_MARIA_MODE": "ATTENDANCE",
        },
    )

    def attest():
        proposal = local.list(workspace)[-1]
        approved = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                "-m",
                "dona_maria.approval_cli",
                "--database",
                str(database),
                "--workspace",
                workspace,
                "approve",
                proposal["id"],
                "--hash",
                proposal["hash"],
            ],
            input="ATESTO " + proposal["hash"] + "\n",
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=20,
        )
        assert approved.returncode == 0, approved.stderr
        assert repository.load(workspace) is not None

    registration = dict(
        operation_id=str(uuid4()),
        command=dict(kind="register_recipe_candidate", payload=dict(candidate=own_recipe())),
    )
    for stage in range(3):
        with anyio.fail_after(50):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    async def call(name, arguments):
                        result = await session.call_tool(name, arguments)
                        assert not result.is_error, result
                        return result.structured_content["data"]

                    async def decide(kind, **payload):
                        before = reader.get_business_state({"workspace_id": workspace})
                        await call(
                            "propose_user_change",
                            dict(
                                operation_id=str(uuid4()), command=dict(kind=kind, payload=payload)
                            ),
                        )
                        assert reader.get_business_state({"workspace_id": workspace}) == before
                        attest()

                    tools = (await session.list_tools()).tools
                    assert {t.name for t in tools} == {
                        "get_business_state",
                        "get_inventory_snapshot",
                        "evaluate_recipe_feasibility",
                        "evaluate_purchase_plan",
                        "propose_user_change",
                        "calculate_pricing_scenarios",
                    }
                    if stage == 0:
                        await call("propose_user_change", registration)
                        assert (await call("get_business_state", {}))["recipes"] == []
                        attest()
                    elif stage == 1:
                        state = await call("get_business_state", {})
                        assert (
                            state["recipes"][0]["origin"]
                            == "Informada pela cozinheira; campos atestados localmente, "
                            "sem comprovação independente."
                        )
                        assert state["kitchen_facts"] == []
                        assert all(
                            r["status"] == "UNKNOWN" for r in state["recipes"][0]["conditions"]
                        )
                        assert (await call("propose_user_change", registration))[
                            "status"
                        ] == "APPLIED_HISTORICAL"
                        await decide("record_recipe_feedback", recipe_id=1, feedback="INTERESTED")
                        await decide(
                            "set_production_plan", items=[dict(recipe_id=1, position=0, batches=1)]
                        )
                        await decide(
                            "record_kitchen_facts",
                            facts=[
                                dict(category=c, key=k, value=True)
                                for c, k in (
                                    ("EQUIPMENT", "pilao"),
                                    ("SKILL", "triturar"),
                                    ("OPERATION", "local_seco"),
                                )
                            ],
                        )
                        evaluation = await call("evaluate_purchase_plan", {})
                        assert evaluation["remaining_budget"] == "80.00"
                        await decide("accept_recipe", recipe_id=1)
                        calculation = await call(
                            "calculate_pricing_scenarios", dict(operation_id=str(uuid4()), recipe=1)
                        )
                        assert calculation["minimum_price"] == "0.28"
                        assert len(calculation["scenarios"]) == 3
                        assert (await call("get_business_state", {}))["menu"] == []
                        await decide("save_menu_decision", recipe_id=1, scenario_id="M20")
                    else:
                        state = await call("get_business_state", {})
                        assert state["menu"][0]["price"] == "0.36"
                        assert state["recipes"][0]["status"] == "MENU_SELECTED"
                        for secret in (
                            workspace,
                            str(database),
                            "turn_ref",
                            "local_event_id",
                            "information_ref",
                        ):
                            assert secret not in json.dumps(state)
                        before_rename = reader.get_business_state({"workspace_id": workspace})[
                            "data"
                        ]
                        renamed = own_recipe()
                        renamed["title"] = "Arroz — título corrigido"
                        for _ in range(2):
                            await decide(
                                "register_recipe_candidate", recipe_id=1, candidate=renamed
                            )
                            current = reader.get_business_state({"workspace_id": workspace})["data"]
                            assert current["candidates"][0]["business_version"] == 1
                            assert current["candidates"][0]["title"] == renamed["title"]
                            assert current["acceptances"] == before_rename["acceptances"]
                            assert (
                                current["pricing_calculations"]
                                == before_rename["pricing_calculations"]
                            )
                            assert current["menu"] == before_rename["menu"]
                            assert (await call("get_business_state", {}))["menu"][0][
                                "price"
                            ] == "0.36"
                        revised = own_recipe()
                        revised["ingredients"][0]["quantity"]["value"] = "200"
                        revised["ingredients"][0]["original_measure"].update(
                            value="200", raw_text="200 g de arroz cru"
                        )
                        await decide("register_recipe_candidate", recipe_id=1, candidate=revised)
                        assert (await call("get_business_state", {}))["menu"] == []
                        assert (await call("propose_user_change", registration))[
                            "status"
                        ] == "APPLIED_HISTORICAL"
                        assert (await call("get_business_state", {}))["menu"] == []
    assert reader.get_inventory_snapshot({"workspace_id": workspace})["data"] == inventory_before
    current = reader.get_business_state({"workspace_id": workspace})["data"]
    assert len(current["acceptances"]) == len(current["pricing_calculations"]) == 1
    assert current["acceptances"][0]["validity"] == "INVALIDATED"
    assert current["menu"] == []
