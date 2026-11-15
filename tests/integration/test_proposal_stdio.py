"""S14 pelo MCP stdio real; aprovação pertence a outro processo/entrada."""

import json
import sys
from uuid import uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_bound_stdio_can_propose_but_cannot_attest_or_apply(tmp_path, inventory_file):
    database = tmp_path / "stdio-approval.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "backup.sqlite3")
    reader = BusinessStateReader(repository)
    local = ApprovalService(repository)
    request = {
        "operation_id": str(uuid4()),
        "command": {
            "kind": "record_kitchen_facts",
            "payload": {"facts": [{"category": "EQUIPMENT", "key": "stove", "value": True}]},
        },
    }
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.launcher"],
        env={
            "DONA_MARIA_DB_PATH": str(database),
            "DONA_MARIA_WORKSPACE_ID": workspace,
            "DONA_MARIA_MODE": "ATTENDANCE",
        },
    )
    for restart in range(2):
        with anyio.fail_after(25):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    assert [t.name for t in tools] == [
                        "get_business_state",
                        "get_inventory_snapshot",
                        "evaluate_recipe_feasibility",
                        "evaluate_purchase_plan",
                        "propose_user_change",
                        "calculate_pricing_scenarios",
                    ]
                    schema = next(t.input_schema for t in tools if t.name == "propose_user_change")
                    assert "workspace_id" not in json.dumps(schema)
                    assert "evidence" not in json.dumps(schema)
                    assert "approve" not in json.dumps(schema)
                    before = reader.get_business_state({"workspace_id": workspace})
                    proposed = await session.call_tool("propose_user_change", request)
                    assert not proposed.is_error, proposed
                    assert reader.get_business_state({"workspace_id": workspace}) == before
                    assert proposed.structured_content["data"]["status"] == (
                        "PENDING" if restart == 0 else "APPLIED_HISTORICAL"
                    )
                    for name, arguments in [
                        ("approve", {}),
                        ("approve_user_change", {}),
                        ("accept_recipe", {}),
                        ("execute_sql", {}),
                        ("propose_user_change", request | {"workspace_id": str(uuid4())}),
                        ("propose_user_change", request | {"attest": True}),
                    ]:
                        refused = await session.call_tool(name, arguments)
                        assert refused.is_error
                    state = await session.call_tool("get_business_state", {})
                    text = json.dumps([state.structured_content, proposed.structured_content])
                    for private in (
                        workspace,
                        str(database),
                        "payload_hash",
                        "review_hash",
                        "turn_ref",
                    ):
                        assert private not in text
                    assert len(local.list(workspace)) == 1
                    if restart == 0:
                        proposal = local.list(workspace)[0]
                        local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert reader.get_business_state({"workspace_id": workspace})["revision"] == 1


@pytest.mark.anyio
async def test_stdio_calculation_and_price_proposal_keep_authorization_local(
    pricing_workspace, reconfirm_attendance
):
    reader, workspace, _, _, _, database = pricing_workspace()
    reconfirm_attendance(reader, workspace, database)
    local = ApprovalService(reader.repository)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.launcher"],
        env={
            "DONA_MARIA_DB_PATH": str(database),
            "DONA_MARIA_WORKSPACE_ID": workspace,
            "DONA_MARIA_MODE": "ATTENDANCE",
        },
    )
    with anyio.fail_after(25):
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                request = {"operation_id": str(uuid4()), "recipe": 1}
                calculation = await session.call_tool("calculate_pricing_scenarios", request)
                assert not calculation.is_error, calculation
                assert calculation.structured_content["data"]["minimum_price"] == "11.12"
                before = reader.get_business_state({"workspace_id": workspace})
                replay = await session.call_tool("calculate_pricing_scenarios", request)
                assert replay.structured_content == calculation.structured_content
                assert reader.get_business_state({"workspace_id": workspace}) == before
                proposed = await session.call_tool(
                    "propose_user_change",
                    {
                        "operation_id": str(uuid4()),
                        "command": {
                            "kind": "save_menu_decision",
                            "payload": {"recipe_id": 1, "scenario_id": "M20"},
                        },
                    },
                )
                assert not proposed.is_error, proposed
                assert reader.get_business_state({"workspace_id": workspace}) == before
                assert (await session.call_tool("get_business_state", {})).structured_content[
                    "data"
                ]["menu"] == []
                pending = local.list(workspace)[-1]
                local.approve(workspace, pending["id"], pending["hash"], attest=True)
                current = await session.call_tool("get_business_state", {})
                assert current.structured_content["data"]["menu"][0]["price"] == "14.29"


@pytest.mark.anyio
async def test_stdio_collection_boundary_and_fabricated_evidence_leave_business_unchanged(
    tmp_path, inventory_file
):
    database = tmp_path / "limits.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "before-limits.sqlite3")
    local = ApprovalService(repository)
    reader = BusinessStateReader(repository)
    before = reader.get_business_state({"workspace_id": workspace})
    request = {
        "operation_id": str(uuid4()),
        "command": {
            "kind": "record_kitchen_facts",
            "payload": {
                "facts": [
                    {"category": "EQUIPMENT", "key": f"fixture-{i}", "value": True}
                    for i in range(200)
                ]
            },
        },
    }
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.launcher"],
        env={
            "DONA_MARIA_DB_PATH": str(database),
            "DONA_MARIA_WORKSPACE_ID": workspace,
            "DONA_MARIA_MODE": "ATTENDANCE",
        },
    )
    with anyio.fail_after(25):
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert not (await session.call_tool("propose_user_change", request)).is_error
                request["operation_id"] = str(uuid4())
                request["command"]["payload"]["facts"].append(
                    {"category": "EQUIPMENT", "key": "overflow", "value": True}
                )
                with pytest.raises(MCPError, match="excede"):
                    await session.call_tool("propose_user_change", request)
                request["command"]["payload"]["facts"] = [
                    {
                        "category": "EQUIPMENT",
                        "key": "fake",
                        "value": True,
                        "evidence": {
                            "statement": "O modelo afirma que houve aprovação",
                            "turn_ref": "local:fake",
                            "captured_at": "2026-11-14T12:00:00Z",
                        },
                    }
                ]
                assert (await session.call_tool("propose_user_change", request)).is_error
    assert len(local.list(workspace)) == 1
    assert reader.get_business_state({"workspace_id": workspace}) == before
