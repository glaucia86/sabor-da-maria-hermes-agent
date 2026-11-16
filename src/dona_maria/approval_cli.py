"""Revisão local assistida. Não importar ou registrar este comando no MCP."""

import argparse
import json
import sqlite3
from decimal import DecimalException
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.planning import BusinessRuleError


def main() -> None:
    parser = argparse.ArgumentParser(description="Atestação local da manifestação da cozinheira.")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--workspace", type=UUID, required=True)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("list")
    migration = commands.add_parser("migrate")
    migration.add_argument("--backup", type=Path, required=True)
    research_migration = commands.add_parser("migrate-research")
    research_migration.add_argument("--backup", type=Path, required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("proposal", type=UUID)
    for action in ("approve", "reject"):
        command = commands.add_parser(action)
        command.add_argument("proposal", type=UUID)
        command.add_argument("--hash", required=True)
    args = parser.parse_args()
    repository = SQLiteWorkspaceRepository(args.database)
    service = ApprovalService(repository)
    workspace = str(args.workspace)
    try:
        if repository.load(workspace) is None:
            raise ValueError("Workspace ausente.")
        if args.action == "migrate":
            migrate_proposals(repository, args.backup)
            result = {"migrated": True, "schema": 2}
        elif args.action == "migrate-research":
            from dona_maria.research import migrate_research

            migrate_research(repository, args.backup)
            result = {"migrated": True, "schema": 3}
        elif args.action == "list":
            result = service.list(workspace)
        elif args.action == "inspect":
            result = service.inspect(workspace, str(args.proposal))
        elif args.action == "reject":
            result = service.reject(workspace, str(args.proposal), args.hash)
        else:
            proposal = service.inspect(workspace, str(args.proposal))
            if proposal["hash"] != args.hash:
                raise ValueError("Hash divergente.")
            print(proposal["summary"])
            print("Hash: " + proposal["hash"])
            print(
                "Ateste somente se a cozinheira manifestou esta decisão sobre o conteúdo exato. "
                "Você não decide por ela."
            )
            answer = input("Digite ATESTO seguido do hash apresentado: ")
            result = service.approve(
                workspace, str(args.proposal), args.hash, attest=answer == "ATESTO " + args.hash
            )
    except (
        ValueError,
        OSError,
        EOFError,
        sqlite3.Error,
        ValidationError,
        DecimalException,
        BusinessRuleError,
    ) as exc:
        code = exc.code if isinstance(exc, BusinessRuleError) else "LOCAL_REVIEW_REFUSED"
        parser.exit(
            1, f"{code}: revisão recusada; confira proposta, contexto e armazenamento local.\n"
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
