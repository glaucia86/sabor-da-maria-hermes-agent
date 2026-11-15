"""S16 pelo MCP real e aprovação CLI separada, somente com fixtures sintéticas."""

import json
import sqlite3
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


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["REAL", "SIMULATION"])
async def test_partial_adaptation_measurement_and_mode_survive_stdio_restart(
    tmp_path, inventory_file, recipe_candidate, mode
):
    database = tmp_path / "isolated.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode=mode
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "backup.sqlite3")
    local = ApprovalService(repository)
    reader = BusinessStateReader(repository)
    inventory = reader.get_inventory_snapshot({"workspace_id": workspace})
    source = {"kind": "USER_PROVIDED"}
    measurement = dict(
        kind="USER_REPORTED_MEASUREMENT",
        method="Pesei em balança doméstica.",
        context="Arroz cru, recipiente tarado.",
    )
    candidate = dict(
        title="Receita sintética da cozinheira",
        origin=dict(source=source),
        ingredients=[
            dict(
                description="Arroz",
                ingredient_id=1,
                preparation_basis="RAW",
                source=source,
                original_measure=dict(
                    raw_text="100 g de arroz", value="100", unit_label="g", source=measurement
                ),
                quantity=dict(value="100", unit="g"),
            )
        ],
        method="Misture manualmente.",
        method_source=source,
        yield_gap="Rendimento ainda não relatado.",
        context_gap="Condições ainda não relatadas.",
    )
    original = dict(
        operation_id=str(uuid4()),
        command=dict(kind="register_recipe_candidate", payload=dict(candidate=candidate)),
    )
    adaptation = dict(
        operation_id=str(uuid4()),
        command=dict(
            kind="register_recipe_candidate",
            payload=dict(
                recipe_id=1,
                candidate=dict(
                    origin=dict(source=source, derived_from=dict(recipe_id=1, version=1)),
                    changes=dict(
                        method="Divida em duas porções depois de misturar.",
                        method_source=source,
                        yield_per_batch=dict(
                            servings_per_batch=2,
                            sale_unit_label="porção",
                            source=measurement
                            | {
                                "inputs": [
                                    dict(
                                        entity="RECIPE",
                                        entity_id=1,
                                        version=1,
                                        field="ingredients/0/original_measure/source",
                                    )
                                ]
                            },
                        ),
                        yield_gap=None,
                    ),
                ),
            ),
        ),
    )
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
        result = subprocess.run(
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
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        assert result.returncode == 0, result.stderr

    for stage in range(3):
        with anyio.fail_after(60):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    async def call(name, arguments):
                        result = await session.call_tool(name, arguments)
                        assert not result.is_error, result
                        return result.structured_content["data"]

                    tools = {tool.name for tool in (await session.list_tools()).tools}
                    assert len(tools) == 6
                    assert "propose_user_change" in tools
                    opening = await call("get_business_state", {})
                    assert opening["context_mode"] == mode
                    assert opening["hypothetical"] is (mode == "SIMULATION")
                    if stage < 2:
                        before = reader.get_business_state({"workspace_id": workspace})
                        await call("propose_user_change", original if stage == 0 else adaptation)
                        assert reader.get_business_state({"workspace_id": workspace}) == before
                        attest()
                    else:
                        recipe = opening["recipes"][0]
                        assert recipe["version"] == 2
                        assert recipe["adapted_from"] == dict(recipe=1, version=1)
                        assert any(
                            origin.get("method") == measurement["method"]
                            for origin in recipe["information_origins"]
                        )
                        before = database.read_bytes()
                        assert (await call("propose_user_change", adaptation))[
                            "status"
                        ] == "APPLIED_HISTORICAL"
                        for arguments in (
                            {"context_mode": "REAL"},
                            {"workspace_id": str(uuid4())},
                            {"database": "other.sqlite3"},
                        ):
                            refused = await session.call_tool("get_business_state", arguments)
                            assert refused.is_error
                        invalid = json.loads(json.dumps(adaptation))
                        invalid["operation_id"] = str(uuid4())
                        invalid["command"]["payload"]["candidate"]["origin"]["derived_from"][
                            "version"
                        ] = 99
                        assert (await session.call_tool("propose_user_change", invalid)).is_error
                        assert database.read_bytes() == before
                        for private in (
                            workspace,
                            str(database),
                            "local_event_id",
                            "turn_ref",
                            "information_ref",
                        ):
                            assert private not in json.dumps(opening)
    assert reader.get_inventory_snapshot({"workspace_id": workspace})["data"] == inventory["data"]
    with sqlite3.connect(database) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM user_change_proposals WHERE status='APPROVED'"
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM operations WHERE tool='register_recipe_candidate'"
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute("SELECT COUNT(*) FROM decisions WHERE kind='LOCAL_APPROVAL'").fetchone()[0]
            == 2
        )
