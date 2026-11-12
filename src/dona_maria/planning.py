"""Agregado e regras determinísticas de produção; sem SQLite, MCP ou rede."""

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from dona_maria.candidates import CandidateInput, RecipeCandidate
from dona_maria.inventory import InventorySnapshot
from dona_maria.pricing import (
    FINANCIAL_CONTEXT,
    CalculatePricingRequest,
    MenuDecision,
    PricingCalculation,
    SaveMenuDecisionRequest,
    calculate_pricing,
    explicit_price_choice,
    price_option,
)
from dona_maria.production import (
    AcceptanceRequest,
    FeedbackRequest,
    KitchenFact,
    KitchenFactsRequest,
    PlanItem,
    PlanRequest,
    ProductionPlan,
    RecipeAcceptance,
    RecipeFeedback,
    explicit_acceptance,
)


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
    feedback: list[RecipeFeedback] = []
    plan: ProductionPlan | None = None
    kitchen_facts: list[KitchenFact] = []
    acceptances: list[RecipeAcceptance] = []
    invalidated_acceptance_ids: list[UUID] = []
    pricing_calculations: list[PricingCalculation] = []
    menu_decisions: list[MenuDecision] = []

    @model_validator(mode="after")
    def valid_references(self):
        recipes = {recipe.id: recipe for recipe in self.candidates}
        collections = [
            [recipe.id for recipe in self.candidates],
            [item.recipe_id for item in self.feedback],
            [(fact.category, fact.key) for fact in self.kitchen_facts],
            [fact.id for fact in self.kitchen_facts],
            [acceptance.id for acceptance in self.acceptances],
            [calculation.id for calculation in self.pricing_calculations],
            [decision.id for decision in self.menu_decisions],
            self.invalidated_acceptance_ids,
        ]
        if self.plan:
            collections.extend(
                [
                    [item.recipe_id for item in self.plan.items],
                    [item.plan_item_id for item in self.plan.items],
                    [item.position for item in self.plan.items],
                ]
            )
            if self.plan.inventory_snapshot_id != self.inventory_snapshot_id:
                raise ValueError("Fotografia do plano não pertence ao workspace.")
            for item in self.plan.items:
                recipe = recipes.get(item.recipe_id)
                if recipe is None or item.recipe_version > recipe.version:
                    raise ValueError("Referência de produção inválida.")
                if item.business_recipe_version > recipe.business_version:
                    raise ValueError("Versão material inválida.")
                if item.business_recipe_version == recipe.business_version:
                    servings = (
                        recipe.yield_per_batch.servings_per_batch * item.batches
                        if recipe.yield_per_batch
                        else None
                    )
                    surplus = (
                        None
                        if servings is None
                        else servings - (item.requested_servings or servings)
                    )
                    if (item.servings, item.surplus_servings) != (servings, surplus):
                        raise ValueError("Rendimento derivado inconsistente.")
        if any(len(values) != len(set(values)) for values in collections):
            raise ValueError("Identidade ou chave duplicada no agregado.")
        if any(item.recipe_id not in recipes for item in [*self.feedback, *self.acceptances]):
            raise ValueError("Decisão não pertence ao workspace.")
        if not set(self.invalidated_acceptance_ids) <= {a.id for a in self.acceptances}:
            raise ValueError("Invalidação sem aceite histórico.")
        plan_items = {item.plan_item_id: item for item in self.plan.items} if self.plan else {}
        for acceptance in self.acceptances:
            if acceptance.recipe_version > recipes[acceptance.recipe_id].version:
                raise ValueError("Aceite referencia versão de receita inexistente.")
            if acceptance.id in self.invalidated_acceptance_ids:
                continue
            item = plan_items.get(acceptance.plan_item_id)
            if (
                item is None
                or item.recipe_id != acceptance.recipe_id
                or item.batches != acceptance.batches
            ):
                raise ValueError("Aceite não corresponde ao item/escala do plano.")
        acceptances = {a.id: a for a in self.acceptances}
        calculations = {c.id: c for c in self.pricing_calculations}
        for calculation in self.pricing_calculations:
            acceptance = acceptances.get(calculation.acceptance_id)
            if acceptance is None or (
                calculation.recipe_id,
                calculation.fingerprint,
                calculation.batches,
            ) != (acceptance.recipe_id, acceptance.fingerprint, acceptance.batches):
                raise ValueError("Cálculo sem aceite/escala correspondente.")
            if any(
                a.recipe_id != calculation.recipe_id or a.plan_item_id != acceptance.plan_item_id
                for a in calculation.allocations
            ):
                raise ValueError("Alocação não pertence ao cálculo.")
        for decision in self.menu_decisions:
            calculation = calculations.get(decision.calculation_id)
            if calculation is None or (
                decision.recipe_id,
                decision.acceptance_id,
                decision.fingerprint,
            ) != (calculation.recipe_id, calculation.acceptance_id, calculation.fingerprint):
                raise ValueError("Decisão sem cálculo correspondente.")
            option = next(
                (s for s in calculation.scenarios if s.scenario_id == decision.scenario_id), None
            )
            if (decision.scenario_id is None) == (decision.custom_price is None):
                raise ValueError("Decisão precisa de exatamente uma escolha.")
            if decision.price != (
                option.price if option else decision.custom_price
            ) or not explicit_price_choice(decision):
                raise ValueError("Preço não corresponde à escolha humana.")
            with localcontext(FINANCIAL_CONTEXT):
                if Decimal(decision.price) < Decimal(calculation.minimum.price):
                    raise ValueError("Decisão abaixo do piso técnico.")
        return self


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class BusinessRuleError(Exception):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        self.code, self.message = code, message
        self.details = details or {}
        super().__init__(message)


