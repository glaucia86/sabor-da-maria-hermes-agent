"""Origens declaradas e materializadas; nenhuma declaração autoriza uma escrita."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StrictInt,
    field_validator,
)


def require_uuid_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("UUID deve ser textual.")
    return value


UUIDText = Annotated[UUID, BeforeValidator(require_uuid_text)]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]
Note = Annotated[str, Field(min_length=1, max_length=4000)]


class CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserEvidence(CandidateModel):
    turn_ref: ShortText
    statement: Note
    captured_at: AwareDatetime

    @field_validator("turn_ref", "statement")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evidência exige referência e fala com conteúdo.")
        return value

    @field_validator("captured_at", mode="before")
    @classmethod
    def textual_date(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Evidência exige data RFC 3339 textual com timezone.")
        return value

    @field_validator("captured_at")
    @classmethod
    def utc_date(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class WebSource(CandidateModel):
    kind: Literal["WEB"] = "WEB"
    url: HttpUrl
    title: ShortText
    excerpt: Note
    retrieved_at: AwareDatetime
    # Ausência dos campos novos conserva a serialização histórica e seus hashes.
    research_result_id: UUIDText | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    segment: ShortText | None = Field(default=None, exclude_if=lambda value: value is None)
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @field_validator("retrieved_at", mode="before")
    @classmethod
    def textual_retrieval(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Data de recuperação deve ser RFC 3339 textual com timezone.")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def utc_retrieval(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("url", mode="before")
    @classmethod
    def bounded_url(cls, value: object) -> object:
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError("URL deve ser HTTP/HTTPS textual até 2048 caracteres.")
        return value

    @field_validator("url")
    @classmethod
    def credential_free_url(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("URL de fonte não pode conter credenciais.")
        return value


class InformationRef(CandidateModel):
    entity: Literal["RECIPE", "CONVERSION"]
    entity_id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    field: ShortText


class RegisteredWebReference(CandidateModel):
    kind: Literal["WEB"]
    research_result_id: UUIDText
    segment: ShortText


class UserProvidedSource(CandidateModel):
    kind: Literal["USER_PROVIDED"]
    # Ausência representa somente uma alegação na proposta, nunca fato confirmado.
    evidence: UserEvidence | None = None
    local_event_id: UUIDText | None = None
    information_ref: InformationRef | None = None


class UserSimulationSource(UserProvidedSource):
    kind: Literal["USER_SIMULATION"]
    scenario: Note


class UserReportedMeasurementSource(UserProvidedSource):
    kind: Literal["USER_REPORTED_MEASUREMENT"]
    method: Note
    context: Note
    inputs: Annotated[list[InformationRef], Field(max_length=200)] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )

    @field_validator("method", "context")
    @classmethod
    def reported_detail(cls, value):
        if not value.strip():
            raise ValueError("Medição exige método e contexto relatados.")
        return value


def legacy_web_tag(value):
    # O antigo WebSource aceitava omissão de kind; conserva leitura e hash de replay.
    if isinstance(value, dict) and "kind" not in value and "url" in value:
        return {"kind": "WEB", **value}
    return value


PrimaryProvenance = Annotated[
    WebSource | UserProvidedSource | UserSimulationSource | UserReportedMeasurementSource,
    Field(discriminator="kind"),
    BeforeValidator(legacy_web_tag),
]


class DerivedProvenance(CandidateModel):
    kind: Literal["DERIVED"] = "DERIVED"
    rule: ShortText
    rule_version: ShortText
    # A saída soma até duas referências próprias às 200 dependências de entrada.
    inputs: Annotated[list[InformationRef], Field(min_length=1, max_length=202)]
    depends_on_simulation: StrictBool = Field(default=False, exclude_if=lambda value: not value)


OutputProvenance = Annotated[
    WebSource
    | UserProvidedSource
    | UserSimulationSource
    | UserReportedMeasurementSource
    | DerivedProvenance,
    Field(discriminator="kind"),
    BeforeValidator(legacy_web_tag),
]


class RecipeVersionRef(CandidateModel):
    recipe_id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]


class RecipeOrigin(CandidateModel):
    source: PrimaryProvenance
    derived_from: RecipeVersionRef | None = None


def source_fields(value, path=""):
    """Percorre somente os campos de origem da candidata, conservando seu caminho exato."""
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from source_fields(item, f"{path}/{index}".lstrip("/"))
    elif isinstance(value, dict):
        if value.get("kind") in {
            "WEB",
            "USER_PROVIDED",
            "USER_SIMULATION",
            "USER_REPORTED_MEASUREMENT",
            "DERIVED",
        }:
            yield path, value
        else:
            for key, item in value.items():
                if key == "business_basis":
                    continue  # Snapshot financeiro auditado, não uma nova fonte de informação.
                yield from source_fields(item, f"{path}/{key}".lstrip("/"))


def information_value(content, path):
    """Valor atestado pelo source; metadados não fazem parte do fato relatado."""
    parts = path.split("/")
    node = content
    try:
        for part in parts[:-1]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        if parts[-1] == "method_source":
            return node.get("method")
        if parts[-1] == "context_source":
            return node.get("operational_context")
        if isinstance(node, list):
            return None
        excluded = {"source", "quantity_source", "line_id", "id", "status"}
        if parts[:1] == ["ingredients"] and parts[-2:] != ["original_measure", "source"]:
            excluded |= {"original_measure", "quantity", "quantity_gap"}
        return {key: value for key, value in node.items() if key not in excluded}
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def inherited_sources(content, original):
    sources = dict(source_fields(original))
    inherited = {}
    for path, source in source_fields(content):
        previous = sources.get(path)
        if (
            previous is None
            or path.startswith("origin/")
            or information_value(content, path) != information_value(original, path)
        ):
            continue
        new_measurement = (
            source["kind"] == "USER_REPORTED_MEASUREMENT" and previous["kind"] != "USER_SIMULATION"
        )
        if source["kind"] == "USER_SIMULATION" or new_measurement:
            if any(
                source.get(key) != previous.get(key)
                for key in ("kind", "method", "context", "scenario", "inputs")
            ):
                continue
        inherited[path] = previous
    return inherited


def context_labels(mode, content):
    depends, pending = False, [content]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            depends |= (
                value.get("kind") == "USER_SIMULATION" or value.get("depends_on_simulation") is True
            )
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return {
        "context_mode": mode or "REAL",
        "depends_on_simulation": depends,
        "hypothetical": mode == "SIMULATION" or depends,
    }


def transitive_inputs(references, resolve):
    """Expande referências locais com limite total e detecção de ciclos."""
    result, visited = [], set()

    def visit(reference, ancestors):
        key = (reference.entity, reference.entity_id, reference.version, reference.field)
        if key in ancestors:
            raise ValueError("Referência circular.")
        if key in visited:
            return
        if len(visited) >= 200:
            raise ValueError("Dependências excedem 200 referências.")
        visited.add(key)
        result.append(reference)
        source = resolve(reference)
        for entry in source.get("inputs", []):
            visit(InformationRef.model_validate(entry), ancestors | {key})

    for reference in references:
        visit(reference, set())
    return result
