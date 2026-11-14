"""SQLite local: agregado validado, fotografia imutável e transações explícitas."""

import json
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from uuid import UUID, uuid4

from dona_maria.candidates import RecipeCandidate, RegisterCandidateRequest
from dona_maria.ingredients import (
    ConversionRequest,
    ResolveIngredientRequest,
    apply_overlays,
    validate_overlay_references,
    with_complements,
)
from dona_maria.inventory import InventorySnapshot
from dona_maria.planning import (
    BusinessRuleError,
    WorkspaceState,
    _accept_recipe,
    _apply_production_command,
    _calculate_pricing,
    _invalidate_acceptances,
    _record_feedback,
    _save_menu_decision,
    _validate_ingredient_references,
    avoided_preference,
    canonical_json,
    confirm_quote,
    correction_next_action,
    evaluate_feasibility,
    evaluate_plan,
    fingerprint,
    invalidate_expired_acceptances,
    record_conversion,
    register_quote,
    resolve_ingredient,
)
from dona_maria.pricing import (
    FINANCIAL_CONTEXT,
    CalculatePricingRequest,
    SaveMenuDecisionRequest,
    allocate_plan_costs,
    calculate_pricing,
)
from dona_maria.production import (
    AcceptanceRequest,
    FeasibilityRequest,
    FeedbackRequest,
    KitchenFactsRequest,
    PlanRequest,
    PreferencesRequest,
    RecipeFeedback,
)
from dona_maria.quotes import ConfirmQuoteRequest, RegisterQuoteRequest, validate_quote_references


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