def _calculate_pricing(state, request: CalculatePricingRequest, snapshot, revision, now):
    evaluation = evaluate_plan(
        state.candidates,
        state.plan,
        state.kitchen_facts,
        state.feedback,
        snapshot,
        state.pricing_policy_version,
        revision,
    )
    acceptance = next(
        (
            a
            for a in state.acceptances
            if a.id == request.acceptance_id and a.recipe_id == request.recipe_id
        ),
        None,
    )
    if acceptance is None:
        raise BusinessRuleError(
            "ACCEPTANCE_REQUIRED", "Aceite vigente necessário antes do cálculo."
        )
    if (
        acceptance.id in state.invalidated_acceptance_ids
        or acceptance.fingerprint != evaluation["fingerprint"]
    ):
        raise BusinessRuleError("STALE_EVALUATION", "Reconfirme o resumo atual antes de calcular.")
    recipe = next(r for r in state.candidates if r.id == request.recipe_id)
    item = next(i for i in state.plan.items if i.plan_item_id == acceptance.plan_item_id)
    calculation = next(
        (
            c
            for c in state.pricing_calculations
            if c.acceptance_id == acceptance.id
            and c.fingerprint == evaluation["fingerprint"]
            and c.pricing_policy_version == state.pricing_policy_version
        ),
        None,
    )
    if calculation is None:
        calculation = calculate_pricing(
            recipe, item, acceptance, snapshot, state.pricing_policy_version, now
        )
        state.pricing_calculations.append(calculation)
    return {"calculation": calculation.model_dump(mode="json") | {"validity": "VALID"}}


def _save_menu_decision(state, request: SaveMenuDecisionRequest, snapshot, revision, now):
    evaluation = evaluate_plan(
        state.candidates,
        state.plan,
        state.kitchen_facts,
        state.feedback,
        snapshot,
        state.pricing_policy_version,
        revision,
    )
    acceptance = next(
        (
            a
            for a in state.acceptances
            if a.id == request.acceptance_id and a.recipe_id == request.recipe_id
        ),
        None,
    )
    if acceptance is None:
        raise BusinessRuleError(
            "ACCEPTANCE_REQUIRED", "Aceite vigente necessário antes da escolha."
        )
    calculation = next(
        (
            c
            for c in state.pricing_calculations
            if c.id == request.calculation_id
            and c.acceptance_id == acceptance.id
            and c.recipe_id == request.recipe_id
        ),
        None,
    )
    if (
        calculation is None
        or acceptance.id in state.invalidated_acceptance_ids
        or acceptance.fingerprint != evaluation["fingerprint"]
        or calculation.fingerprint != evaluation["fingerprint"]
    ):
        raise BusinessRuleError("STALE_EVALUATION", "Apresente cálculo vigente antes da escolha.")
    with localcontext(FINANCIAL_CONTEXT):
        cost = Decimal(calculation.cmv_per_serving)
        if request.custom_price is not None:
            option = price_option(cost, Decimal(request.custom_price), Decimal("0"), "CUSTOM")
            if Decimal("0.90") * Decimal(request.custom_price) < cost:
                raise BusinessRuleError(
                    "PRICE_BELOW_MINIMUM",
                    "Preço não cobre taxa e ingredientes.",
                    details={
                        "minimum_price": calculation.minimum.price,
                        "result_theoretical": option.result_theoretical,
                    },
                )
        else:
            option = next(s for s in calculation.scenarios if s.scenario_id == request.scenario_id)
    if not explicit_price_choice(request):
        raise BusinessRuleError(
            "USER_CONFIRMATION_REQUIRED", "Peça escolha inequívoca do cenário ou preço exato."
        )
    decision = MenuDecision(
        id=str(uuid4()),
        recipe_id=str(request.recipe_id),
        acceptance_id=str(acceptance.id),
        calculation_id=str(calculation.id),
        scenario_id=request.scenario_id,
        custom_price=request.custom_price,
        price=option.price,
        evidence=request.evidence,
        fingerprint=calculation.fingerprint,
        decided_at=now,
    )
    state.menu_decisions.append(decision)
    public = decision.model_dump(mode="json") | {"validity": "VALID"}
    return {
        "decision": public,
        "menu": pricing_view(state, evaluation)["menu"],
        "chosen_option": option.model_dump(mode="json"),
    }


