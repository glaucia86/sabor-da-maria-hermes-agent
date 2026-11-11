"""SQLite local: agregado validado, fotografia imutável e transações explícitas."""

import hashlib
import json
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict

from dona_maria.candidates import CandidateInput, RecipeCandidate, RegisterCandidateRequest
from dona_maria.inventory import InventorySnapshot


class WorkspaceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_schema_version: Literal["1.0"] = "1.0"
    id: UUID
    inventory_snapshot_id: UUID
    budget_initial: Literal["80.00"] = "80.00"
    pricing_policy_version: Literal["1.0"] = "1.0"
    created_at: AwareDatetime
    updated_at: AwareDatetime
    candidates: list[RecipeCandidate] = []


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _decode_json(text: str) -> dict:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise sqlite3.DatabaseError("Chave JSON duplicada.")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=unique_object)
    except (TypeError, ValueError) as exc:
        raise sqlite3.DatabaseError("JSON persistido inválido.") from exc


class BusinessRuleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code, self.message = code, message
        super().__init__(message)


SCHEMA = (
    "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)",
    """CREATE TABLE inventory_snapshots (
        id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, import_policy_version TEXT NOT NULL,
        payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(source_sha256, import_policy_version))""",
    """CREATE TABLE workspaces (
        id TEXT PRIMARY KEY, revision INTEGER NOT NULL, snapshot_id TEXT NOT NULL
        REFERENCES inventory_snapshots(id), state_schema_version TEXT NOT NULL,
        state_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE decisions (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        kind TEXT NOT NULL, fingerprint TEXT NOT NULL, payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL)""",
    """CREATE TABLE operations (
        workspace_id TEXT NOT NULL REFERENCES workspaces(id), operation_id TEXT NOT NULL,
        tool TEXT NOT NULL, payload_hash TEXT NOT NULL, result_json TEXT NOT NULL,
        committed_revision INTEGER NOT NULL, PRIMARY KEY(workspace_id, operation_id))""",
)


