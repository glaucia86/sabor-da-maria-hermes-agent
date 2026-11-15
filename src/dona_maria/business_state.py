"""Serviço público de consulta, produção, aceite e precificação determinística."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator

from dona_maria.approvals import ApprovalService, BoundProposalRequest
from dona_maria.candidates import RegisterCandidateRequest, UUIDText
from dona_maria.ingredients import (
    ConversionRequest,
    ResolveIngredientRequest,
    current_conversions,
    recipe_conversion_applies,
)
from dona_maria.inventory import normalize_name
from dona_maria.limits import call_fits
from dona_maria.persistence import (
    BusinessRuleError,
    SQLiteWorkspaceRepository,
    requires_local_review,
)
from dona_maria.planning import WorkspaceState, evaluate_plan, plan_context, pricing_view
from dona_maria.pricing import (
    FINANCIAL_CONTEXT,
    CalculatePricingRequest,
    SaveMenuDecisionRequest,
    price_option,
)
from dona_maria.production import (
    AcceptanceRequest,
    FeasibilityRequest,
    FeedbackRequest,
    KitchenFactsRequest,
    PlanRequest,
    PreferencesRequest,
)
from dona_maria.provenance import context_labels, source_fields
from dona_maria.quotes import ConfirmQuoteRequest, RegisterQuoteRequest, current_confirmation


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


class AttendanceReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Reference = Annotated[StrictInt, Field(ge=1)]


class AttendanceInventoryRequest(AttendanceReadRequest):
    ingredients: Annotated[list[Reference], Field(max_length=200)] | None = None


class AttendanceFeasibilityRequest(AttendanceReadRequest):
    recipe: Reference
    plan_item: Reference


class AttendancePricingRequest(AttendanceReadRequest):
    operation_id: Annotated[UUIDText, Field(strict=False)]
    recipe: Reference


ATTENDANCE_TOOLS = {
    "get_business_state": (AttendanceReadRequest, "Consulta os fatos e pendências atuais."),
    "get_inventory_snapshot": (AttendanceInventoryRequest, "Consulta os ingredientes disponíveis."),
    "evaluate_recipe_feasibility": (
        AttendanceFeasibilityRequest,
        "Verifica as condições da receita no plano atual.",
    ),
    "evaluate_purchase_plan": (AttendanceReadRequest, "Verifica os faltantes do plano atual."),
    "propose_user_change": (
        BoundProposalRequest,
        "Propõe uma decisão para revisão local; não a aplica.",
    ),
    "calculate_pricing_scenarios": (
        AttendancePricingRequest,
        "Calcula preços após aceite local vigente; não escolhe preço.",
    ),
}


def _attendance_failure(message="Não foi possível consultar. Peça auxílio à pessoa operadora."):
    return {"ok": False, "data": None, "message": message}


def _attendance_provenance(recipe):
    sources = []
    for _, source in source_fields(recipe):
        if source["kind"] == "WEB" and source.get("research_result_id"):
            public = {key: source[key] for key in ("url", "title", "excerpt", "retrieved_at")}
            if public not in sources:
                sources.append(public)
    if sources:
        return {
            "origin": "Pesquisa web registrada; condições da cozinha exigem confirmação.",
            "sources": sources,
        }
    return {
        "origin": (
            "Informada pela cozinheira; campos atestados localmente, sem comprovação independente."
            if recipe.get("provenance_version") == "2.0"
            else "Fonte histórica preservada."
        )
    }


@dataclass(frozen=True)
class AttendanceService:
    """Fronteira de leitura; o contexto é autoridade local, nunca entrada do modelo."""

    database: Path
    workspace_id: str
    mode: str
    _reader: "BusinessStateReader" = field(init=False, repr=False)

    def __post_init__(self):
        try:
            if self.mode != "ATTENDANCE" or not self.database.is_absolute():
                raise ValueError
            database = self.database.resolve(strict=True)
            workspace = str(UUID(self.workspace_id))
            repository = SQLiteWorkspaceRepository(database)
            if not database.is_file() or repository.load(workspace) is None:
                raise ValueError
        except (ValueError, OSError, sqlite3.Error, ValidationError):
            raise ValueError("Atendimento indisponível. Peça auxílio à pessoa operadora.") from None
        object.__setattr__(self, "database", database)
        object.__setattr__(self, "workspace_id", workspace)
        object.__setattr__(self, "_reader", BusinessStateReader(repository))

    def call(self, name: str, arguments: dict) -> dict:
        if name not in ATTENDANCE_TOOLS:
            return _attendance_failure("Esta ação não está disponível neste atendimento.")
        try:
            if not call_fits(arguments):
                return _attendance_failure("O pedido excede o limite. Envie um pedido menor.")
            request = ATTENDANCE_TOOLS[name][0].model_validate(arguments)
        except (ValidationError, TypeError, ValueError, RecursionError):
            return _attendance_failure("Não foi possível usar esses dados. Revise o pedido.")
        try:
            loaded = self._reader.repository.load(self.workspace_id, with_snapshot=True)
            if loaded is None:
                return _attendance_failure()
            _, state, snapshot = loaded
            if name == "propose_user_change":
                proposal = ApprovalService(self._reader.repository).propose_bound(
                    self.workspace_id, arguments
                )
                return {
                    "ok": True,
                    "data": proposal,
                    "message": (
                        "Proposta consultável pela pessoa operadora. "
                        "Consulte o estado atual para decisões vigentes."
                    ),
                }
            if name == "calculate_pricing_scenarios":
                local = ApprovalService(self._reader.repository)
                # Banco legado continua legível; habilitação da escrita exige migração explícita.
                with closing(self._reader.repository._connect("ro")) as db:
                    local._require_schema(db)
                references = self._reader.repository.approval_refs(self.workspace_id)
                if request.recipe > len(state.candidates) or requires_local_review(
                    state, references
                ):
                    return _attendance_failure(
                        "Revise localmente as premissas e o aceite antes de calcular."
                    )
                recipe = state.candidates[request.recipe - 1]
                current = self._reader.get_business_state({"workspace_id": self.workspace_id})
                if not current["ok"]:
                    return _attendance_failure()
                valid = {
                    a["id"] for a in current["data"]["acceptances"] if a["validity"] == "VALID"
                }
                acceptance = next(
                    (
                        a
                        for a in reversed(state.acceptances)
                        if a.recipe_id == recipe.id
                        and str(a.id) in valid
                        and a.evidence.turn_ref in references
                    ),
                    None,
                )
                if acceptance is None:
                    return _attendance_failure("É necessário novo aceite local antes de calcular.")
                expected_revision = self._reader.repository.operation_revision(
                    self.workspace_id, str(request.operation_id), name
                )
                envelope = self._reader.calculate_pricing_scenarios(
                    {
                        "workspace_id": self.workspace_id,
                        "operation_id": str(request.operation_id),
                        "expected_revision": expected_revision,
                        "recipe_id": str(recipe.id),
                        "acceptance_id": str(acceptance.id),
                    }
                )
                if not envelope["ok"]:
                    return _attendance_failure()
                calculation = envelope["data"]["calculation"]
                after = self._reader.get_business_state({"workspace_id": self.workspace_id})
                if not after["ok"] or not any(
                    c["id"] == calculation["id"] and c["validity"] == "VALID"
                    for c in after["data"]["pricing_calculations"]
                ):
                    return _attendance_failure("O cálculo é histórico. Reavalie o plano atual.")
                return {
                    "ok": True,
                    "data": {
                        **context_labels(state.context_mode, state.model_dump(mode="json")),
                        "recipe": request.recipe,
                        "ingredient_cost_per_serving": calculation["cmv_per_serving"],
                        "minimum_price": calculation["minimum"]["price"],
                        "scenarios": [
                            {
                                "scenario": s["scenario_id"],
                                "price": s["price"],
                                "fee": s["display"]["fee"],
                                "surplus_after_fee": s["display"]["result"],
                            }
                            for s in calculation["scenarios"]
                        ],
                        "operational_costs": "Embalagem, gás/energia e trabalho não informados.",
                    },
                    "message": (
                        "Cálculo registrado. A escolha do preço exige manifestação "
                        "e aprovação local."
                    ),
                }
            internal = {"workspace_id": self.workspace_id}
            if name == "get_inventory_snapshot" and request.ingredients is not None:
                if any(index > len(snapshot.items) for index in request.ingredients):
                    return _attendance_failure(
                        "Ingrediente indisponível. Consulte a despensa atual."
                    )
                internal["ingredient_ids"] = [
                    str(snapshot.items[index - 1].id) for index in request.ingredients
                ]
            elif name == "evaluate_recipe_feasibility":
                if (
                    request.recipe > len(state.candidates)
                    or state.plan is None
                    or request.plan_item > len(state.plan.items)
                ):
                    return _attendance_failure("Receita indisponível. Consulte o plano atual.")
                internal.update(
                    recipe_id=str(state.candidates[request.recipe - 1].id),
                    plan_item_id=str(state.plan.items[request.plan_item - 1].plan_item_id),
                )
            envelope = getattr(self._reader, name)(internal)
            if not envelope["ok"]:
                return _attendance_failure()
            data = envelope["data"]
            if name == "get_business_state":
                references = self._reader.repository.approval_refs(self.workspace_id)
                needs_review = requires_local_review(state, references)
                approved_acceptances = {
                    str(a.id) for a in state.acceptances if a.evidence.turn_ref in references
                }
                approved_decisions = {
                    str(d.id) for d in state.menu_decisions if d.evidence.turn_ref in references
                }
                valid_acceptances = {
                    a["recipe_id"]
                    for a in data["acceptances"]
                    if a["id"] in approved_acceptances and a["validity"] == "VALID"
                }
                data["menu"] = [
                    d
                    for d in data["menu"]
                    if d["id"] in approved_decisions
                    and d["acceptance_id"] in approved_acceptances
                    and not needs_review
                ]
                selected_recipes = {d["recipe_id"] for d in data["menu"]}
                priced_recipes = {
                    c["recipe_id"]
                    for c in data["pricing_calculations"]
                    if c["acceptance_id"] in approved_acceptances and c["validity"] == "VALID"
                }
                for recipe in data["candidates"]:
                    recipe.setdefault("status", "DISCOVERED")
                    if recipe["status"] in ("ACCEPTED", "PRICED", "MENU_SELECTED"):
                        recipe["status"] = (
                            "AWAITING_LOCAL_RECONFIRMATION"
                            if needs_review
                            else "MENU_SELECTED"
                            if recipe["id"] in selected_recipes
                            else "PRICED"
                            if recipe["id"] in priced_recipes
                            else "ACCEPTED"
                            if recipe["id"] in valid_acceptances
                            else "AWAITING_LOCAL_RECONFIRMATION"
                        )
                    elif needs_review and recipe["status"] == "READY_FOR_ACCEPTANCE":
                        recipe["status"] = "AWAITING_LOCAL_RECONFIRMATION"
                fact_references = {
                    (f["category"], f["key"]): i for i, f in enumerate(data["kitchen_facts"], 1)
                }
                pending_facts = _attendance_kitchen_facts(
                    {
                        "plan": data["plan"],
                        "kitchen_facts": [
                            f
                            for f in data["kitchen_facts"]
                            if f["evidence"]["turn_ref"] not in references
                        ],
                    }
                )
                pending_preferences = [
                    {
                        "preference": index,
                        **{key: preference[key] for key in ("category", "term", "value")},
                    }
                    for index, preference in enumerate(data["preferences"], 1)
                    if preference["validity"] == "VALID"
                    and preference["evidence"]["turn_ref"] not in references
                ]
                data["kitchen_facts"] = [
                    f for f in data["kitchen_facts"] if f["evidence"]["turn_ref"] in references
                ]
                data["preferences"] = [
                    p for p in data["preferences"] if p["evidence"]["turn_ref"] in references
                ]
                recipes = {
                    recipe["id"]: index for index, recipe in enumerate(data["candidates"], 1)
                }
                projected = {
                    "remaining_budget": data["budget_remaining"],
                    "recipes": [
                        {
                            "recipe": index,
                            "version": recipe["version"],
                            "adapted_from": _attendance_origin(recipe, recipes),
                            "information_origins": [
                                {
                                    "field": path,
                                    "kind": source["kind"],
                                    **{
                                        key: source[key]
                                        for key in ("method", "context", "scenario", "rule")
                                        if key in source
                                    },
                                }
                                for path, source in source_fields(recipe)
                            ],
                            "title": recipe["title"],
                            "status": recipe["status"],
                            "interest": recipe["interest"],
                            **_attendance_provenance(recipe),
                            "missing_information": recipe["gaps"],
                            "ingredients": [
                                {key: ingredient[key] for key in ("description", "quantity")}
                                for ingredient in recipe["ingredients"]
                            ],
                            "conditions": [
                                {
                                    key: requirement[key]
                                    for key in (
                                        "category",
                                        "key",
                                        "condition",
                                        "value",
                                        "unit",
                                        "status",
                                        "reason",
                                    )
                                }
                                for requirement in recipe["requirements"]
                            ],
                        }
                        for index, recipe in enumerate(data["candidates"], 1)
                    ],
                    "plan": [
                        {
                            "plan_item": index,
                            "recipe": recipes[item["recipe_id"]],
                            "batches": item["batches"],
                            "servings": item["servings"],
                        }
                        for index, item in enumerate(
                            data["plan"]["items"] if data["plan"] else [], 1
                        )
                    ],
                    "kitchen_facts": _attendance_kitchen_facts(data),
                    "pending_kitchen_facts": [
                        {"fact": fact_references[(f["category"], f["key"])], **f}
                        for f in pending_facts
                    ],
                    "fact_references": [
                        {"fact": index, "category": category, "key": key}
                        for (category, key), index in fact_references.items()
                    ],
                    "pending_preferences": pending_preferences,
                    "preferences": [
                        {key: preference[key] for key in ("category", "term", "value")}
                        for preference in data["preferences"]
                        if preference["validity"] == "VALID"
                    ],
                    "menu": _attendance_menu(data, recipes),
                    "requires_local_review": needs_review
                    or any(
                        a["id"] not in approved_acceptances and a["validity"] == "VALID"
                        for a in data["acceptances"]
                    ),
                    "proposals": ApprovalService(self._reader.repository).public_list(
                        self.workspace_id
                    ),
                    "next_step": (
                        "Revise as pendências. Decisões exigem manifestação da cozinheira, "
                        "proposta e atestação local da pessoa operadora."
                    ),
                }
                projected.update(
                    _attendance_review_references(state, snapshot, references, self._reader.clock())
                )
            elif name == "get_inventory_snapshot":
                indices = {str(item.id): index for index, item in enumerate(snapshot.items, 1)}
                projected = {
                    "items": [
                        {
                            "ingredient": indices[item["id"]],
                            "name": item["name_original"],
                            **{
                                key: item[key]
                                for key in (
                                    "stock_quantity_original",
                                    "stock_unit_original",
                                    "purchase_quantity_original",
                                    "purchase_unit_original",
                                    "acquisition_total",
                                    "unit_cost",
                                    "dimension",
                                )
                            },
                            "needs_review": bool(item["issues"]),
                        }
                        for item in data["items"]
                    ],
                    "historical_total": data["historical_total"],
                }
            elif name == "evaluate_purchase_plan":
                projected = {
                    key: data[key]
                    for key in (
                        "purchase_status",
                        "disbursement",
                        "remaining_budget",
                    )
                }
                projected["needs_review"] = bool(data["gaps"])
                projected.update(_attendance_purchase(data, state, snapshot))
                review = requires_local_review(
                    state, self._reader.repository.approval_refs(self.workspace_id)
                )
                projected["requires_local_review"] = review
                if review:
                    projected["needs_review"] = True
                    if projected["purchase_status"] == "CONFIRMED":
                        projected["purchase_status"] = "PENDING"
                    projected["questions"].append(
                        {
                            "message": (
                                "Revise localmente o plano e as condições humanas "
                                "antes de confirmar."
                            ),
                            "ingredients": [],
                        }
                    )
            else:
                projected = {
                    "status": data["status"],
                    "missing_information": data["gaps"],
                    "conditions": [
                        {key: requirement[key] for key in ("category", "key", "status", "question")}
                        for requirement in data["requirements"]
                    ],
                }
                review = requires_local_review(
                    state, self._reader.repository.approval_refs(self.workspace_id)
                )
                projected["requires_local_review"] = review
                if review and projected["status"] == "ELIGIBLE":
                    projected["status"] = "PENDING"
                    projected["missing_information"] = [
                        *projected["missing_information"],
                        "Revise localmente as condições humanas e o plano antes do aceite.",
                    ]
            return {
                "ok": True,
                "data": projected
                | context_labels(state.context_mode, state.model_dump(mode="json")),
                "message": "Consulta realizada. Nenhuma alteração foi feita.",
            }
        except Exception:
            # Exceções de persistência/domínio nunca atravessam a fronteira de atendimento.
            return _attendance_failure()


def _attendance_origin(recipe, references):
    reference = (recipe.get("origin") or {}).get("derived_from")
    if not reference:
        return None
    return {"recipe": references.get(reference["recipe_id"]), "version": reference["version"]}


def _attendance_kitchen_facts(data):
    plan = data["plan"]
    context = f"{plan['id']}:{plan['version']}" if plan else None
    return [
        {key: fact[key] for key in ("category", "key", "value", "unit")}
        for fact in data["kitchen_facts"]
        if (fact["category"], fact["key"]) != ("OPERATION", "production_arrangement")
        or (plan is not None and fact["context"] == context)
    ]


def _attendance_review_references(state, snapshot, references, now):
    ingredients = {
        i.id: index for index, i in enumerate([*snapshot.items, *state.complement_ingredients], 1)
    }
    recipes = {r.id: index for index, r in enumerate(state.candidates, 1)}
    current = {c.id for c in current_conversions(state.ingredient_conversions)}
    conversions = []
    for index, conversion in enumerate(state.ingredient_conversions, 1):
        if conversion.id not in current:
            continue
        recipe = next((r for r in state.candidates if r.id == conversion.recipe_id), None)
        if conversion.scope == "RECIPE_MEASURE" and (
            recipe is None or not recipe_conversion_applies(conversion, recipe)
        ):
            continue
        conversions.append(
            {
                "conversion": index,
                "ingredient": ingredients[conversion.ingredient_id],
                "recipe": recipes.get(conversion.recipe_id),
                "line": next(
                    (
                        n
                        for n, line in enumerate(recipe.ingredients, 1)
                        if line.line_id == conversion.line_id
                    ),
                    None,
                )
                if recipe
                else None,
                **{
                    key: getattr(conversion, key)
                    for key in (
                        "from_unit",
                        "to_unit",
                        "factor",
                        "context",
                        "scope",
                        "from_preparation_basis",
                    )
                },
                "requires_local_review": getattr(conversion.evidence, "turn_ref", None)
                not in references,
            }
        )
    quotes = []
    for index, quote in enumerate({q.id: q for q in state.complement_quotes}.values(), 1):
        confirmation = current_confirmation(quote, state.quote_confirmations)
        quotes.append(
            {
                "quote": index,
                "ingredient": ingredients[quote.ingredient_id],
                **{
                    key: getattr(quote, key)
                    for key in (
                        "description",
                        "package_price",
                        "purchase_extra_total",
                        "extra_conditions",
                        "availability",
                        "availability_context",
                        "max_packages",
                        "supplier",
                    )
                },
                "package_quantity": quote.package_quantity.model_dump(mode="json")
                if quote.package_quantity
                else None,
                "status": confirmation.status_at(now)
                if confirmation and confirmation.evidence.turn_ref in references
                else "REVIEW_REQUIRED"
                if confirmation
                else "ESTIMATED",
            }
        )
    return {
        "conversions": conversions,
        "quotes": quotes,
        "complement_ingredients": [
            {
                "ingredient": ingredients[i.id],
                "name": i.name_original,
                "dimension": i.dimension,
                "availability_note": i.availability_note,
            }
            for i in state.complement_ingredients
        ],
        "preference_references": [
            {"preference": index, "category": p.category, "term": p.term}
            for index, p in enumerate(state.preferences, 1)
        ],
    }


def _attendance_menu(data, recipes):
    menu = []
    for decision in data["menu"]:
        calculation = next(
            c for c in data["pricing_calculations"] if c["id"] == decision["calculation_id"]
        )
        # Mesmo cálculo do contrato legado, inclusive para preço personalizado já persistido.
        with localcontext(FINANCIAL_CONTEXT):
            option = price_option(
                Decimal(calculation["cmv_per_serving"]),
                Decimal(decision["price"]),
                Decimal("0"),
                "CUSTOM",
            )
        menu.append(
            {
                "recipe": recipes[decision["recipe_id"]],
                "price": decision["price"],
                "ingredient_cost_per_serving": calculation["cmv_per_serving"],
                "fee": option.display["fee"],
                "surplus_after_fee": option.display["result"],
                "operational_costs": "Embalagem, gás/energia e trabalho não informados.",
            }
        )
    return menu


def _attendance_purchase(data, state, snapshot):
    names = {
        str(item.id): item.name_original
        for item in [*snapshot.items, *state.complement_ingredients]
    }
    names.update(
        {
            str(ingredient.line_id): ingredient.description
            for recipe in state.candidates
            for ingredient in recipe.ingredients
        }
    )
    names.update(
        {str(quote.id): names[str(quote.ingredient_id)] for quote in state.complement_quotes}
    )
    messages = {
        "MISSING_INFORMATION": (
            "Precisamos confirmar a quantidade, o estoque ou uma oferta para este ingrediente."
        ),
        "UNIT_CONVERSION_REQUIRED": (
            "Precisamos esclarecer a medida e a unidade antes de avaliar a compra."
        ),
        "PRICE_UNCONFIRMED": "O preço e as condições da oferta ainda precisam de confirmação.",
        "QUOTE_EXPIRED": "A oferta expirou; precisamos de condições atuais.",
        "STALE_QUOTE": "A oferta mudou; precisamos revisar suas condições.",
        "BUDGET_EXCEEDED": (
            "A compra ultrapassa o orçamento de R$ 80,00. Revise as quantidades ou alternativas."
        ),
    }
    questions = []
    for gap in data["gaps"]:
        message = messages.get(
            gap.partition(":")[0], "Há uma pendência de compra. Revise as condições do plano."
        )
        ingredients = sorted({name for identifier, name in names.items() if identifier in gap})
        question = {"message": message, "ingredients": ingredients}
        if question not in questions:
            questions.append(question)
    return {
        "demand": [
            {
                "name": line["source"]["name_original"],
                **{
                    key: line[key]
                    for key in (
                        "unit",
                        "required",
                        "stock_available",
                        "stock_used",
                        "shortage",
                    )
                },
            }
            for line in data["demand"]
        ],
        "questions": questions,
    }


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

    def record_user_preferences(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command("record_user_preferences", PreferencesRequest, arguments)

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

    def confirm_complement_quote(self, arguments: dict[str, object]) -> dict[str, object]:
        return self._production_command("confirm_complement_quote", ConfirmQuoteRequest, arguments)

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
            lambda request: self.repository.purchase_evaluation(
                str(request.workspace_id), self.clock()
            ),
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
        except (sqlite3.Error, ValidationError) as exc:
            return _storage_unavailable(str(request.workspace_id), cause=exc)

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
        except (sqlite3.Error, ValidationError) as exc:
            return _storage_unavailable(workspace_id, cause=exc)
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
        except (sqlite3.Error, ValidationError) as exc:
            return _storage_unavailable(workspace_id, cause=exc)
        if loaded is not None:
            revision, state, snapshot = loaded
            now = self.clock()
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
            from dona_maria.ingredients import apply_overlays

            effective, _ = apply_overlays(state.candidates, snapshot, state.ingredient_conversions)
            state = state.model_copy(
                update={
                    "candidates": [
                        resolved if original.provenance_version == "2.0" else original
                        for original, resolved in zip(state.candidates, effective, strict=True)
                    ]
                }
            )
            return ReadErrorEnvelope(
                ok=True,
                workspace_id=workspace_id,
                revision=revision,
                data=_project_business_state(state, evaluation, now),
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


def _project_business_state(state: WorkspaceState, evaluation: dict, now: datetime) -> dict:
    """Projeta os dados carregados sem I/O ou alteração dos modelos de negócio."""
    acceptances = [
        acceptance.model_dump(mode="json")
        | {
            "validity": "VALID"
            if acceptance.id not in state.invalidated_acceptance_ids
            and acceptance.fingerprint == evaluation["fingerprint"]
            and evaluation["purchase_status"] == "CONFIRMED"
            else "INVALIDATED",
        }
        for acceptance in state.acceptances
    ]
    prices = pricing_view(state, evaluation)
    current_preferences = {(p.category, normalize_name(p.term)): p.id for p in state.preferences}
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
                    entry["status"] != "ELIGIBLE" for entry in evaluation["feasibility_by_recipe"]
                )
                else "INGREDIENT_CHECK_PENDING"
                if evaluation["purchase_status"] != "CONFIRMED"
                else "DISCOVERED"
                if candidate["interest"] == "UNDECIDED"
                else "READY_FOR_ACCEPTANCE"
            )
        elif feedback:
            candidate["status"] = "FEASIBILITY_PENDING"
        if any(a["recipe_id"] == candidate["id"] and a["validity"] == "VALID" for a in acceptances):
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
    labels = plan_context(state)
    evaluation = evaluation | labels
    for entry in [
        *acceptances,
        *prices["pricing_calculations"],
        *prices["menu_decisions"],
        *prices["menu"],
    ]:
        if labels["hypothetical"]:
            entry.update(
                labels
                | {
                    "depends_on_simulation": state.decision_simulation_dependencies.get(
                        UUID(entry["id"]), labels["depends_on_simulation"]
                    )
                }
            )
    return {
        **context_labels(state.context_mode, state.model_dump(mode="json")),
        "inventory_snapshot_id": str(state.inventory_snapshot_id),
        "budget_initial": state.budget_initial,
        "budget_remaining": evaluation["remaining_budget"]
        if state.plan and state.plan.items
        else "80.00",
        "candidates": candidates,
        "complement_ingredients": [i.model_dump(mode="json") for i in state.complement_ingredients],
        "complement_quotes": [
            quote.public(current_confirmation(quote, state.quote_confirmations), now)
            for quote in state.complement_quotes
        ],
        "ingredient_conversions": [c.model_dump(mode="json") for c in state.ingredient_conversions],
        "ingredient_resolutions": [r.model_dump(mode="json") for r in state.ingredient_resolutions],
        "acceptances": acceptances,
        **prices,
        "evaluation": evaluation,
        "plan": state.plan.model_dump(mode="json") if state.plan else None,
        "kitchen_facts": [fact.model_dump(mode="json") for fact in state.kitchen_facts],
        "preferences": [
            p.model_dump(mode="json")
            | {
                "validity": "VALID"
                if p.id == current_preferences[(p.category, normalize_name(p.term))]
                else "INVALIDATED"
            }
            for p in state.preferences
        ],
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
    }


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