def pricing_view(state: WorkspaceState, evaluation: dict) -> dict:
    accepted = {
        a.id
        for a in state.acceptances
        if a.id not in state.invalidated_acceptance_ids
        and a.fingerprint == evaluation["fingerprint"]
    }
    calculations = [
        c.model_dump(mode="json")
        | {
            "validity": "VALID"
            if c.acceptance_id in accepted
            and c.fingerprint == evaluation["fingerprint"]
            and c.pricing_policy_version == state.pricing_policy_version
            else "INVALIDATED"
        }
        for c in state.pricing_calculations
    ]
    current_calculations = {c["id"] for c in calculations if c["validity"] == "VALID"}
    latest = {d.recipe_id: d.id for d in state.menu_decisions}
    decisions = [
        d.model_dump(mode="json")
        | {
            "validity": "VALID"
            if str(d.calculation_id) in current_calculations and d.id == latest[d.recipe_id]
            else "INVALIDATED"
        }
        for d in state.menu_decisions
    ]
    return dict(
        pricing_calculations=calculations,
        menu_decisions=decisions,
        menu=[d for d in decisions if d["validity"] == "VALID"],
    )


def evaluate_feasibility(
    recipe: RecipeCandidate,
    item: PlanItem,
    facts: list[KitchenFact],
    *,
    plan: ProductionPlan | None = None,
    candidates: list[RecipeCandidate] | None = None,
) -> dict:
    gaps = list(recipe.public()["gaps"])
    needs_arrangement = item.batches > 1 or (plan is not None and len(plan.items) > 1)
    sequential = plan is not None and any(
        fact.category == "OPERATION"
        and fact.key == "production_arrangement"
        and fact.value == "SEQUENTIAL"
        and fact.context == f"{plan.id}:{plan.version}"
        for fact in facts
    )
    if needs_arrangement and not sequential:
        gaps.append("Confirme sequência, capacidade compartilhada e tempo para o plano atual.")
    if recipe.business_version != item.business_recipe_version:
        gaps.append("Versão da receita mudou; reconfirme o plano.")
    requirements = []
    for requirement in recipe.requirements:
        fact = next(
            (
                fact
                for fact in facts
                if (fact.category, fact.key) == (requirement.category, requirement.key)
            ),
            None,
        )
        status = "UNKNOWN"
        if (
            requirement.condition in {"PRESENT", "SKILL_KNOWN"}
            and fact
            and isinstance(fact.value, bool)
        ):
            status = "CONFIRMED" if fact.value else "BLOCKED"
        elif (
            requirement.condition == "EXPLICIT_CONDITION" and fact and requirement.value is not None
        ):
            matches = (
                type(fact.value) is type(requirement.value) and fact.value == requirement.value
            )
            status = "CONFIRMED" if matches else "BLOCKED"
        elif requirement.condition in {"MIN_CAPACITY", "MIN_AVAILABLE_TIME"} and fact:
            numeric = r"[0-9]{1,12}(?:\.[0-9]{1,6})?"
            if (
                isinstance(requirement.value, str)
                and re.fullmatch(numeric, requirement.value)
                and isinstance(fact.value, str)
                and re.fullmatch(numeric, fact.value)
                and requirement.unit is not None
                and requirement.unit == fact.unit
                and Decimal(requirement.value) > 0
            ):
                minimum = Decimal(requirement.value)
                if sequential and requirement.condition == "MIN_AVAILABLE_TIME" and candidates:
                    with localcontext() as context:
                        context.prec = 34
                        minimum = sum(
                            (
                                Decimal(r.value) * i.batches
                                for i in plan.items
                                for c in candidates
                                if c.id == i.recipe_id
                                for r in c.requirements
                                if (r.category, r.key, r.condition, r.unit)
                                == (
                                    requirement.category,
                                    requirement.key,
                                    requirement.condition,
                                    requirement.unit,
                                )
                                and isinstance(r.value, str)
                                and re.fullmatch(numeric, r.value)
                            ),
                            Decimal("0"),
                        )
                status = "CONFIRMED" if Decimal(fact.value) >= minimum else "BLOCKED"
        requirements.append(
            dict(
                id=str(requirement.id),
                category=requirement.category,
                key=requirement.key,
                status=status,
                fact_ids=[str(fact.id)] if fact else [],
                question=(
                    f"Confirme {requirement.key} para {item.batches} lote(s): {requirement.reason}"
                )
                if status == "UNKNOWN"
                else None,
            )
        )
    blocked = any(requirement["status"] == "BLOCKED" for requirement in requirements)
    pending = gaps or any(requirement["status"] == "UNKNOWN" for requirement in requirements)
    return dict(
        recipe_id=str(recipe.id),
        plan_item_id=str(item.plan_item_id),
        status="BLOCKED" if blocked else "PENDING" if pending else "ELIGIBLE",
        requirements=requirements,
        gaps=gaps,
        category_status=recipe.public()["category_status"],
    )