def _invalidation_summary(state: WorkspaceState, previously_invalid: set[UUID]) -> dict:
    invalidated = [
        identifier
        for identifier in state.invalidated_acceptance_ids
        if identifier not in previously_invalid
    ]
    invalidated_ids = set(invalidated)
    latest_choices = {d.recipe_id: d.id for d in state.menu_decisions}
    return {
        "invalidated_decisions": [str(identifier) for identifier in invalidated],
        "invalidated_calculation_ids": [
            str(c.id) for c in state.pricing_calculations if c.acceptance_id in invalidated_ids
        ],
        "invalidated_menu_decision_ids": [
            str(d.id)
            for d in state.menu_decisions
            if d.acceptance_id in invalidated_ids and d.id == latest_choices[d.recipe_id]
        ],
    }


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

    def load(self, workspace_id: str, *, with_snapshot: bool = False) -> tuple | None:
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
            return loaded if with_snapshot else loaded[:2]

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
            validate_overlay_references(state, snapshot)
            validate_quote_references(state, snapshot)
            for candidate in state.candidates:
                _validate_ingredient_references(snapshot, candidate, state.complement_ingredients)
        except (BusinessRuleError, ValueError) as exc:
            raise sqlite3.DatabaseError("Referência de candidata inválida.") from exc
        SQLiteWorkspaceRepository._validate_pricing(state, snapshot, row["revision"])
        return row["revision"], state, snapshot

    @staticmethod
    def _validate_pricing(
        state: WorkspaceState, snapshot: InventorySnapshot, revision: int
    ) -> None:
        if not state.pricing_calculations:
            return
        effective_recipes, effective = apply_overlays(
            state.candidates, snapshot, state.ingredient_conversions
        )
        stocks = {item.id: item for item in snapshot.items}
        recipes = {recipe.id: recipe for recipe in effective_recipes}
        acceptances = {acceptance.id: acceptance for acceptance in state.acceptances}
        plan_items = {item.plan_item_id: item for item in state.plan.items} if state.plan else {}
        current_fingerprint = evaluate_plan(
            state.candidates,
            state.plan,
            state.kitchen_facts,
            state.feedback,
            snapshot,
            state.pricing_policy_version,
            revision,
            conversions=state.ingredient_conversions,
            complement_ingredients=state.complement_ingredients,
            quotes=state.complement_quotes,
            confirmations=state.quote_confirmations,
        )["fingerprint"]
        for calculation in state.pricing_calculations:
            for allocation in calculation.allocations:
                if allocation.origin == "QUOTE":
                    quote = next(
                        (
                            q
                            for q in state.complement_quotes
                            if q.id == allocation.source_id
                            and str(q.version) == allocation.source_version
                        ),
                        None,
                    )
                    if (
                        quote is None
                        or quote.ingredient_id != allocation.ingredient_id
                        or quote.package_quantity is None
                        or allocation.unit != quote.package_quantity.unit
                        or Decimal(allocation.purchase_quantity_base)
                        != Decimal(quote.package_quantity.value)
                        or allocation.acquisition_total != quote.package_price
                        or allocation.source != quote.source.model_dump(mode="json")
                    ):
                        raise sqlite3.DatabaseError(
                            "Origem da alocação não corresponde à cotação histórica."
                        )
                    continue
                stock = stocks.get(allocation.ingredient_id)
                bases = [(stock.dimension, stock.purchase_quantity_base)] if stock else []
                with localcontext(FINANCIAL_CONTEXT):
                    bases.extend(
                        (c.to_unit, stock.purchase_quantity_base * Decimal(c.factor))
                        for c in state.ingredient_conversions
                        if stock and c.ingredient_id == stock.id and c.scope == "HISTORICAL_PACKAGE"
                    )
                if (
                    stock is None
                    or allocation.source_id != snapshot.id
                    or allocation.source_version != snapshot.import_policy_version
                    or (allocation.unit, Decimal(allocation.purchase_quantity_base)) not in bases
                    or allocation.acquisition_total != str(stock.acquisition_total)
                    or stock.purchase_source is None
                    or allocation.source != stock.purchase_source.model_dump(mode="json")
                ):
                    raise sqlite3.DatabaseError("Origem do cálculo não corresponde à aquisição.")
            if (
                calculation.acceptance_id in state.invalidated_acceptance_ids
                or calculation.fingerprint != current_fingerprint
            ):
                continue
            acceptance = acceptances[calculation.acceptance_id]
            recomputed = calculate_pricing(
                recipes[calculation.recipe_id],
                plan_items[acceptance.plan_item_id],
                acceptance,
                effective,
                state.pricing_policy_version,
                calculation.calculated_at,
                allocations=[
                    a
                    for a in allocate_plan_costs(
                        effective_recipes,
                        state.plan,
                        with_complements(effective, state.complement_ingredients),
                        state.complement_quotes,
                    )
                    if a.recipe_id == calculation.recipe_id
                ]
                if state.plan.quote_selections
                else None,
            )
            if calculation.model_dump(exclude={"id", "calculated_at"}) != recomputed.model_dump(
                exclude={"id", "calculated_at"}
            ):
                raise sqlite3.DatabaseError("Cálculo não corresponde à receita e produção aceitas.")

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
            _validate_ingredient_references(
                snapshot, request.candidate, state.complement_ingredients
            )
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
            material_change = (
                previous is None or candidate.business_content() != previous.business_content()
            )
            candidate.business_version = (
                previous.business_version + int(material_change) if previous else 1
            )
            if previous and not material_change:
                candidate.ingredients = previous.ingredients
                candidate.requirements = previous.requirements
            previously_invalid = set(state.invalidated_acceptance_ids)
            invalidate_expired_acceptances(state, snapshot, revision, now)
            if (
                previous
                and material_change
                and state.plan
                and any(item.recipe_id == previous.id for item in state.plan.items)
            ):
                _invalidate_acceptances(state)
            state.candidates = [item for item in state.candidates if item.id != candidate.id]
            state.candidates.append(candidate)
            avoided = avoided_preference(state, candidate)
            if avoided:
                _record_feedback(
                    state,
                    RecipeFeedback(
                        recipe_id=str(candidate.id),
                        feedback="REJECTED",
                        evidence=avoided.evidence,
                    ),
                )
            state.updated_at = now
            state = WorkspaceState.model_validate_json(state.model_dump_json())
            revision += 1
            summary = evaluate_plan(
                state.candidates,
                state.plan,
                state.kitchen_facts,
                state.feedback,
                snapshot,
                state.pricing_policy_version,
                revision,
                conversions=state.ingredient_conversions,
                complement_ingredients=state.complement_ingredients,
                quotes=state.complement_quotes,
                confirmations=state.quote_confirmations,
                now=now,
            )
            result = {
                "schema_version": "1.0",
                "ok": True,
                "workspace_id": workspace_id,
                "revision": revision,
                "operation_id": operation_id,
                "data": {
                    "candidate": candidate.public()
                    | {
                        "interest": next(
                            (f.feedback for f in state.feedback if f.recipe_id == candidate.id),
                            "UNDECIDED",
                        )
                    },
                    "summary": summary,
                    **_invalidation_summary(state, previously_invalid),
                    "next_action": correction_next_action(state, summary)
                    if avoided
                    or state.plan
                    and any(i.recipe_id == candidate.id for i in state.plan.items)
                    else "CLARIFY_CANDIDATE_GAPS",
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

    def production_command(
        self,
        tool: str,
        request: FeedbackRequest
        | PreferencesRequest
        | PlanRequest
        | KitchenFactsRequest
        | AcceptanceRequest
        | CalculatePricingRequest
        | SaveMenuDecisionRequest
        | ConversionRequest
        | ResolveIngredientRequest
        | RegisterQuoteRequest
        | ConfirmQuoteRequest,
        now: datetime,
    ) -> dict:
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
                if replay["tool"] != tool or replay["payload_hash"] != payload_hash:
                    raise BusinessRuleError("IDEMPOTENCY_CONFLICT", "Operação já utilizada.")
                return _decode_json(replay["result_json"])
            revision, state, snapshot = loaded
            if revision != request.expected_revision:
                raise BusinessRuleError("STALE_REVISION", "Recarregue o workspace.")
            previously_invalid = set(state.invalidated_acceptance_ids)
            invalidate_expired_acceptances(state, snapshot, revision, now)
            if isinstance(request, ConfirmQuoteRequest):
                data = confirm_quote(state, request, now)
            elif isinstance(request, RegisterQuoteRequest):
                data = register_quote(state, request, snapshot, now)
            elif isinstance(request, ResolveIngredientRequest):
                data = resolve_ingredient(state, request, snapshot, now)
            elif isinstance(request, ConversionRequest):
                data = record_conversion(state, request, snapshot, now)
            elif isinstance(request, SaveMenuDecisionRequest):
                data = _save_menu_decision(state, request, snapshot, revision, now)
            elif isinstance(request, CalculatePricingRequest):
                data = _calculate_pricing(state, request, snapshot, revision, now)
            elif isinstance(request, AcceptanceRequest):
                evaluation = evaluate_plan(
                    state.candidates,
                    state.plan,
                    state.kitchen_facts,
                    state.feedback,
                    snapshot,
                    state.pricing_policy_version,
                    revision,
                    conversions=state.ingredient_conversions,
                    complement_ingredients=state.complement_ingredients,
                    quotes=state.complement_quotes,
                    confirmations=state.quote_confirmations,
                    now=now,
                )
                data = _accept_recipe(state, request, evaluation, now)
            else:
                data = _apply_production_command(state, request, now)
            state.updated_at = now
            state = WorkspaceState.model_validate_json(state.model_dump_json())
            revision += 1
            if isinstance(
                request, (PlanRequest, KitchenFactsRequest, FeedbackRequest, PreferencesRequest)
            ):
                data["summary"] = evaluate_plan(
                    state.candidates,
                    state.plan,
                    state.kitchen_facts,
                    state.feedback,
                    snapshot,
                    state.pricing_policy_version,
                    revision,
                    conversions=state.ingredient_conversions,
                    complement_ingredients=state.complement_ingredients,
                    quotes=state.complement_quotes,
                    confirmations=state.quote_confirmations,
                    now=now,
                )
                data["next_action"] = correction_next_action(state, data["summary"])
            data.update(_invalidation_summary(state, previously_invalid))
            result = {
                "schema_version": "1.0",
                "ok": True,
                "workspace_id": workspace_id,
                "revision": revision,
                "operation_id": operation_id,
                "data": data,
                "warnings": [],
                "error": None,
            }
            db.execute(
                "UPDATE workspaces SET revision=?, state_json=?, updated_at=? WHERE id=?",
                (revision, state.model_dump_json(), now.isoformat(), workspace_id),
            )
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    workspace_id,
                    tool.upper(),
                    payload_hash,
                    canonical_json(data),
                    now.isoformat(),
                ),
            )
            db.execute(
                "INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?)",
                (workspace_id, operation_id, tool, payload_hash, canonical_json(result), revision),
            )
        return result

    def feasibility(self, request: FeasibilityRequest) -> dict:
        with closing(self._connect("ro")) as db:
            db.execute("BEGIN")
            self.check_schema(db)
            loaded = self.load_state(db, str(request.workspace_id))
            if loaded is None:
                raise BusinessRuleError("NOT_FOUND", "Workspace não encontrado.")
            revision, state, snapshot = loaded
            recipes, _ = apply_overlays(state.candidates, snapshot, state.ingredient_conversions)
            recipe = next((r for r in recipes if r.id == request.recipe_id), None)
            item = (
                next(
                    (
                        i
                        for i in state.plan.items
                        if i.plan_item_id == request.plan_item_id
                        and i.recipe_id == request.recipe_id
                    ),
                    None,
                )
                if state.plan
                else None
            )
            if recipe is None or item is None:
                raise BusinessRuleError(
                    "NOT_FOUND", "Receita/item não pertence ao plano do workspace."
                )
            return dict(
                schema_version="1.0",
                ok=True,
                workspace_id=str(request.workspace_id),
                revision=revision,
                operation_id=None,
                warnings=[],
                error=None,
                data=evaluate_feasibility(
                    recipe, item, state.kitchen_facts, plan=state.plan, candidates=recipes
                ),
            )

    def purchase_evaluation(self, workspace_id: str, now: datetime | None = None) -> dict:
        with closing(self._connect("ro")) as db:
            db.execute("BEGIN")
            self.check_schema(db)
            loaded = self.load_state(db, workspace_id)
            if loaded is None:
                raise BusinessRuleError("NOT_FOUND", "Workspace não encontrado.")
            revision, state, snapshot = loaded
            evaluation = evaluate_plan(
                state.candidates,
                state.plan,
                state.kitchen_facts,
                state.feedback,
                snapshot,
                state.pricing_policy_version,
                revision,
                conversions=state.ingredient_conversions,
                complement_ingredients=state.complement_ingredients,
                quotes=state.complement_quotes,
                confirmations=state.quote_confirmations,
                now=now,
            )
            return dict(
                schema_version="1.0",
                ok=True,
                workspace_id=workspace_id,
                revision=revision,
                operation_id=None,
                warnings=[],
                error=None,
                data=evaluation,
            )
