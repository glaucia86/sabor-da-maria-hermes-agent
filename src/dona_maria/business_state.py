"""Serviço público de consulta, produção, aceite e precificação determinística."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import DecimalException
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from dona_maria.candidates import RegisterCandidateRequest
from dona_maria.ingredients import ConversionRequest, ResolveIngredientRequest
from dona_maria.persistence import BusinessRuleError, SQLiteWorkspaceRepository
from dona_maria.planning import evaluate_plan, pricing_view
from dona_maria.pricing import CalculatePricingRequest, SaveMenuDecisionRequest
from dona_maria.production import (
    AcceptanceRequest,
    FeasibilityRequest,
    FeedbackRequest,
    KitchenFactsRequest,
    PlanRequest,
)
from dona_maria.quotes import RegisterQuoteRequest


class GetBusinessStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID

    @field_validator("workspace_id", mode="before")
    @classmethod
    def require_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("workspace_id deve ser UUID textual.")
        return value


class GetInventorySnapshotRequest(GetBusinessStateRequest):
    ingredient_ids: list[UUID] | None = None


class ReadError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, str | list[str]]
    retryable: bool
    next_action: str


class ReadErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    ok: bool = False
    workspace_id: UUID | None
    revision: int | None = None
    operation_id: UUID | None = None
    data: dict | None = None
    warnings: list[str] = []
    error: ReadError | None = None


class BusinessStateReader:
    def __init__(
        self,
        repository: SQLiteWorkspaceRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.clock = clock

    def record_recipe_feedback(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command("record_recipe_feedback", FeedbackRequest, arguments)

    def record_ingredient_conversion(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command(
            "record_ingredient_conversion", ConversionRequest, arguments
        )

    def resolve_recipe_ingredient(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command(
            "resolve_recipe_ingredient", ResolveIngredientRequest, arguments
        )

    def set_production_plan(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command("set_production_plan", PlanRequest, arguments)

    def register_complement_quote(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command(
            "register_complement_quote", RegisterQuoteRequest, arguments
        )

    def record_kitchen_facts(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command("record_kitchen_facts", KitchenFactsRequest, arguments)

    def accept_recipe(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command("accept_recipe", AcceptanceRequest, arguments)

    def calculate_pricing_scenarios(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command(
            "calculate_pricing_scenarios", CalculatePricingRequest, arguments
        )

    def save_menu_decision(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command("save_menu_decision", SaveMenuDecisionRequest, arguments)

    def evaluate_recipe_feasibility(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_query(FeasibilityRequest, self.repository.feasibility, arguments)

    def evaluate_purchase_plan(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_query(
            GetBusinessStateRequest,
            lambda request: self.repository.purchase_evaluation(str(request.workspace_id)),
            arguments,
        )

    def _production_query(self, schema: type[BaseModel], query: Callable, arguments: dict) -> dict:
        try:
            request = schema.model_validate(arguments)
        except ValidationError:
            return ReadErrorEnvelope(
                workspace_id=None,
                error=ReadError(
                    code="VALIDATION_ERROR",
                    message="Consulta de viabilidade inválida.",
                    details={},
                    retryable=False,
                    next_action="CORRECT_INPUT",
                ),
            ).model_dump(mode="json")
        try:
            return query(request)
        except BusinessRuleError as exc:
            return ReadErrorEnvelope(
                workspace_id=request.workspace_id,
                error=ReadError(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                    retryable=False,
                    next_action="CORRECT_INPUT",
                ),
            ).model_dump(mode="json")
        except (sqlite3.Error, ValidationError):
            return _storage_unavailable(str(request.workspace_id))

    def _production_command(self, tool: str, schema: type[BaseModel], arguments: dict) -> dict:
        try:
            request = schema.model_validate(arguments)
        except ValidationError as exc:
            return ReadErrorEnvelope(
                workspace_id=None,
                error=ReadError(
                    code="VALIDATION_ERROR",
                    message="Entrada inválida para produção.",
                    details={
                        "fields": sorted({".".join(map(str, e["loc"])) for e in exc.errors()})
                    },
                    retryable=False,
                    next_action="CORRECT_INPUT",
                ),
            ).model_dump(mode="json")
        try:
            return self.repository.production_command(tool, request, self.clock())
        except DecimalException:
            return ReadErrorEnvelope(
                workspace_id=request.workspace_id,
                operation_id=request.operation_id,
                error=ReadError(
                    code="CALCULATION_ERROR",
                    message="Não foi possível calcular com os custos e limites atuais.",
                    details={},
                    retryable=False,
                    next_action="CHECK_PRICING_INPUTS",
                ),
            ).model_dump(mode="json")
        except BusinessRuleError as exc:
            return ReadErrorEnvelope(
                workspace_id=request.workspace_id,
                operation_id=request.operation_id,
                error=ReadError(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                    retryable=False,
                    next_action="RELOAD_STATE" if exc.code == "STALE_REVISION" else "CORRECT_INPUT",
                ),
            ).model_dump(mode="json")
        except (sqlite3.Error, ValidationError) as exc:
            return _storage_unavailable(
                str(request.workspace_id), operation_id=request.operation_id, cause=exc
            )

    def register_recipe_candidate(self, arguments: dict[str, object]) -> dict[str, object]:
        try:
            request = RegisterCandidateRequest.model_validate(arguments)
        except ValidationError as exc:
            return ReadErrorEnvelope(
                workspace_id=None,
                error=ReadError(
                    code="VALIDATION_ERROR",
                    message="Entrada inválida para registro de candidata.",
                    details={
                        "fields": sorted({".".join(map(str, item["loc"])) for item in exc.errors()})
                    },
                    retryable=False,
                    next_action="CORRECT_INPUT",
                ),
            ).model_dump(mode="json")
        try:
            return self.repository.register_candidate(request, self.clock())
        except BusinessRuleError as exc:
            return ReadErrorEnvelope(
                workspace_id=request.workspace_id,
                operation_id=request.operation_id,
                error=ReadError(
                    code=exc.code,
                    message=exc.message,
                    details={},
                    retryable=False,
                    next_action="RELOAD_STATE" if exc.code == "STALE_REVISION" else "CORRECT_INPUT",
                ),
            ).model_dump(mode="json")
        except (sqlite3.Error, ValidationError) as exc:
            return _storage_unavailable(
                str(request.workspace_id), operation_id=request.operation_id, cause=exc
            )

    def get_inventory_snapshot(self, arguments: dict[str, object]) -> dict[str, object]:
        try:
            request = GetInventorySnapshotRequest.model_validate(arguments)
        except ValidationError:
            return ReadErrorEnvelope(
                workspace_id=None,
                error=ReadError(
                    code="VALIDATION_ERROR",
                    message="Entrada inválida para leitura de inventário.",
                    details={},
                    retryable=False,
                    next_action="CORRECT_INPUT",
                ),
            ).model_dump(mode="json")
        workspace_id = str(request.workspace_id)
        try:
            loaded = self.repository.inventory(workspace_id)
        except (sqlite3.Error, ValidationError):
            return _storage_unavailable(workspace_id)
        if loaded is None:
            return self.get_business_state({"workspace_id": workspace_id})
        revision, snapshot = loaded
        if request.ingredient_ids is not None:
            identifiers = set(request.ingredient_ids)
            if not identifiers.issubset({item.id for item in snapshot.items}):
                return ReadErrorEnvelope(
                    workspace_id=workspace_id,
                    error=ReadError(
                        code="NOT_FOUND",
                        message="Ingrediente não pertence ao workspace.",
                        details={},
                        retryable=False,
                        next_action="CORRECT_INPUT",
                    ),
                ).model_dump(mode="json")
            snapshot = snapshot.model_copy(
                update={
                    "items": [item for item in snapshot.items if item.id in identifiers],
                }
            )
        return ReadErrorEnvelope(
            ok=True,
            workspace_id=workspace_id,
            revision=revision,
            data=snapshot.model_dump(mode="json"),
        ).model_dump(mode="json")

    def get_business_state(self, arguments: dict[str, object]) -> dict[str, object]:
        try:
            request = GetBusinessStateRequest.model_validate(arguments)
        except ValidationError as exc:
            return ReadErrorEnvelope(
                workspace_id=None,
                error=ReadError(
                    code="VALIDATION_ERROR",
                    message="Entrada inválida para leitura do workspace.",
                    details={"fields": sorted({str(error["loc"][0]) for error in exc.errors()})},
                    retryable=False,
                    next_action="CORRECT_INPUT",
                ),
            ).model_dump(mode="json")
        workspace_id = str(request.workspace_id)
        try:
            loaded = self.repository.load(workspace_id, with_snapshot=True)
        except (sqlite3.Error, ValidationError):
            return _storage_unavailable(workspace_id)
        if loaded is not None:
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
            )
            acceptances = [
                acceptance.model_dump(mode="json")
                | {
                    "validity": "VALID"
                    if acceptance.id not in state.invalidated_acceptance_ids
                    and acceptance.fingerprint == evaluation["fingerprint"]
                    else "INVALIDATED",
                }
                for acceptance in state.acceptances
            ]
            prices = pricing_view(state, evaluation)
            candidates = [candidate.public() for candidate in state.candidates]
            for candidate in candidates:
                feedback = next(
                    (item for item in state.feedback if str(item.recipe_id) == candidate["id"]),
                    None,
                )
                if feedback:
                    candidate["interest"] = feedback.feedback
                feasibility = next(
                    (
                        entry
                        for entry in evaluation["feasibility_by_recipe"]
                        if entry["recipe_id"] == candidate["id"]
                    ),
                    None,
                )
                if feasibility:
                    derived = {entry["id"]: entry for entry in feasibility["requirements"]}
                    for requirement in candidate["requirements"]:
                        requirement.update(derived[requirement["id"]])
                    candidate["status"] = (
                        "BLOCKED"
                        if feasibility["status"] == "BLOCKED"
                        else "FEASIBILITY_PENDING"
                        if feasibility["status"] == "PENDING"
                        or any(
                            entry["status"] != "ELIGIBLE"
                            for entry in evaluation["feasibility_by_recipe"]
                        )
                        else "INGREDIENT_CHECK_PENDING"
                        if evaluation["purchase_status"] != "CONFIRMED"
                        else "DISCOVERED"
                        if candidate["interest"] == "UNDECIDED"
                        else "READY_FOR_ACCEPTANCE"
                    )
                elif feedback:
                    candidate["status"] = "FEASIBILITY_PENDING"
                if any(
                    a["recipe_id"] == candidate["id"] and a["validity"] == "VALID"
                    for a in acceptances
                ):
                    candidate["status"] = "ACCEPTED"
                if any(
                    c["recipe_id"] == candidate["id"] and c["validity"] == "VALID"
                    for c in prices["pricing_calculations"]
                ):
                    candidate["status"] = "PRICED"
                if any(d["recipe_id"] == candidate["id"] for d in prices["menu"]):
                    candidate["status"] = "MENU_SELECTED"
                if candidate["interest"] == "REJECTED":
                    candidate["status"] = "REJECTED"
            return ReadErrorEnvelope(
                ok=True,
                workspace_id=workspace_id,
                revision=revision,
                data={
                    "inventory_snapshot_id": str(state.inventory_snapshot_id),
                    "budget_initial": state.budget_initial,
                    "budget_remaining": evaluation["remaining_budget"]
                    if state.plan and state.plan.items
                    else "80.00",
                    "candidates": candidates,
                    "complement_ingredients": [
                        i.model_dump(mode="json") for i in state.complement_ingredients
                    ],
                    "complement_quotes": [quote.public() for quote in state.complement_quotes],
                    "ingredient_conversions": [
                        c.model_dump(mode="json") for c in state.ingredient_conversions
                    ],
                    "ingredient_resolutions": [
                        r.model_dump(mode="json") for r in state.ingredient_resolutions
                    ],
                    "acceptances": acceptances,
                    **prices,
                    "evaluation": evaluation,
                    "plan": state.plan.model_dump(mode="json") if state.plan else None,
                    "kitchen_facts": [fact.model_dump(mode="json") for fact in state.kitchen_facts],
                    "next_action": (
                        "ASK_EXPLICIT_ACCEPTANCE"
                        if any(c.get("status") == "READY_FOR_ACCEPTANCE" for c in candidates)
                        else "ASK_PRICE_CHOICE"
                        if any(c.get("status") == "PRICED" for c in candidates)
                        else "REVIEW_ACCEPTED_RECIPES"
                        if any(c.get("status") == "ACCEPTED" for c in candidates)
                        else "REVIEW_MENU"
                        if prices["menu"]
                        else "CLARIFY_CANDIDATE_GAPS"
                        if any(c["interest"] != "REJECTED" for c in candidates)
                        else "RESEARCH_CANDIDATE"
                    ),
                },
            ).model_dump(mode="json")
        return ReadErrorEnvelope(
            workspace_id=workspace_id,
            error=ReadError(
                code="NOT_FOUND",
                message="Workspace não encontrado.",
                details={
                    "checked_at": self.clock().astimezone(UTC).isoformat().replace("+00:00", "Z")
                },
                retryable=False,
                next_action="CONFIGURE_WORKSPACE",
            ),
        ).model_dump(mode="json")


def _storage_unavailable(
    workspace_id: str, *, operation_id: UUID | None = None, cause: Exception | None = None
) -> dict[str, object]:
    busy = getattr(cause, "sqlite_errorcode", None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
    return ReadErrorEnvelope(
        workspace_id=workspace_id,
        operation_id=operation_id,
        error=ReadError(
            code="STORAGE_BUSY" if busy else "STORAGE_UNAVAILABLE",
            message="Banco ocupado; repetir o mesmo comando/ID."
            if busy
            else "Banco indisponível ou estado ainda não suportado neste recorte.",
            details={},
            retryable=busy,
            next_action="RETRY_SAME_OPERATION" if busy else "CHECK_STORAGE",
        ),
    ).model_dump(mode="json")