def evaluate_plan(
    candidates: list[RecipeCandidate],
    plan: ProductionPlan | None,
    facts: list[KitchenFact],
    feedback: list[RecipeFeedback],
    snapshot: InventorySnapshot,
    policy_version: str,
    revision: int,
) -> dict:
    active_ids = {item.recipe_id for item in plan.items} if plan else set()
    relevant_keys = {
        (r.category, r.key) for c in candidates if c.id in active_ids for r in c.requirements
    }
    if plan and (len(plan.items) > 1 or any(item.batches > 1 for item in plan.items)):
        relevant_keys.add(("OPERATION", "production_arrangement"))
    inputs = dict(
        candidates=[
            dict(
                id=str(recipe.id),
                version=recipe.business_version,
                content=recipe.business_content(),
            )
            for recipe in candidates
            if recipe.id in active_ids
        ],
        plan=plan.model_dump(mode="json") if plan else None,
        facts=[
            fact.model_dump(mode="json")
            for fact in facts
            if (fact.category, fact.key) in relevant_keys
        ],
        feedback=[
            item.model_dump(mode="json") for item in feedback if item.recipe_id in active_ids
        ],
        snapshot=snapshot.model_dump(mode="json"),
        pricing_policy_version=policy_version,
    )
    if inputs["plan"]:
        for item in inputs["plan"]["items"]:
            item["recipe_version"] = item["business_recipe_version"]
    digest = fingerprint(inputs)
    feasibility = []
    gaps = [] if plan and plan.items else ["Confirme o plano de produção."]
    demand = {}
    with localcontext() as context:
        context.prec = 34
        for item in plan.items if plan else []:
            recipe = next(recipe for recipe in candidates if recipe.id == item.recipe_id)
            feasibility.append(
                evaluate_feasibility(recipe, item, facts, plan=plan, candidates=candidates)
            )
            for ingredient in recipe.ingredients:
                if not ingredient.quantity or not ingredient.ingredient_id:
                    gaps.append(f"MISSING_INFORMATION: {ingredient.line_id}")
                    continue
                if ingredient.preparation_basis != "RAW":
                    gaps.append(
                        f"UNIT_CONVERSION_REQUIRED: base cru/cozido de {ingredient.line_id}"
                    )
                    continue
                quantity = ingredient.quantity
                amount = Decimal(quantity.value) * item.batches
                if quantity.unit in {"kg", "L"}:
                    amount *= 1000
                key = str(ingredient.ingredient_id)
                demand[key] = demand.get(key, Decimal("0")) + amount
        lines = []
        for ingredient_id, amount in sorted(demand.items()):
            stock = next(stock for stock in snapshot.items if str(stock.id) == ingredient_id)
            available = stock.stock_quantity_base
            if available is None:
                gaps.append(f"MISSING_INFORMATION: estoque de {ingredient_id}")
            used = min(available, amount) if available is not None else None
            shortage = max(amount - available, Decimal("0")) if available is not None else None
            lines.append(
                dict(
                    ingredient_id=ingredient_id,
                    unit=stock.dimension,
                    required=format(amount, "f"),
                    stock_available=format(available, "f") if available is not None else None,
                    stock_used=format(used, "f") if used is not None else None,
                    shortage=format(shortage, "f") if shortage is not None else None,
                    source=stock.model_dump(mode="json"),
                )
            )
    sufficient = not gaps and all(
        line["shortage"] is not None and Decimal(line["shortage"]) == 0 for line in lines
    )
    evaluation_id = hashlib.sha256(f"{digest}:{revision}".encode("ascii")).hexdigest()
    return dict(
        evaluation_id=evaluation_id,
        fingerprint=digest,
        workspace_revision=revision,
        feasibility_by_recipe=feasibility,
        demand=lines,
        gaps=gaps,
        purchase_status="CONFIRMED" if sufficient else "PENDING",
        disbursement="0.00" if sufficient else None,
        remaining_budget="80.00" if sufficient else None,
    )


