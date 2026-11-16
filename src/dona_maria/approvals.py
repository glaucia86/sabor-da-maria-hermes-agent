"""Propostas sem autoridade; revisão e aplicação pertencem ao processo local."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from copy import copy, deepcopy
from datetime import UTC, datetime, timedelta
from functools import lru_cache, reduce
from operator import or_
from pathlib import Path
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, StrictBool, StrictInt, create_model

from dona_maria.candidates import (
    CandidateAdaptation,
    CandidateModel,
    Category,
    RegisterCandidateRequest,
    ShortText,
    UUIDText,
)
from dona_maria.cost_readiness import AcquisitionRequest, OperationalResourceRequest
from dona_maria.ingredients import ConversionRequest, ResolveIngredientRequest
from dona_maria.limits import call_fits
from dona_maria.persistence import SQLiteWorkspaceRepository, _decode_json, _replay_result
from dona_maria.planning import BusinessRuleError, canonical_json, evaluate_plan, fingerprint
from dona_maria.pricing import SaveMenuDecisionRequest
from dona_maria.production import (
    AcceptanceRequest,
    CommandMeta,
    FeedbackRequest,
    KitchenFactsRequest,
    PlanRequest,
    PreferenceInput,
    PreferencesRequest,
)
from dona_maria.provenance import RegisteredWebReference, WebSource, source_fields
from dona_maria.quotes import (
    ConfirmQuoteRequest,
    RegisterQuoteRequest,
    quote_confirmation_statement,
)


class FactPayload(CandidateModel):
    category: Category
    key: ShortText
    value: StrictBool | ShortText
    unit: ShortText | None = None
    context: ShortText | None = None
    replaces_fact_id: UUIDText | None = None


class FactsPayload(CandidateModel):
    facts: Annotated[list[FactPayload], Field(min_length=1, max_length=200)]


class FactsCommand(CandidateModel):
    kind: Literal["record_kitchen_facts"]
    payload: FactsPayload


def _payload_model(name, schema, **overrides):
    # Reutiliza os tipos existentes, excluindo toda autoridade declarada pelo chamador.
    fields = {
        key: (field.rebuild_annotation(), field)
        for key, field in schema.model_fields.items()
        if key not in {*CommandMeta.model_fields, "evidence"}
    }
    return create_model(name, __base__=CandidateModel, **(fields | overrides))


PreferencePayload = _payload_model("PreferencePayload", PreferenceInput)
PreferencesPayload = _payload_model(
    "PreferencesPayload",
    PreferencesRequest,
    preferences=(Annotated[list[PreferencePayload], Field(min_length=1, max_length=200)], ...),
)
FeedbackPayload = _payload_model("FeedbackPayload", FeedbackRequest)
PlanPayload = _payload_model("PlanPayload", PlanRequest)
AcceptancePayload = _payload_model("AcceptancePayload", AcceptanceRequest)
PricePayload = _payload_model("PricePayload", SaveMenuDecisionRequest)
ConversionPayload = _payload_model("ConversionPayload", ConversionRequest)
ResolutionPayload = _payload_model("ResolutionPayload", ResolveIngredientRequest)
ConfirmQuotePayload = _payload_model("ConfirmQuotePayload", ConfirmQuoteRequest)
ReviseQuotePayload = _payload_model("ReviseQuotePayload", RegisterQuoteRequest)
ReviseCandidatePayload = _payload_model("ReviseCandidatePayload", RegisterCandidateRequest)
AcquisitionPayload = _payload_model("AcquisitionPayload", AcquisitionRequest)
OperationalResourcePayload = _payload_model(
    "OperationalResourcePayload", OperationalResourceRequest
)


class AcquisitionCommand(CandidateModel):
    kind: Literal["record_inventory_acquisition"]
    payload: AcquisitionPayload


class OperationalResourceCommand(CandidateModel):
    kind: Literal["record_operational_resource"]
    payload: OperationalResourcePayload


class PreferencesCommand(CandidateModel):
    kind: Literal["record_user_preferences"]
    payload: PreferencesPayload


class FeedbackCommand(CandidateModel):
    kind: Literal["record_recipe_feedback"]
    payload: FeedbackPayload


class PlanCommand(CandidateModel):
    kind: Literal["set_production_plan"]
    payload: PlanPayload


class AcceptanceCommand(CandidateModel):
    kind: Literal["accept_recipe"]
    payload: AcceptancePayload


class PriceCommand(CandidateModel):
    kind: Literal["save_menu_decision"]
    payload: PricePayload


class ConversionCommand(CandidateModel):
    kind: Literal["record_ingredient_conversion"]
    payload: ConversionPayload


class ResolutionCommand(CandidateModel):
    kind: Literal["resolve_recipe_ingredient"]
    payload: ResolutionPayload


class ConfirmQuoteCommand(CandidateModel):
    kind: Literal["confirm_complement_quote"]
    payload: ConfirmQuotePayload


class ReviseQuoteCommand(CandidateModel):
    kind: Literal["register_complement_quote"]
    payload: ReviseQuotePayload


class ReviseCandidateCommand(CandidateModel):
    kind: Literal["register_recipe_candidate"]
    payload: ReviseCandidatePayload


class ProposalRequest(CommandMeta):
    command: Annotated[
        FactsCommand
        | PreferencesCommand
        | FeedbackCommand
        | PlanCommand
        | AcceptanceCommand
        | PriceCommand
        | ConversionCommand
        | ResolutionCommand
        | ConfirmQuoteCommand
        | ReviseQuoteCommand
        | ReviseCandidateCommand
        | AcquisitionCommand
        | OperationalResourceCommand,
        Field(discriminator="kind"),
    ]


_INJECTED_FIELDS = {
    "workspace_id",
    "expected_revision",
    "evidence",
    "recipe_version",
    "expected_recipe_version",
    "quote_version",
    "expected_quote_version",
    "method_version",
    "evaluation_id",
    "plan_item_id",
    "acceptance_id",
    "calculation_id",
    "local_event_id",
    "information_ref",
    "provenance_version",
    "quantity_source",
}


@lru_cache
def _bound_type(annotation):
    if annotation is WebSource:
        return RegisteredWebReference
    if annotation is UUID:
        return Annotated[StrictInt, Field(ge=1)]
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _bound_type(UUID) if args[0] is UUID else Annotated[_bound_type(args[0]), *args[1:]]
    if origin is list:
        return Annotated[list[_bound_type(args[0])], Field(max_length=200)]
    if origin in (UnionType, Union):
        return reduce(or_, (_bound_type(arg) for arg in args))
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        fields = {}
        for name, field in annotation.model_fields.items():
            if name in _INJECTED_FIELDS:
                continue
            public_field = copy(field)
            if field.annotation is UUID:
                public_field.metadata = []
            fields[name] = (_bound_type(field.annotation), public_field)
        return create_model("Bound" + annotation.__name__, __base__=CandidateModel, **fields)
    return annotation


BoundCommand = _bound_type(ProposalRequest.model_fields["command"].annotation)


class BoundProposalRequest(CandidateModel):
    operation_id: UUIDText
    command: Annotated[BoundCommand, Field(discriminator="kind")]


def _expand_bound_command(command, state, snapshot, revision, now):
    quotes = list({q.id: q for q in state.complement_quotes}.values())
    collections = {
        "recipe_id": state.candidates,
        "ingredient_id": [*snapshot.items, *state.complement_ingredients],
        "existing_ingredient_id": [*snapshot.items, *state.complement_ingredients],
        "quote_id": quotes,
        "plan_item_id": state.plan.items if state.plan else [],
        "acceptance_id": state.acceptances,
        "calculation_id": state.pricing_calculations,
        "replaces_fact_id": state.kitchen_facts,
        "replaces_preference_id": state.preferences,
        "replaces_conversion_id": state.ingredient_conversions,
        "replaces_acquisition_id": state.inventory_acquisitions,
        "replaces_resource_id": state.operational_resources,
    }
    information_entities = {
        "RECIPE": state.candidates,
        "CONVERSION": state.ingredient_conversions,
        "INVENTORY_ACQUISITION": state.inventory_acquisitions,
        "OPERATIONAL_RESOURCE": state.operational_resources,
    }

    def expand(value, recipe=None):
        if isinstance(value, list):
            return [expand(item, recipe) for item in value]
        if not isinstance(value, dict):
            return value
        if value.get("recipe_id") is not None:
            index = value["recipe_id"]
            if not 1 <= index <= len(state.candidates):
                raise BusinessRuleError("NOT_FOUND", "Receita não pertence ao contexto.")
            recipe = state.candidates[index - 1]
        result = {}
        for key, item in value.items():
            if key == "entity_id" and value.get("entity") in information_entities:
                entries = information_entities[value["entity"]]
                if not 1 <= item <= len(entries):
                    raise BusinessRuleError("NOT_FOUND", "Informação não pertence ao contexto.")
                result[key] = str(entries[item - 1].id)
                continue
            if item is not None and (key in collections or key == "line_id"):
                entries = (
                    recipe.ingredients if key == "line_id" and recipe else collections.get(key, [])
                )
                if not 1 <= item <= len(entries):
                    raise BusinessRuleError("NOT_FOUND", "Referência não pertence ao contexto.")
                attribute = (
                    "line_id"
                    if key == "line_id"
                    else "plan_item_id"
                    if key == "plan_item_id"
                    else "id"
                )
                result[key] = str(getattr(entries[item - 1], attribute))
            else:
                result[key] = expand(item, recipe)
        return result

    expanded = expand(command)
    kind, payload = expanded["kind"], expanded["payload"]
    recipe = next((r for r in state.candidates if str(r.id) == payload.get("recipe_id")), None)
    quote = next((q for q in quotes if str(q.id) == payload.get("quote_id")), None)
    if kind in (
        "record_ingredient_conversion",
        "resolve_recipe_ingredient",
        "record_operational_resource",
    ):
        payload["recipe_version"] = recipe.version if recipe else None
    if kind == "register_recipe_candidate":
        if recipe:
            payload["expected_recipe_version"] = recipe.version
        candidate = payload["candidate"]
        for review in candidate.get("changes", candidate).get("category_reviews", []) or []:
            review["method_version"] = recipe.version + 1 if recipe else 1
    if kind in ("confirm_complement_quote", "register_complement_quote") and quote:
        payload[
            "quote_version" if kind == "confirm_complement_quote" else "expected_quote_version"
        ] = quote.version
    if kind == "set_production_plan":
        for item in payload["items"]:
            item["recipe_version"] = next(
                r.version for r in state.candidates if str(r.id) == item["recipe_id"]
            )
        for item in payload["quote_selections"]:
            item["quote_version"] = next(q.version for q in quotes if str(q.id) == item["quote_id"])
    if kind == "record_kitchen_facts":
        for fact in payload["facts"]:
            if (
                fact["category"] == "OPERATION"
                and fact["key"] == "production_arrangement"
                and state.plan
            ):
                fact["context"] = f"{state.plan.id}:{state.plan.version}"
    if kind == "accept_recipe":
        item = (
            next((i for i in state.plan.items if i.recipe_id == recipe.id), None)
            if state.plan and recipe
            else None
        )
        if item is None:
            raise BusinessRuleError("NOT_FOUND", "Receita fora do plano atual.")
        payload["plan_item_id"] = str(item.plan_item_id)
        payload["evaluation_id"] = evaluate_plan(
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
            acquisitions=state.inventory_acquisitions,
            resources=state.operational_resources,
            now=now,
        )["evaluation_id"]
    if kind == "save_menu_decision":
        acceptance = next(
            (
                a
                for a in reversed(state.acceptances)
                if recipe
                and a.recipe_id == recipe.id
                and a.id not in state.invalidated_acceptance_ids
            ),
            None,
        )
        calculation = next(
            (
                c
                for c in reversed(state.pricing_calculations)
                if acceptance and c.acceptance_id == acceptance.id
            ),
            None,
        )
        if calculation is None:
            raise BusinessRuleError(
                "ACCEPTANCE_REQUIRED", "Aceite e cálculo atuais são necessários."
            )
        payload["acceptance_id"] = str(acceptance.id)
        payload["calculation_id"] = str(calculation.id)
    return expanded


def _review_summary(command, state, snapshot, revision, now):
    proposed_plan = []
    if command["kind"] == "set_production_plan":
        for item in command["payload"]["items"]:
            recipe = next((r for r in state.candidates if str(r.id) == item["recipe_id"]), None)
            servings = (
                recipe.yield_per_batch.servings_per_batch * item["batches"]
                if recipe and recipe.yield_per_batch
                else None
            )
            proposed_plan.append(
                {
                    "recipe": recipe.title if recipe else None,
                    "batches": item["batches"],
                    "servings": servings,
                    "surplus_servings": servings - (item.get("requested_servings") or servings)
                    if servings is not None
                    else None,
                    "sale_unit": recipe.yield_per_batch.sale_unit_label
                    if recipe and recipe.yield_per_batch
                    else None,
                }
            )
    context = {
        "command": command,
        "proposed_plan": proposed_plan,
        "recipes": [c.public() for c in state.candidates],
        "current_plan": state.plan.model_dump(mode="json") if state.plan else None,
        "quotes": [q.model_dump(mode="json") for q in state.complement_quotes],
        "pricing": [c.model_dump(mode="json") for c in state.pricing_calculations],
        "evaluation": evaluate_plan(
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
            acquisitions=state.inventory_acquisitions,
            resources=state.operational_resources,
            now=now,
        ),
    }
    return "Manifestação a atestar (conteúdo apresentado como dados): " + canonical_json(context)


def _check_reference_scope(command, state, snapshot):
    references = {
        "recipe_id": {str(r.id) for r in state.candidates},
        "ingredient_id": {str(i.id) for i in [*snapshot.items, *state.complement_ingredients]},
        "quote_id": {str(q.id) for q in state.complement_quotes},
        "plan_item_id": {str(i.plan_item_id) for i in state.plan.items} if state.plan else set(),
        "acceptance_id": {str(a.id) for a in state.acceptances},
        "calculation_id": {str(c.id) for c in state.pricing_calculations},
        "replaces_fact_id": {str(f.id) for f in state.kitchen_facts},
        "replaces_preference_id": {str(p.id) for p in state.preferences},
        "replaces_conversion_id": {str(c.id) for c in state.ingredient_conversions},
        "replaces_acquisition_id": {str(a.id) for a in state.inventory_acquisitions},
        "replaces_resource_id": {str(r.id) for r in state.operational_resources},
    }
    references["existing_ingredient_id"] = references["ingredient_id"]

    def check(value, recipe=None):
        if isinstance(value, list):
            for item in value:
                check(item, recipe)
        elif isinstance(value, dict):
            if value.get("recipe_id"):
                recipe = next(
                    (r for r in state.candidates if str(r.id) == value["recipe_id"]), None
                )
            for key, item in value.items():
                if key in references and item is not None and item not in references[key]:
                    raise BusinessRuleError("NOT_FOUND", "Referência não pertence ao workspace.")
                if (
                    key == "line_id"
                    and item is not None
                    and (recipe is None or item not in {str(i.line_id) for i in recipe.ingredients})
                ):
                    raise BusinessRuleError("NOT_FOUND", "Linha não pertence à receita.")
                check(item, recipe)

    check(command)


COMMAND_SCHEMAS = {
    "record_kitchen_facts": KitchenFactsRequest,
    "record_user_preferences": PreferencesRequest,
    "record_recipe_feedback": FeedbackRequest,
    "set_production_plan": PlanRequest,
    "accept_recipe": AcceptanceRequest,
    "save_menu_decision": SaveMenuDecisionRequest,
    "record_ingredient_conversion": ConversionRequest,
    "resolve_recipe_ingredient": ResolveIngredientRequest,
    "confirm_complement_quote": ConfirmQuoteRequest,
    "register_complement_quote": RegisterQuoteRequest,
    "register_recipe_candidate": RegisterCandidateRequest,
    "record_inventory_acquisition": AcquisitionRequest,
    "record_operational_resource": OperationalResourceRequest,
}


def _materialize(document, event_id, now, state):
    kind = document["command"]["kind"]
    payload = deepcopy(document["command"]["payload"])
    statement = "Atestação local da manifestação da cozinheira; proposta " + document["id"] + "."
    if kind == "set_production_plan":
        parts = []
        for item in payload["items"]:
            recipe = next((r for r in state.candidates if str(r.id) == item["recipe_id"]), None)
            if recipe and recipe.yield_per_batch:
                servings = item["batches"] * recipe.yield_per_batch.servings_per_batch
                parts.append(
                    f"{item['batches']} lotes, {servings} porções, "
                    f"sobra de {servings - (item.get('requested_servings') or servings)}"
                )
        statement = "Confirmo a produção: " + "; ".join(parts)
    elif kind == "accept_recipe":
        statement = "Aceito este prato conforme o resumo."
    elif kind == "save_menu_decision":
        statement = "Escolho " + (payload.get("scenario_id") or payload["custom_price"])
    elif kind == "confirm_complement_quote":
        from dona_maria.quotes import ConfirmationScope

        statement = quote_confirmation_statement(ConfirmationScope.model_validate(payload["scope"]))
    evidence = {
        "turn_ref": "local:" + event_id,
        "statement": statement,
        "captured_at": now.isoformat(),
    }
    if kind in {"register_recipe_candidate", "record_ingredient_conversion"}:
        for _, source in source_fields(payload):
            if source["kind"] in {"USER_PROVIDED", "USER_REPORTED_MEASUREMENT", "USER_SIMULATION"}:
                source.update(evidence=evidence, local_event_id=event_id)
    if kind in ("record_kitchen_facts", "record_user_preferences"):
        key = "facts" if kind == "record_kitchen_facts" else "preferences"
        payload[key] = [item | {"evidence": evidence} for item in payload[key]]
    elif "evidence" in COMMAND_SCHEMAS[kind].model_fields:
        payload["evidence"] = evidence
    return COMMAND_SCHEMAS[kind].model_validate(
        {
            "workspace_id": document["workspace_id"],
            "operation_id": document["operation_id"],
            "expected_revision": document["expected_revision"],
            **payload,
        }
    )


def _without_evidence(value):
    if isinstance(value, list):
        return [_without_evidence(item) for item in value]
    if isinstance(value, dict):
        if value.get("kind") in {"USER_PROVIDED", "USER_REPORTED_MEASUREMENT", "USER_SIMULATION"}:
            return {
                key: item
                for key, item in value.items()
                if key not in {"evidence", "local_event_id", "information_ref"}
            }
        return {key: _without_evidence(item) for key, item in value.items() if key != "evidence"}
    return value


def _web_sources(value):
    return {canonical_json(source) for _, source in source_fields(value) if source["kind"] == "WEB"}


def _operator_identity():
    if os.name == "nt":
        return os.getlogin()
    import pwd

    return pwd.getpwuid(os.getuid()).pw_name


def _document(row):
    document = _decode_json(row["document_json"])
    if (
        fingerprint(document) != row["review_hash"]
        or document["id"] != row["id"]
        or document["workspace_id"] != row["workspace_id"]
        or document["operation_id"] != row["operation_id"]
    ):
        raise BusinessRuleError("AUTHORIZATION_REQUIRED", "Proposta inconsistente; não aprovar.")
    return document


PROPOSAL_SCHEMA = """CREATE TABLE user_change_proposals (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    operation_id TEXT NOT NULL, request_hash TEXT NOT NULL,
    document_json TEXT NOT NULL, review_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED')),
    event_json TEXT, result_json TEXT,
    UNIQUE(workspace_id, operation_id))"""


def migrate_proposals(repository: SQLiteWorkspaceRepository, backup: Path) -> None:
    """Migração explícita 1→2; backup consistente inclui páginas presentes no WAL."""
    with repository.transaction() as db:
        repository.check_schema(db)
        versions = [
            r[0] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        if versions != [1]:
            raise sqlite3.DatabaseError("Migração exige schema 1.")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("Banco corrompido.")
        for row in db.execute("SELECT id FROM workspaces"):
            repository.load_state(db, row[0])
        backup = backup.resolve()
        descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with (
            closing(repository._connect("ro")) as source,
            closing(sqlite3.connect(backup)) as target,
        ):
            source.backup(target)
        db.execute(PROPOSAL_SCHEMA)
        db.execute("INSERT INTO schema_migrations VALUES (2, ?)", (datetime.now(UTC).isoformat(),))


class ApprovalService:
    def __init__(
        self,
        repository: SQLiteWorkspaceRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.repository = repository
        self.clock = clock

    @staticmethod
    def _require_schema(db):
        SQLiteWorkspaceRepository.check_schema(db)
        if not db.execute("SELECT 1 FROM schema_migrations WHERE version=2").fetchone():
            raise BusinessRuleError("AUTHORIZATION_REQUIRED", "A migração local é necessária.")

    def propose(self, arguments: dict, *, client_hash: str | None = None) -> dict:
        if client_hash is None and not call_fits(arguments):
            raise BusinessRuleError("INPUT_LIMIT", "Pedido excede o limite permitido.")
        from dona_maria.research import resolve_web_references, verify_web_sources

        arguments = resolve_web_references(
            self.repository, arguments.get("workspace_id"), arguments
        )
        request = ProposalRequest.model_validate(arguments)
        # Autoridade e derivações nunca entram pela proposta, nem como evento reaproveitado.
        payload = arguments.get("command", {}).get("payload", {})
        candidate = payload.get("candidate")
        if (
            request.command.kind == "record_ingredient_conversion"
            and (payload.get("source") or {}).get("kind") == "WEB"
        ):
            raise BusinessRuleError(
                "SOURCE_NOT_LINKED", "Nova fonte web exige resultado registrado."
            )
        for _, source in source_fields(payload):
            if source["kind"] == "DERIVED" or (
                source["kind"] != "WEB"
                and any(key in source for key in ("evidence", "local_event_id", "information_ref"))
            ):
                raise BusinessRuleError(
                    "AUTHORIZATION_REQUIRED", "A origem exige aprovação local exata."
                )
        if isinstance(candidate, dict):
            if candidate.get("provenance_version") is not None or any(
                i.get("quantity_source") is not None for i in candidate.get("ingredients", [])
            ):
                raise BusinessRuleError(
                    "AUTHORIZATION_REQUIRED", "Metadados são produzidos pelo servidor."
                )
        request_json = request.model_dump(mode="json")
        workspace, operation = str(request.workspace_id), str(request.operation_id)
        with self.repository.transaction() as db:
            self._require_schema(db)
            loaded = self.repository.load_state(db, workspace)
            if loaded is None:
                raise BusinessRuleError("NOT_FOUND", "Workspace não encontrado.")
            if isinstance(getattr(request.command.payload, "candidate", None), CandidateAdaptation):
                adaptation = request.command.payload.candidate
                historical = self.repository.historical_recipe(
                    db, workspace, adaptation.origin.derived_from
                )
                request_json["command"]["payload"]["candidate"] = adaptation.resolve(
                    historical
                ).model_dump(mode="json")
            if loaded[1].context_mode != "SIMULATION" and any(
                source["kind"] == "USER_SIMULATION" for _, source in source_fields(payload)
            ):
                raise BusinessRuleError(
                    "CONTEXT_MISMATCH", "Origem fictícia exige contexto SIMULATION."
                )
            from dona_maria.provenance import InformationRef, transitive_inputs

            for _, source in source_fields(payload):
                transitive_inputs(
                    [InformationRef.model_validate(ref) for ref in source.get("inputs", [])],
                    lambda ref: self.repository.resolve_information(db, workspace, ref),
                )
            now = self.clock()
            identifier = str(uuid4())
            normalized = _materialize(
                request_json | {"id": identifier}, str(uuid4()), now, loaded[1]
            ).model_dump(mode="json")
            request_json["command"]["payload"] = _without_evidence(
                {
                    key: value
                    for key, value in normalized.items()
                    if key not in CommandMeta.model_fields
                }
            )
            request_hash = fingerprint(request_json)
            previous = db.execute(
                "SELECT * FROM user_change_proposals WHERE workspace_id=? AND operation_id=?",
                (workspace, operation),
            ).fetchone()
            if previous:
                if previous["request_hash"] != request_hash:
                    raise BusinessRuleError("IDEMPOTENCY_CONFLICT", "Operação já utilizada.")
                return self._view(previous)
            if db.execute(
                "SELECT 1 FROM operations WHERE workspace_id=? AND operation_id=?",
                (workspace, operation),
            ).fetchone():
                raise BusinessRuleError("IDEMPOTENCY_CONFLICT", "Operação já utilizada.")
            revision, state, snapshot = loaded
            if revision != request.expected_revision:
                raise BusinessRuleError("STALE_REVISION", "Recarregue o estado atual.")
            command = request_json["command"]
            _check_reference_scope(command, state, snapshot)
            kind, payload = command["kind"], command["payload"]
            if kind == "register_recipe_candidate":
                previous = next(
                    (r for r in state.candidates if str(r.id) == payload.get("recipe_id")), None
                )
                original = previous.model_dump(mode="json") if previous else {}
                origin = payload["candidate"].get("origin") or {}
                reference = origin.get("derived_from")
                if reference:
                    from dona_maria.provenance import RecipeVersionRef, inherited_sources

                    historical = self.repository.historical_recipe(
                        db, workspace, RecipeVersionRef.model_validate(reference)
                    )
                    original = historical.model_dump(mode="json")
                    inherited = inherited_sources(payload["candidate"], original)
                    if any(
                        source["kind"] == "WEB" and path not in inherited
                        for path, source in source_fields(payload["candidate"])
                    ):
                        raise BusinessRuleError(
                            "SOURCE_NOT_LINKED", "Alteração exige nova origem humana."
                        )
                human = any(s["kind"] != "WEB" for _, s in source_fields(payload["candidate"]))
                if (
                    human
                    and not reference
                    and (
                        _web_sources(payload["candidate"])
                        or previous is not None
                        and previous.provenance_version != "2.0"
                    )
                ):
                    raise BusinessRuleError(
                        "SOURCE_NOT_LINKED", "Adaptação histórica ainda não está habilitada."
                    )
                if not _web_sources(payload["candidate"]).issubset(_web_sources(original)):
                    verify_web_sources(
                        db,
                        workspace,
                        payload["candidate"],
                        purpose="RECIPE",
                        legacy=_web_sources(original),
                    )
                if previous is None and not human and not _web_sources(payload["candidate"]):
                    raise BusinessRuleError(
                        "SOURCE_REQUIRED", "Informe a origem humana da receita."
                    )
                if human and payload["candidate"].get("origin", {}).get("source", {}).get(
                    "kind"
                ) not in {"USER_PROVIDED", "USER_REPORTED_MEASUREMENT", "USER_SIMULATION"}:
                    raise BusinessRuleError(
                        "SOURCE_REQUIRED", "Informe a origem da receita própria."
                    )
            if kind == "register_complement_quote":
                previous = next(
                    (
                        q
                        for q in reversed(state.complement_quotes)
                        if str(q.id) == payload.get("quote_id")
                    ),
                    None,
                )
                if (
                    previous is None
                    or payload["quote"]["source"] != previous.model_dump(mode="json")["source"]
                ):
                    verify_web_sources(db, workspace, payload["quote"]["source"], purpose="QUOTE")
            document = {
                "id": identifier,
                "workspace_id": workspace,
                "operation_id": operation,
                "expected_revision": revision,
                "command": command,
                "dependencies": {
                    "state": fingerprint(state.model_dump(mode="json")),
                    "snapshot": fingerprint(snapshot.model_dump(mode="json")),
                },
                "summary": _review_summary(command, state, snapshot, revision, now),
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "client_hash": client_hash,
            }
            _materialize(document, str(uuid4()), now, state)
            review_hash = fingerprint(document)
            db.execute(
                "INSERT INTO user_change_proposals "
                "VALUES (?, ?, ?, ?, ?, ?, 'PENDING', NULL, NULL)",
                (
                    document["id"],
                    workspace,
                    operation,
                    request_hash,
                    canonical_json(document),
                    review_hash,
                ),
            )
            return document | {"hash": review_hash, "status": "PENDING"}

    def propose_bound(self, workspace_id: str, arguments: dict) -> dict:
        if not call_fits(arguments):
            raise BusinessRuleError("INPUT_LIMIT", "Pedido excede o limite permitido.")
        request = BoundProposalRequest.model_validate(arguments)
        client_hash = fingerprint(request.model_dump(mode="json"))
        existing = next(
            (p for p in self.list(workspace_id) if p["operation_id"] == str(request.operation_id)),
            None,
        )
        if existing:
            if existing["client_hash"] != client_hash:
                raise BusinessRuleError("IDEMPOTENCY_CONFLICT", "Operação já utilizada.")
            return self.public_view(workspace_id, existing)
        loaded = self.repository.load(workspace_id, with_snapshot=True)
        if loaded is None:
            raise BusinessRuleError("NOT_FOUND", "Workspace não encontrado.")
        command = request.model_dump(mode="json")["command"]
        candidate = getattr(request.command.payload, "candidate", None)
        if hasattr(candidate, "changes"):
            command["payload"]["candidate"]["changes"] = candidate.changes.model_dump(
                mode="json", exclude_unset=True
            )
        command = _expand_bound_command(
            command,
            loaded[1],
            loaded[2],
            loaded[0],
            self.clock(),
        )
        proposal = self.propose(
            {
                "command": command,
                "operation_id": str(request.operation_id),
                "workspace_id": workspace_id,
                "expected_revision": loaded[0],
            },
            client_hash=client_hash,
        )
        return self.public_view(workspace_id, proposal)

    def public_view(self, workspace_id: str, proposal: dict) -> dict:
        index = next(
            i for i, p in enumerate(self.list(workspace_id), 1) if p["id"] == proposal["id"]
        )
        return self._public_status(index, proposal)

    @staticmethod
    def _view(row):
        return _document(row) | {"hash": row["review_hash"], "status": row["status"]}

    def inspect(self, workspace_id: str, proposal_id: str) -> dict:
        with closing(self.repository._connect("ro")) as db:
            self._require_schema(db)
            row = db.execute(
                "SELECT * FROM user_change_proposals WHERE workspace_id=? AND id=?",
                (workspace_id, proposal_id),
            ).fetchone()
            if row is None:
                raise BusinessRuleError("NOT_FOUND", "Proposta não pertence ao workspace.")
            return self._view(row)

    def list(self, workspace_id: str) -> list[dict]:
        with closing(self.repository._connect("ro")) as db:
            self.repository.check_schema(db)
            if not db.execute("SELECT 1 FROM schema_migrations WHERE version=2").fetchone():
                return []
            return [
                self._view(row)
                for row in db.execute(
                    "SELECT * FROM user_change_proposals WHERE workspace_id=? ORDER BY rowid",
                    (workspace_id,),
                )
            ]

    def public_list(self, workspace_id: str) -> list[dict]:
        return [self._public_status(index, p) for index, p in enumerate(self.list(workspace_id), 1)]

    def _public_status(self, index, proposal):
        status = proposal["status"]
        if status == "APPROVED":
            status = "APPLIED_HISTORICAL"
        elif status == "PENDING" and self.clock() >= datetime.fromisoformat(proposal["expires_at"]):
            status = "EXPIRED"
        return {"proposal": index, "status": status}

    def reject(self, workspace_id: str, proposal_id: str, review_hash: str) -> dict:
        with self.repository.transaction() as db:
            self._require_schema(db)
            row = db.execute(
                "SELECT * FROM user_change_proposals WHERE workspace_id=? AND id=?",
                (workspace_id, proposal_id),
            ).fetchone()
            if row is None:
                raise BusinessRuleError("NOT_FOUND", "Proposta não pertence ao workspace.")
            document = _document(row)
            if review_hash != row["review_hash"] or row["status"] == "APPROVED":
                raise BusinessRuleError(
                    "AUTHORIZATION_REQUIRED", "Proposta não pode ser rejeitada."
                )
            if row["status"] != "REJECTED":
                event = {
                    "id": str(uuid4()),
                    "operator": _operator_identity(),
                    "action": "REJECT",
                    "proposal_id": proposal_id,
                    "hash": review_hash,
                    "workspace_id": workspace_id,
                    "occurred_at": self.clock().isoformat(),
                }
                db.execute(
                    "UPDATE user_change_proposals SET status='REJECTED', event_json=? "
                    "WHERE workspace_id=? AND id=?",
                    (canonical_json(event), workspace_id, proposal_id),
                )
        return document | {"hash": review_hash, "status": "REJECTED"}

    def approve(
        self, workspace_id: str, proposal_id: str, review_hash: str, *, attest: bool
    ) -> dict:
        if attest is not True:
            raise BusinessRuleError(
                "AUTHORIZATION_REQUIRED", "Ateste a manifestação da cozinheira."
            )
        with self.repository.transaction() as db:
            self._require_schema(db)
            row = db.execute(
                "SELECT * FROM user_change_proposals WHERE workspace_id=? AND id=?",
                (workspace_id, proposal_id),
            ).fetchone()
            if row is None:
                raise BusinessRuleError("NOT_FOUND", "Proposta não pertence ao workspace.")
            document = _document(row)
            if review_hash != row["review_hash"]:
                raise BusinessRuleError(
                    "AUTHORIZATION_REQUIRED", "Conteúdo diverge da revisão local."
                )
            if row["status"] == "APPROVED":
                loaded = self.repository.load_state(db, workspace_id)
                if loaded is None:
                    raise BusinessRuleError("NOT_FOUND", "Workspace não encontrado.")
                self.repository._approval_refs(db, workspace_id)
                operation = db.execute(
                    "SELECT * FROM operations WHERE workspace_id=? AND operation_id=?",
                    (workspace_id, row["operation_id"]),
                ).fetchone()
                return _replay_result(operation, loaded[0])
            if row["status"] != "PENDING":
                raise BusinessRuleError("AUTHORIZATION_REQUIRED", "Proposta rejeitada.")
            now = self.clock()
            if (
                not datetime.fromisoformat(document["created_at"])
                <= now
                < datetime.fromisoformat(document["expires_at"])
            ):
                raise BusinessRuleError("AUTHORIZATION_EXPIRED", "Apresente uma nova proposta.")
            loaded = self.repository.load_state(db, workspace_id)
            if loaded is None:
                raise BusinessRuleError("NOT_FOUND", "Workspace não encontrado.")
            revision, state, snapshot = loaded
            if revision != document["expected_revision"] or document["dependencies"] != {
                "state": fingerprint(state.model_dump(mode="json")),
                "snapshot": fingerprint(snapshot.model_dump(mode="json")),
            }:
                raise BusinessRuleError(
                    "STALE_REVISION", "Estado alterado; apresente nova proposta."
                )
            event = {
                "id": str(uuid4()),
                "operator": _operator_identity(),
                "action": "APPROVE",
                "attestation": "A cozinheira manifestou a decisão sobre o resumo exato.",
                "proposal_id": proposal_id,
                "hash": review_hash,
                "workspace_id": workspace_id,
                "occurred_at": now.isoformat(),
            }
            request = _materialize(document, event["id"], now, state)
            if isinstance(request, RegisterCandidateRequest):
                result = self.repository._register_candidate(
                    db, request, now, locally_approved=True
                )
            else:
                result = self.repository._production_command(
                    db, document["command"]["kind"], request, now, locally_approved=True
                )
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, 'LOCAL_APPROVAL', ?, ?, ?)",
                (event["id"], workspace_id, review_hash, canonical_json(event), now.isoformat()),
            )
            db.execute(
                "UPDATE user_change_proposals SET status='APPROVED', event_json=?, result_json=? "
                "WHERE id=? AND workspace_id=?",
                (canonical_json(event), canonical_json(result), proposal_id, workspace_id),
            )
        return result
