"""S18 no catálogo conversacional real; só a entrada local atesta as propostas."""

import json
import sys
from uuid import uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from dona_maria.approvals import ApprovalService, migrate_proposals


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_incomplete_cost_and_external_water_survive_stdio_restart_with_local_approval(
    pricing_workspace,
    tmp_path,
):
    reader, workspace, _, _, _, database = pricing_workspace(total=None, accept=False)
    migrate_proposals(reader.repository, tmp_path / "stdio-backup.sqlite3")
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
    acquisition_request = dict(
        operation_id=str(uuid4()),
        command=dict(
            kind="record_inventory_acquisition",
            payload=dict(
                ingredient_id=1,
                available_quantity={"value": "500", "unit": "g"},
                acquired_quantity={"value": "1000", "unit": "g"},
                acquisition_total="20.00",
                basis="HISTORICAL_ACQUISITION",
                context="Aquisição humana sintética; não é reposição.",
            ),
        ),
    )
    for restart in range(2):
        with anyio.fail_after(30):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    assert len(tools) == 6
                    schema = next(t.input_schema for t in tools if t.name == "propose_user_change")
                    assert "record_inventory_acquisition" in json.dumps(schema)
                    assert "record_operational_resource" in json.dumps(schema)
                    for forbidden in (
                        "approve",
                        "record_inventory_acquisition",
                        "import_inventory",
                    ):
                        assert (await session.call_tool(forbidden, {})).is_error
                    if restart == 0:
                        pending = await session.call_tool("evaluate_purchase_plan", {})
                        assert (
                            pending.structured_content["data"]["financial_readiness"]["status"]
                            == "PENDING"
                        )
                        result = await session.call_tool(
                            "propose_user_change",
                            dict(
                                operation_id=str(uuid4()),
                                command=dict(
                                    kind="record_operational_resource",
                                    payload=dict(
                                        recipe_id=1,
                                        resource_name="Água",
                                        purpose="Limpeza dos utensílios.",
                                        classification="EXTERNAL_OPERATIONAL_RESOURCE",
                                        quantity={"value": "2", "unit": "L"},
                                        cost_gap="Conta não informada.",
                                        context="Atividade externa à composição do alimento.",
                                    ),
                                ),
                            ),
                        )
                        assert not result.is_error, result
                        proposal = local.list(workspace)[-1]
                        local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
                    before = reader.get_business_state({"workspace_id": workspace})
                    proposed = await session.call_tool("propose_user_change", acquisition_request)
                    assert not proposed.is_error, proposed
                    assert reader.get_business_state({"workspace_id": workspace}) == before
                    if restart == 0:
                        proposal = local.list(workspace)[-1]
                        local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
                    else:
                        assert proposed.structured_content["data"]["status"] == "APPLIED_HISTORICAL"
                    evaluated = await session.call_tool("evaluate_purchase_plan", {})
                    data = evaluated.structured_content["data"]
                    assert data["financial_readiness"]["status"] == "READY"
                    assert data["financial_readiness"]["net_profit_complete"] is False
                    assert data["operational_resources"][0]["included_in_ingredient_cmv"] is False
                    assert data["operational_resources"][0]["cost"] is None
                    assert data["demand"][0]["stock_available"] == "500"
                    assert workspace not in json.dumps(data)
                    assert "local_event_id" not in json.dumps(data)
                    refused = await session.call_tool(
                        "calculate_pricing_scenarios",
                        dict(
                            operation_id=str(uuid4()),
                            recipe=1,
                        ),
                    )
                    assert refused.is_error
    state = reader.get_business_state({"workspace_id": workspace})["data"]
    assert len(state["inventory_acquisitions"]) == len(state["operational_resources"]) == 1
    assert state["pricing_calculations"] == state["menu"] == []
