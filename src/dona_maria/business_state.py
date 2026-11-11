"""Leitura mínima de S00; não cria workspace, inventário ou decisões."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class GetBusinessStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID

    @field_validator("workspace_id", mode="before")
    @classmethod
    def require_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("workspace_id deve ser UUID textual.")
        return value


class ReadError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["NOT_FOUND", "VALIDATION_ERROR", "STORAGE_UNAVAILABLE"]
    message: str
    details: dict[str, str | list[str]]
    retryable: bool
    next_action: str


class ReadErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    ok: Literal[False] = False
    workspace_id: UUID | None
    revision: None = None
    operation_id: None = None
    data: None = None
    warnings: list[str] = []
    error: ReadError


class SQLiteWorkspaceRepository:
    def __init__(self, database: Path) -> None:
        self.database = database.resolve()

    def contains(self, workspace_id: str) -> bool:
        # mode=ro impede que uma leitura crie banco ou altere seu conteúdo.
        with closing(
            sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True, timeout=5)
        ) as db:
            table = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspaces'"
            ).fetchone()
            if table is None:
                return False
            return (
                db.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
                is not None
            )


class BusinessStateReader:
    def __init__(
        self,
        repository: SQLiteWorkspaceRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.clock = clock

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
            workspace_exists = self.repository.contains(workspace_id)
        except sqlite3.Error:
            return _storage_unavailable(workspace_id)
        if workspace_exists:
            return _storage_unavailable(workspace_id)
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


def _storage_unavailable(workspace_id: str) -> dict[str, object]:
    return ReadErrorEnvelope(
        workspace_id=workspace_id,
        error=ReadError(
            code="STORAGE_UNAVAILABLE",
            message="Banco indisponível ou estado ainda não suportado neste recorte.",
            details={},
            retryable=False,
            next_action="CHECK_STORAGE",
        ),
    ).model_dump(mode="json")