def _accept_recipe(
    state: WorkspaceState,
    request: AcceptanceRequest,
    evaluation: dict,
    now: datetime,
) -> dict:
    recipe = next((recipe for recipe in state.candidates if recipe.id == request.recipe_id), None)
    item = (
        next(
            (
                item
                for item in state.plan.items
                if item.recipe_id == request.recipe_id and item.plan_item_id == request.plan_item_id
            ),
            None,
        )
        if state.plan
        else None
    )
    if recipe is None or item is None:
        raise BusinessRuleError("NOT_FOUND", "Receita/item não pertence ao plano do workspace.")
    if request.evaluation_id != evaluation["evaluation_id"]:
        raise BusinessRuleError(
            "STALE_EVALUATION", "Apresente a avaliação atual antes de pedir aceite."
        )
    statuses = [entry["status"] for entry in evaluation["feasibility_by_recipe"]]
    if "BLOCKED" in statuses:
        raise BusinessRuleError("CONSTRAINT_BLOCKED", "Há impedimento no plano ativo.")
    if "PENDING" in statuses:
        raise BusinessRuleError("MISSING_INFORMATION", "Esclareça as condições do plano ativo.")
    if evaluation["purchase_status"] != "CONFIRMED":
        raise BusinessRuleError(
            "MISSING_INFORMATION", "Ingredientes insuficientes ou sem medida sustentada."
        )
    feedback = next((item for item in state.feedback if item.recipe_id == request.recipe_id), None)
    if feedback is None or feedback.feedback != "INTERESTED":
        raise BusinessRuleError(
            "USER_CONFIRMATION_REQUIRED", "Confirme o interesse pela candidata."
        )
    if not explicit_acceptance(request.evidence):
        raise BusinessRuleError(
            "USER_CONFIRMATION_REQUIRED", "Peça um aceite inequívoco do resumo atual."
        )
    acceptance = RecipeAcceptance(
        id=str(uuid4()),
        recipe_id=str(recipe.id),
        recipe_version=recipe.version,
        plan_item_id=str(item.plan_item_id),
        batches=item.batches,
        evaluation_id=evaluation["evaluation_id"],
        fingerprint=evaluation["fingerprint"],
        evidence=request.evidence,
        accepted_at=now,
    )
    state.acceptances.append(acceptance)
    return {
        "acceptance": acceptance.model_dump(mode="json") | {"validity": "VALID"},
        "summary": evaluation,
    }


