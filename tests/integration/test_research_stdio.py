"""S17: SQLite temporário, CLI e MCP STDIO reais; fonte web é fixture identificada."""

import json
import subprocess
import sys
from uuid import uuid4

import anyio
import pytest
from conftest import synthetic_web_extraction
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import AttendanceService, BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.research import ResearchService, migrate_research


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_explicit_migration_cli_preserves_business_state_and_backup(tmp_path, inventory_file):
    database = tmp_path / "migration.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "v1.sqlite3")
    before = repository.load(workspace)
    backup = tmp_path / "v2.sqlite3"
    command = [
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
        "migrate-research",
        "--backup",
        str(backup),
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"migrated": True, "schema": 3}
    assert SQLiteWorkspaceRepository(backup).load(workspace) == before
    assert repository.load(workspace) == before
    repeated = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert repeated.returncode != 0
    assert repository.load(workspace) == before


@pytest.mark.anyio
async def test_research_reference_dispatches_through_bound_stdio_and_restarts(
    tmp_path, inventory_file, recipe_candidate
):
    database = tmp_path / "stdio-research.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "stdio-v1.sqlite3")
    migrate_research(repository, tmp_path / "stdio-v2.sqlite3")

    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Fixture"}]

    class Extractor:
        async def extract(self, url):
            return synthetic_web_extraction(url, "100 g de arroz; cozinhe em água.")

    research = ResearchService(
        AttendanceService(database, workspace, "ATTENDANCE"),
        {"arroz": "arroz"},
        search=search,
        extractor=Extractor(),
    )
    result = await research.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    identifier = result["data"]["results"][0]["research_result_id"]
    assert (await research.call("extract_culinary_source", {"research_result_id": identifier}))[
        "ok"
    ]
    ref = {"kind": "WEB", "research_result_id": identifier, "segment": "segment-1"}

    def replace(value):
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            return (
                dict(ref)
                if value.get("kind") == "WEB"
                else {k: replace(v) for k, v in value.items()}
            )
        return value

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.launcher"],
        env={
            "DONA_MARIA_DB_PATH": str(database),
            "DONA_MARIA_WORKSPACE_ID": workspace,
            "DONA_MARIA_MODE": "ATTENDANCE",
        },
    )
    local = ApprovalService(repository)
    before = BusinessStateReader(repository).get_business_state({"workspace_id": workspace})
    inventory_before = BusinessStateReader(repository).get_inventory_snapshot(
        {"workspace_id": workspace}
    )
    request = {
        "operation_id": str(uuid4()),
        "command": {
            "kind": "register_recipe_candidate",
            "payload": {"candidate": replace(recipe_candidate)},
        },
    }
    for turn in range(2):
        with anyio.fail_after(30):
            async with (
                stdio_client(parameters) as (read, write),
                ClientSession(read, write) as session,
            ):
                initialized = await session.initialize()
                assert initialized.capabilities.resources is None
                assert initialized.capabilities.prompts is None
                for _ in range(2):
                    assert {t.name for t in (await session.list_tools()).tools} == {
                        "get_business_state",
                        "get_inventory_snapshot",
                        "evaluate_recipe_feasibility",
                        "evaluate_purchase_plan",
                        "propose_user_change",
                        "calculate_pricing_scenarios",
                    }
                for forbidden in (
                    "web_search",
                    "web_extract",
                    "extract_culinary_source",
                    "accept_recipe",
                ):
                    assert (await session.call_tool(forbidden, {})).is_error
                if turn == 0:
                    rejected = await session.call_tool(
                        "propose_user_change", request | {"workspace_id": str(uuid4())}
                    )
                    assert rejected.is_error
                    assert (
                        BusinessStateReader(repository).get_business_state(
                            {"workspace_id": workspace}
                        )
                        == before
                    )
                    proposal_result = await session.call_tool("propose_user_change", request)
                    assert not proposal_result.is_error, proposal_result.content
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
                        timeout=30,
                    )
                    assert approved.returncode == 0, approved.stderr
                state = (await session.call_tool("get_business_state", {})).structured_content
                assert (
                    state["ok"]
                    and "Pesquisa web registrada" in state["data"]["recipes"][0]["origin"]
                )
                assert identifier not in json.dumps(state)
                replay = await session.call_tool("propose_user_change", request)
                assert not replay.is_error
    assert len(repository.load(workspace)[1].candidates) == 1
    assert (
        BusinessStateReader(repository).get_inventory_snapshot({"workspace_id": workspace})["data"]
        == inventory_before["data"]
    )
