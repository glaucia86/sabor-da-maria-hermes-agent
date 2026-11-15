"""O operador revisa em outro processo; nenhum Hermes é executado aqui."""

import json
import subprocess
import sys
from uuid import uuid4

from dona_maria.approvals import ApprovalService
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


def test_cli_migration_review_attestation_and_rejection(tmp_path, inventory_file):
    database = tmp_path / "operator.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]

    def cli(*arguments, answer=""):
        return subprocess.run(
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
                *arguments,
            ],
            input=answer,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )

    migrated = cli("migrate", "--backup", str(tmp_path / "backup.sqlite3"))
    assert migrated.returncode == 0, migrated.stderr
    local = ApprovalService(SQLiteWorkspaceRepository(database))
    proposal = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=0,
            command={
                "kind": "record_kitchen_facts",
                "payload": {"facts": [{"category": "EQUIPMENT", "key": "stove", "value": True}]},
            },
        )
    )
    listed = cli("list")
    assert listed.returncode == 0
    assert json.loads(listed.stdout)[0]["id"] == proposal["id"]
    inspected = cli("inspect", proposal["id"])
    assert json.loads(inspected.stdout)["hash"] == proposal["hash"]
    refused = cli("approve", proposal["id"], "--hash", proposal["hash"], answer="sim\n")
    assert refused.returncode != 0
    reader = BusinessStateReader(local.repository)
    assert reader.get_business_state({"workspace_id": workspace})["revision"] == 0
    approved = cli(
        "approve",
        proposal["id"],
        "--hash",
        proposal["hash"],
        answer="ATESTO " + proposal["hash"] + "\n",
    )
    assert approved.returncode == 0, approved.stderr
    assert proposal["summary"] in approved.stdout
    assert "a cozinheira" in approved.stdout.casefold()
    assert reader.get_business_state({"workspace_id": workspace})["revision"] == 1
    replayed = cli(
        "approve",
        proposal["id"],
        "--hash",
        proposal["hash"],
        answer="ATESTO " + proposal["hash"] + "\n",
    )
    assert replayed.returncode == 0
    assert reader.get_business_state({"workspace_id": workspace})["revision"] == 1
    pending = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=1,
            command={
                "kind": "record_kitchen_facts",
                "payload": {"facts": [{"category": "SKILL", "key": "cook", "value": True}]},
            },
        )
    )
    rejected = cli("reject", pending["id"], "--hash", pending["hash"])
    assert rejected.returncode == 0, rejected.stderr
    assert json.loads(rejected.stdout)["status"] == "REJECTED"


def test_lost_cli_response_after_commit_replays_original_result_without_another_effect(
    tmp_path, inventory_file
):
    from dona_maria.approvals import migrate_proposals

    database = tmp_path / "lost-response.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "before-loss.sqlite3")
    local = ApprovalService(repository)
    proposal = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=0,
            command={
                "kind": "record_kitchen_facts",
                "payload": {"facts": [{"category": "EQUIPMENT", "key": "stove", "value": True}]},
            },
        )
    )
    proxy = tmp_path / "lose_committed_response.py"
    proxy.write_text(
        """import os
import runpy
import sys

original = sys.stdout
class LostResponse:
    def write(self, text):
        if text.startswith('{"schema_version":'):
            os._exit(74)
        return original.write(text)
    def flush(self):
        return original.flush()

sys.stdout = LostResponse()
runpy.run_module("dona_maria.approval_cli", run_name="__main__")
""",
        encoding="utf-8",
    )
    arguments = [
        "--database",
        str(database),
        "--workspace",
        workspace,
        "approve",
        proposal["id"],
        "--hash",
        proposal["hash"],
    ]
    lost = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", str(proxy), *arguments],
        input="ATESTO " + proposal["hash"] + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert lost.returncode == 74, lost.stderr
    reader = BusinessStateReader(repository)
    committed = reader.get_business_state({"workspace_id": workspace})
    assert committed["revision"] == 1
    assert local.inspect(workspace, proposal["id"])["status"] == "APPROVED"
    before = database.read_bytes()
    replay = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-m", "dona_maria.approval_cli", *arguments],
        input="ATESTO " + proposal["hash"] + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert replay.returncode == 0, replay.stderr
    result = (
        json.loads(replay.stdout.splitlines()[-1].split(": ", 1)[-1])
        if replay.stdout.splitlines()[-1].startswith("Digite ")
        else json.loads(replay.stdout.splitlines()[-1])
    )
    assert result["revision"] == 1
    assert reader.get_business_state({"workspace_id": workspace}) == committed
    assert database.read_bytes() == before