def _apply_production_command(
    state: WorkspaceState,
    request: FeedbackRequest | PlanRequest | KitchenFactsRequest,
    now: datetime,
) -> dict:
    if isinstance(request, KitchenFactsRequest):
        active = {item.recipe_id for item in state.plan.items} if state.plan else set()
        relevant = {
            (r.category, r.key) for c in state.candidates if c.id in active for r in c.requirements
        }
        if state.plan and (
            len(state.plan.items) > 1 or any(i.batches > 1 for i in state.plan.items)
        ):
            relevant.add(("OPERATION", "production_arrangement"))
        if relevant & {(fact.category, fact.key) for fact in request.facts}:
            _invalidate_acceptances(state)
        saved = []
        for new in request.facts:
            previous = next(
                (
                    fact
                    for fact in state.kitchen_facts
                    if (fact.category, fact.key) == (new.category, new.key)
                ),
                None,
            )
            if (previous.id if previous else None) != new.replaces_fact_id:
                raise BusinessRuleError("STALE_REVISION", "Substituição exige ID do fato atual.")
            fact = KitchenFact(
                **new.model_dump(mode="json"),
                id=str(uuid4()),
                version=previous.version + 1 if previous else 1,
                recorded_at=now,
            )
            state.kitchen_facts = [f for f in state.kitchen_facts if f is not previous]
            state.kitchen_facts.append(fact)
            saved.append(fact.model_dump(mode="json"))
        return {"facts": saved}
    if isinstance(request, FeedbackRequest):
        if not any(item.id == request.recipe_id for item in state.candidates):
            raise BusinessRuleError("NOT_FOUND", "Candidata não pertence ao workspace.")
        feedback = RecipeFeedback(
            recipe_id=str(request.recipe_id),
            feedback=request.feedback,
            evidence=request.evidence,
        )
        state.feedback = [item for item in state.feedback if item.recipe_id != request.recipe_id]
        state.feedback.append(feedback)
        if state.plan and any(item.recipe_id == request.recipe_id for item in state.plan.items):
            _invalidate_acceptances(state)
            if request.feedback == "REJECTED":
                state.plan.items = [
                    item for item in state.plan.items if item.recipe_id != request.recipe_id
                ]
                state.plan.version += 1
        return {"feedback": feedback.model_dump(mode="json")}
    items = []
    for item in sorted(request.items, key=lambda item: item.position):
        recipe = next((recipe for recipe in state.candidates if recipe.id == item.recipe_id), None)
        if recipe is None:
            raise BusinessRuleError("NOT_FOUND", "Candidata não pertence ao workspace.")
        if any(
            feedback.recipe_id == recipe.id and feedback.feedback == "REJECTED"
            for feedback in state.feedback
        ):
            raise BusinessRuleError(
                "CONSTRAINT_BLOCKED", "Candidata recusada; pergunte por outra opção."
            )
        if recipe.version != item.recipe_version:
            raise BusinessRuleError("STALE_REVISION", "Versão da receita não é atual.")
        servings = (
            recipe.yield_per_batch.servings_per_batch * item.batches
            if recipe.yield_per_batch
            else None
        )
        if item.requested_servings is not None and recipe.yield_per_batch:
            per_batch = recipe.yield_per_batch.servings_per_batch
            if item.batches != (item.requested_servings + per_batch - 1) // per_batch:
                raise BusinessRuleError("VALIDATION_ERROR", "Confirme os lotes inteiros ajustados.")
            surplus = servings - item.requested_servings
            statement = request.evidence.statement.casefold()
            if surplus and not (
                statement.startswith("confirmo ")
                and re.search(rf"\b{item.batches} lotes?\b", statement)
                and re.search(rf"\b{servings} porç(?:ões|ão)\b", statement)
                and re.search(rf"\bsobra de {surplus}\b", statement)
            ):
                raise BusinessRuleError(
                    "USER_CONFIRMATION_REQUIRED",
                    f"Confirme {item.batches} lotes, {servings} porções e sobra de {surplus}.",
                )
        previous_item = (
            next((i for i in state.plan.items if i.recipe_id == item.recipe_id), None)
            if state.plan
            else None
        )
        items.append(
            PlanItem(
                **item.model_dump(mode="json"),
                plan_item_id=str(previous_item.plan_item_id) if previous_item else str(uuid4()),
                servings=servings,
                business_recipe_version=recipe.business_version,
                surplus_servings=None
                if servings is None
                else servings - (item.requested_servings or servings),
            )
        )
    statement = request.evidence.statement.casefold().strip()
    if not statement.startswith("confirmo ") or re.search(r"\b(não|talvez|se)\b|\?", statement):
        raise BusinessRuleError(
            "USER_CONFIRMATION_REQUIRED", "Confirme explicitamente a produção descrita no resumo."
        )
    _invalidate_acceptances(state)
    state.plan = ProductionPlan(
        id=str(state.plan.id) if state.plan else str(uuid4()),
        version=state.plan.version + 1 if state.plan else 1,
        items=items,
        inventory_snapshot_id=str(state.inventory_snapshot_id),
        evidence=request.evidence,
    )
    return {"plan": state.plan.model_dump(mode="json")}


def _invalidate_acceptances(state: WorkspaceState) -> None:
    for acceptance in state.acceptances:
        if acceptance.id not in state.invalidated_acceptance_ids:
            state.invalidated_acceptance_ids.append(acceptance.id)


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
