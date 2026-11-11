"""Bootstrap local explícito; nunca exposto como ferramenta MCP."""

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from dona_maria.inventory import import_inventory
from dona_maria.persistence import SQLiteWorkspaceRepository


def bootstrap_workspace(
    database: Path, inventory: Path, *, allowed_directory: Path, workspace_id: str | None = None
) -> dict:
    snapshot = import_inventory(inventory, allowed_directory=allowed_directory)
    return SQLiteWorkspaceRepository(database).bootstrap(snapshot, datetime.now(UTC), workspace_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importação local explícita da despensa.")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--allowed-directory", type=Path, required=True)
    parser.add_argument("--workspace-id", help="Reutiliza somente workspace da mesma fotografia.")
    args = parser.parse_args()
    try:
        result = bootstrap_workspace(
            args.database,
            args.inventory,
            allowed_directory=args.allowed_directory,
            workspace_id=args.workspace_id,
        )
    except (ValueError, OSError, sqlite3.Error):
        parser.exit(1, "Importação recusada; conferir origem, diretório e armazenamento.\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
