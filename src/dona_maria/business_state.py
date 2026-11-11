"""Serviço público de consulta e registro de candidatas, sem aceite ou preço."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from dona_maria.candidates import RegisterCandidateRequest
from dona_maria.persistence import BusinessRuleError, SQLiteWorkspaceRepository


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
            loaded = self.repository.load(workspace_id)
        except (sqlite3.Error, ValidationError):
            return _storage_unavailable(workspace_id)
        if loaded is not None:
            revision, state = loaded
            return ReadErrorEnvelope(
                ok=True,
                workspace_id=workspace_id,
                revision=revision,
                data={
                    "inventory_snapshot_id": str(state.inventory_snapshot_id),
                    "budget_initial": state.budget_initial,
                    "budget_remaining": "80.00",
                    "candidates": [candidate.public() for candidate in state.candidates],
                    "next_action": "CLARIFY_CANDIDATE_GAPS"
                    if state.candidates
                    else "RESEARCH_CANDIDATE",
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