class SQLiteWorkspaceRepository:
    def __init__(self, database: Path) -> None:
        self.database = database.resolve()
        self._write_lock = threading.Lock()

    def _connect(self, mode: str) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database.as_uri() + f"?mode={mode}",
            uri=True,
            timeout=5,
            autocommit=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def transaction(self, *, bootstrap: bool = False):
        with self._write_lock, closing(self._connect("rwc" if bootstrap else "rw")) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    @staticmethod
    def check_schema(db: sqlite3.Connection) -> bool:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables:
            return False
        if "schema_migrations" not in tables:
            raise sqlite3.DatabaseError("Schema não suportado.")
        versions = [row[0] for row in db.execute("SELECT version FROM schema_migrations")]
        if versions != [1]:
            raise sqlite3.DatabaseError("Versão de schema não suportada.")
        return True

    def load(self, workspace_id: str) -> tuple[int, WorkspaceState] | None:
        with closing(self._connect("ro")) as db:
            db.execute("BEGIN")
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            # Compatibilidade de leitura do seam mínimo S00; nunca migra esse schema.
            if (
                tables == {"workspaces"}
                and not db.execute(
                    "SELECT 1 FROM workspaces WHERE id=?", (workspace_id,)
                ).fetchone()
            ):
                return None
            if not self.check_schema(db):
                return None
            loaded = self.load_state(db, workspace_id)
            if loaded is None:
                return None
            revision, state, _snapshot = loaded
            return revision, state

    @staticmethod
    def load_state(
        db: sqlite3.Connection, workspace_id: str
    ) -> tuple[int, WorkspaceState, InventorySnapshot] | None:
        row = db.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if row is None:
            return None
        state = WorkspaceState.model_validate(_decode_json(row["state_json"]))
        if str(state.id) != workspace_id or str(state.inventory_snapshot_id) != row["snapshot_id"]:
            raise sqlite3.DatabaseError("Referência de workspace inválida.")
        if row["state_schema_version"] != state.state_schema_version or row["revision"] < 0:
            raise sqlite3.DatabaseError("Revisão/schema inválido.")
        if len({candidate.id for candidate in state.candidates}) != len(state.candidates):
            raise sqlite3.DatabaseError("Candidatas duplicadas no agregado.")
        snapshot = SQLiteWorkspaceRepository.load_snapshot(db, row["snapshot_id"])
        try:
            for candidate in state.candidates:
                _validate_ingredient_references(snapshot, candidate)
        except BusinessRuleError as exc:
            raise sqlite3.DatabaseError("Referência de candidata inválida.") from exc
        return row["revision"], state, snapshot

    @staticmethod
    def load_snapshot(db: sqlite3.Connection, snapshot_id: str) -> InventorySnapshot:
        row = db.execute("SELECT * FROM inventory_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise sqlite3.DatabaseError("Snapshot ausente.")
        snapshot = InventorySnapshot.model_validate(_decode_json(row["payload_json"]))
        if (
            str(snapshot.id) != snapshot_id
            or snapshot.source_sha256 != row["source_sha256"]
            or snapshot.import_policy_version != row["import_policy_version"]
        ):
            raise sqlite3.DatabaseError("Referência de snapshot inválida.")
        if len({item.id for item in snapshot.items}) != len(snapshot.items):
            raise sqlite3.DatabaseError("Identidades duplicadas.")
        return snapshot

    def inventory(self, workspace_id: str) -> tuple[int, InventorySnapshot] | None:
        with closing(self._connect("ro")) as db:
            db.execute("BEGIN")
            if not self.check_schema(db):
                return None
            loaded = self.load_state(db, workspace_id)
            if loaded is None:
                return None
            revision, _state, snapshot = loaded
            return revision, snapshot

    def bootstrap(
        self, snapshot: InventorySnapshot, now: datetime, workspace_id: str | None = None
    ) -> dict:
        with self.transaction(bootstrap=True) as db:
            if not self.check_schema(db):
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute("INSERT INTO schema_migrations VALUES (1, ?)", (now.isoformat(),))
            if workspace_id is not None:
                existing = self.load_state(db, str(UUID(workspace_id)))
                if existing is None or existing[1].inventory_snapshot_id != snapshot.id:
                    raise ValueError(
                        "Workspace ausente ou fotografia diferente; criar outro workspace."
                    )
                return {
                    "workspace_id": workspace_id,
                    "snapshot_id": str(snapshot.id),
                    "revision": existing[0],
                    "budget_initial": "80.00",
                }
            state = WorkspaceState(
                id=uuid4(),
                inventory_snapshot_id=snapshot.id,
                created_at=now,
                updated_at=now,
            )
            db.execute(
                "INSERT OR IGNORE INTO inventory_snapshots VALUES (?, ?, ?, ?, ?)",
                (
                    str(snapshot.id),
                    snapshot.source_sha256,
                    snapshot.import_policy_version,
                    snapshot.model_dump_json(),
                    now.isoformat(),
                ),
            )
            self.load_snapshot(db, str(snapshot.id))
            db.execute(
                "INSERT INTO workspaces VALUES (?, 0, ?, ?, ?, ?, ?)",
                (
                    str(state.id),
                    str(snapshot.id),
                    state.state_schema_version,
                    state.model_dump_json(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    str(state.id),
                    "IMPORT_WORKSPACE",
                    fingerprint(snapshot.model_dump(mode="json")),
                    canonical_json({"snapshot_id": str(snapshot.id)}),
                    now.isoformat(),
                ),
            )
            result = {
                "workspace_id": str(state.id),
                "snapshot_id": str(snapshot.id),
                "revision": 0,
                "budget_initial": "80.00",
            }
            db.execute(
                "INSERT INTO operations VALUES (?, ?, ?, ?, ?, 0)",
                (
                    str(state.id),
                    str(uuid4()),
                    "bootstrap_workspace",
                    fingerprint({"snapshot_id": str(snapshot.id)}),
                    canonical_json(result),
                ),
            )
        return result

    def register_candidate(self, request: RegisterCandidateRequest, now: datetime) -> dict:
        workspace_id, operation_id = str(request.workspace_id), str(request.operation_id)
        payload_hash = fingerprint(request.model_dump(mode="json"))
        with self.transaction() as db:
            self.check_schema(db)
            loaded = self.load_state(db, workspace_id)
            if loaded is None:
                raise BusinessRuleError("NOT_FOUND", "Workspace não encontrado.")
            replay = db.execute(
                "SELECT * FROM operations WHERE workspace_id=? AND operation_id=?",
                (workspace_id, operation_id),
            ).fetchone()
            if replay:
                if (
                    replay["tool"] != "register_recipe_candidate"
                    or replay["payload_hash"] != payload_hash
                ):
                    raise BusinessRuleError(
                        "IDEMPOTENCY_CONFLICT", "Operação já usada com outro conteúdo."
                    )
                return _decode_json(replay["result_json"])
            revision, state, snapshot = loaded
            if revision != request.expected_revision:
                raise BusinessRuleError(
                    "STALE_REVISION", "Recarregue a revisão atual do workspace."
                )
            if not request.candidate.sources:
                raise BusinessRuleError("SOURCE_REQUIRED", "Candidata pesquisada exige fonte.")
            _validate_ingredient_references(snapshot, request.candidate)
            previous = next(
                (item for item in state.candidates if item.id == request.recipe_id), None
            )
            if request.recipe_id is not None and previous is None:
                raise BusinessRuleError("NOT_FOUND", "Candidata não pertence ao workspace.")
            if previous and previous.version != request.expected_recipe_version:
                raise BusinessRuleError("STALE_REVISION", "Recarregue a versão atual da candidata.")
            candidate = RecipeCandidate(
                **request.candidate.model_dump(mode="json"),
                id=previous.id if previous else uuid4(),
                version=previous.version + 1 if previous else 1,
                recorded_at=now,
            )
            state.candidates = [item for item in state.candidates if item.id != candidate.id]
            state.candidates.append(candidate)
            state.updated_at = now
            state = WorkspaceState.model_validate_json(state.model_dump_json())
            revision += 1
            result = {
                "schema_version": "1.0",
                "ok": True,
                "workspace_id": workspace_id,
                "revision": revision,
                "operation_id": operation_id,
                "data": {
                    "candidate": candidate.public(),
                    "invalidated_decisions": [],
                    "next_action": "CLARIFY_CANDIDATE_GAPS",
                },
                "warnings": [],
                "error": None,
            }
            db.execute(
                "UPDATE workspaces SET revision=?, state_json=?, updated_at=? WHERE id=?",
                (
                    revision,
                    state.model_dump_json(),
                    now.isoformat(),
                    workspace_id,
                ),
            )
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    workspace_id,
                    "REGISTER_RECIPE_CANDIDATE",
                    fingerprint(
                        {
                            "snapshot_id": str(state.inventory_snapshot_id),
                            "candidate": candidate.model_dump(mode="json"),
                            "pricing_policy_version": state.pricing_policy_version,
                        }
                    ),
                    candidate.model_dump_json(),
                    now.isoformat(),
                ),
            )
            db.execute(
                "INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?)",
                (
                    workspace_id,
                    operation_id,
                    "register_recipe_candidate",
                    payload_hash,
                    canonical_json(result),
                    revision,
                ),
            )
        return result


def _validate_ingredient_references(snapshot: InventorySnapshot, candidate: CandidateInput) -> None:
    items = {item.id: item for item in snapshot.items}
    if isinstance(candidate, RecipeCandidate) and (
        len({item.line_id for item in candidate.ingredients}) != len(candidate.ingredients)
    ):
        raise BusinessRuleError("VALIDATION_ERROR", "Linhas de ingredientes duplicadas.")
    dimensions = {"g": "g", "kg": "g", "ml": "ml", "L": "ml", "un": "un"}
    for ingredient in candidate.ingredients:
        if ingredient.ingredient_id is None:
            continue
        item = items.get(ingredient.ingredient_id)
        if item is None:
            raise BusinessRuleError("NOT_FOUND", "Ingrediente não pertence ao workspace.")
        if ingredient.quantity and dimensions[ingredient.quantity.unit] != item.dimension:
            raise BusinessRuleError(
                "UNIT_CONVERSION_REQUIRED", "Medida exige conversão sustentada."
            )
