"""S16 pelo MCP real e aprovação CLI separada, somente com fixtures sintéticas."""

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository

SKILL = Path(__file__).parents[2] / "skills/dona-maria-cardapio/SKILL.md"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def attest(local, database, workspace):
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
                        attest(local, database, workspace)
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


def skill_example():
    text = SKILL.read_text(encoding="utf-8")
    (block,) = [
        block
        for block in re.findall(r"```json\r?\n(.*?)```", text, re.S)
        if "category_review_changes" in block
    ]
    return json.loads(block)


def keys(value):
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in keys(item)}
    return set()


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["REAL", "SIMULATION"])
async def test_skill_category_review_example_matches_mcp_contract(tmp_path, inventory_file, mode):
    database = tmp_path / "skill-example.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode=mode
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "backup.sqlite3")
    local = ApprovalService(repository)
    reader = BusinessStateReader(repository)
    source = {"kind": "USER_PROVIDED"}
    requirement = dict(
        category="EQUIPMENT", key="panela", condition="PRESENT", reason="Cozinhar o lote."
    )
    reviews = [
        dict(
            category=category,
            requirement_keys=["panela"] if category == "EQUIPMENT" else [],
            method_version=1,
            not_applicable_reason=None if category == "EQUIPMENT" else "Sem condição crítica.",
            source=source,
        )
        for category in ("EQUIPMENT", "SKILL", "OPERATION")
    ]
    candidate = dict(
        title="Receita genérica da cozinheira",
        origin=dict(source=source),
        ingredients=[
            dict(
                description="Ingrediente sintético",
                preparation_basis="RAW",
                source=source,
                original_measure=dict(raw_text="250 g", value="250", unit_label="g", source=source),
                quantity=dict(value="250", unit="g"),
            )
        ],
        method="Preparo declarado.",
        method_source=source,
        yield_per_batch=dict(servings_per_batch=2, sale_unit_label="porção", source=source),
        operational_context="Um lote por vez.",
        context_source=source,
        requirements=[requirement | dict(source=source)],
        category_reviews=reviews,
        declared_gaps=["Lacuna anterior."],
    )
    registered = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=0,
            command=dict(kind="register_recipe_candidate", payload=dict(candidate=candidate)),
        )
    )
    original = local.approve(workspace, registered["id"], registered["hash"], attest=True)
    original = original["data"]["candidate"]
    example = skill_example()
    changes = example["command"]["payload"]["candidate"]["changes"]
    (patch,) = changes["category_review_changes"]
    assert not keys(example) & {
        "method_version",
        "evidence",
        "local_event_id",
        "information_ref",
        "category_reviews",
    }
    example["operation_id"] = str(uuid4())
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.launcher"],
        env={
            "DONA_MARIA_DB_PATH": str(database),
            "DONA_MARIA_WORKSPACE_ID": workspace,
            "DONA_MARIA_MODE": "ATTENDANCE",
        },
    )
    with anyio.fail_after(60):
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                definitions = tools["propose_user_change"].input_schema["$defs"]
                assert set(definitions["BoundCategoryReviewChange"]["properties"]) == {
                    "category",
                    "not_applicable_reason",
                    "requirement_keys",
                    "source",
                }
                assert set(definitions["BoundUserProvidedSource"]["properties"]) == {"kind"}
                before = reader.get_business_state({"workspace_id": workspace})
                proposed = await session.call_tool("propose_user_change", example)
                assert not proposed.is_error, proposed
                assert proposed.structured_content["data"]["status"] == "PENDING"
                assert reader.get_business_state({"workspace_id": workspace}) == before
                attest(local, database, workspace)
                opening = (await session.call_tool("get_business_state", {})).structured_content
                recipe = opening["data"]["recipes"][0]
                assert recipe["version"] == 2
                assert recipe["adapted_from"] == dict(recipe=1, version=1)
                gaps = recipe["missing_information"]
                assert set(changes["declared_gaps"]) <= set(gaps)
                assert "Lacuna anterior." not in gaps
                assert not any(gap.startswith("Categoria não revisada") for gap in gaps)
                for private in ("local_event_id", "turn_ref", "information_ref"):
                    assert private not in json.dumps(opening)
                replay = await session.call_tool("propose_user_change", example)
                assert replay.structured_content["data"]["status"] == "APPLIED_HISTORICAL"
    adapted = reader.get_business_state({"workspace_id": workspace})["data"]["candidates"][0]
    for previous, review in zip(
        original["category_reviews"], adapted["category_reviews"], strict=True
    ):
        if review["category"] == patch["category"]:
            assert review["not_applicable_reason"] == patch["not_applicable_reason"]
            assert review["source"]["local_event_id"] != previous["source"]["local_event_id"]
        else:
            assert review == previous | {"method_version": 2}
    assert adapted["ingredients"][0]["quantity"] == original["ingredients"][0]["quantity"]
    assert adapted["business_version"] == original["business_version"] + 1
