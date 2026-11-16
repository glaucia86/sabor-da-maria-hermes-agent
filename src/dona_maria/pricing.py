"""Snapshots financeiros S03: Decimal técnico separado da apresentação didática."""

import re
from datetime import datetime
from decimal import (
    ROUND_CEILING,
    ROUND_HALF_UP,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AwareDatetime, Field, field_validator, model_validator

from dona_maria.candidates import CandidateModel, UUIDText
from dona_maria.inventory import InventorySnapshot
from dona_maria.production import CommandMeta, PlanItem, RecipeAcceptance, UserEvidence

CENT = Decimal("0.01")
NET = Decimal("0.90")
FINANCIAL_CONTEXT = Context(prec=34, traps=[DivisionByZero, InvalidOperation, Overflow])


class CalculatePricingRequest(CommandMeta):
    recipe_id: UUIDText
    acceptance_id: UUIDText


class SaveMenuDecisionRequest(CalculatePricingRequest):
    calculation_id: UUIDText
    scenario_id: Literal["M10", "M20", "M30"] | None = None
    custom_price: Annotated[str, Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,2})?$")] | None = None
    evidence: UserEvidence

    @field_validator("custom_price")
    @classmethod
    def positive_money(cls, value):
        if value is not None:
            if Decimal(value) <= 0:
                raise ValueError("Preço deve ser positivo.")
            return format(Decimal(value), ".2f")
        return value

    @model_validator(mode="after")
    def exactly_one_choice(self):
        if (self.scenario_id is None) == (self.custom_price is None):
            raise ValueError("Informe exatamente cenário ou preço personalizado.")
        return self


class MenuDecision(CandidateModel):
    id: UUIDText
    recipe_id: UUIDText
    acceptance_id: UUIDText
    calculation_id: UUIDText
    scenario_id: Literal["M10", "M20", "M30"] | None
    custom_price: str | None
    price: str
    evidence: UserEvidence
    fingerprint: str
    decided_at: AwareDatetime


def explicit_price_choice(request: SaveMenuDecisionRequest) -> bool:
    statement = " ".join(request.evidence.statement.casefold().strip().rstrip(".! ").split())
    if request.scenario_id:
        return (
            re.fullmatch(
                r"(?:escolho|confirmo)(?: o)?(?: cenário)? " + request.scenario_id.casefold(),
                statement,
            )
            is not None
        )
    match = re.fullmatch(
        r"(?:escolho|confirmo)(?: o)?(?: preço)?(?: de| por)?(?: r\$)? "
        r"([0-9]{1,12}(?:[.,][0-9]{1,2})?)",
        statement,
    )
    return match is not None and Decimal(match[1].replace(",", ".")) == Decimal(
        request.custom_price
    )


class CostAllocation(CandidateModel):
    ingredient_id: UUIDText
    plan_item_id: UUIDText
    recipe_id: UUIDText
    origin: Literal["INVENTORY", "QUOTE", "REPORTED_ACQUISITION"] = "INVENTORY"
    source_id: UUIDText
    source_version: str
    quantity: str
    unit: Literal["g", "ml", "un"]
    acquisition_total: str
    purchase_quantity_base: str
    unit_cost: str
    subtotal: str
    source: dict


class PricingScenario(CandidateModel):
    scenario_id: Literal["MINIMUM", "M10", "M20", "M30", "CUSTOM"]
    target_margin: str
    price: str
    fee_theoretical: str
    receipt_theoretical: str
    result_theoretical: str
    effective_margin: str
    display: dict[str, str]


class PricingCalculation(CandidateModel):
    id: UUIDText
    recipe_id: UUIDText
    acceptance_id: UUIDText
    fingerprint: str
    pricing_policy_version: Literal["1.0"]
    allocations: list[CostAllocation]
    batches: int
    servings_per_batch: int
    planned_servings: int
    sale_unit_label: str
    cmv_production: str
    cmv_average_batch: str
    cmv_per_serving: str
    minimum: PricingScenario
    scenarios: list[PricingScenario]
    explanation: list[str]
    calculated_at: AwareDatetime

    @model_validator(mode="after")
    def consistent_financials(self):
        try:
            with localcontext(FINANCIAL_CONTEXT):
                if (
                    self.batches <= 0
                    or self.servings_per_batch <= 0
                    or self.planned_servings != self.batches * self.servings_per_batch
                ):
                    raise ValueError("Escala financeira inconsistente.")
                for allocation in self.allocations:
                    total, purchased, quantity = map(
                        Decimal,
                        (
                            allocation.acquisition_total,
                            allocation.purchase_quantity_base,
                            allocation.quantity,
                        ),
                    )
                    if min(total, purchased, quantity) <= 0 or not all(
                        n.is_finite() for n in (total, purchased, quantity)
                    ):
                        raise ValueError("Alocação exige custo, denominador e consumo positivos.")
                    if Decimal(allocation.unit_cost) != total / purchased or Decimal(
                        allocation.subtotal
                    ) != quantity * (total / purchased):
                        raise ValueError("Subtotal de aquisição inconsistente.")
                production = sum((Decimal(a.subtotal) for a in self.allocations), Decimal("0"))
                cost = production / self.planned_servings
                if (
                    Decimal(self.cmv_production),
                    Decimal(self.cmv_average_batch),
                    Decimal(self.cmv_per_serving),
                ) != (production, production / self.batches, cost):
                    raise ValueError("CMV derivado inconsistente.")
                expected = [
                    price_option(cost, minimum_price(cost, Decimal(m)), Decimal(m), identifier)
                    for identifier, m in (
                        ("MINIMUM", "0"),
                        ("M10", "0.10"),
                        ("M20", "0.20"),
                        ("M30", "0.30"),
                    )
                ]
                if [self.minimum, *self.scenarios] != expected:
                    raise ValueError("Piso/cenários inconsistentes com o CMV técnico.")
        except DecimalException as exc:
            raise ValueError("Snapshot financeiro inválido.") from exc
        return self


def price_option(
    cost: Decimal, price: Decimal, margin: Decimal, identifier: str
) -> PricingScenario:
    fee = Decimal("0.10") * price
    receipt = NET * price
    result = receipt - cost
    displayed_fee = fee.quantize(CENT, rounding=ROUND_HALF_UP)
    displayed_cost = cost.quantize(CENT, rounding=ROUND_HALF_UP)
    displayed_receipt = price - displayed_fee
    return PricingScenario(
        scenario_id=identifier,
        target_margin=format(margin, "f"),
        price=format(price, ".2f"),
        fee_theoretical=format(fee, "f"),
        receipt_theoretical=format(receipt, "f"),
        result_theoretical=format(result, "f"),
        effective_margin=format(result / price, "f"),
        display=dict(
            cmv=format(displayed_cost, ".2f"),
            fee=format(displayed_fee, ".2f"),
            receipt=format(displayed_receipt, ".2f"),
            result=format(displayed_receipt - displayed_cost, ".2f"),
        ),
    )


def minimum_price(cost: Decimal, margin: Decimal = Decimal("0")) -> Decimal:
    if not cost.is_finite() or cost <= 0 or not margin.is_finite() or not 0 <= margin < NET:
        raise InvalidOperation("Custo ou margem inválidos.")
    denominator = NET - margin
    price = (cost / denominator).quantize(CENT, rounding=ROUND_CEILING)
    if denominator * price < cost:
        price += CENT
    if price >= Decimal("1000000000000"):
        raise InvalidOperation("Preço calculado fora do intervalo monetário.")
    return price


def calculate_pricing(
    recipe,
    item: PlanItem,
    acceptance: RecipeAcceptance,
    snapshot: InventorySnapshot,
    policy: str,
    now: datetime,
    *,
    allocations: list[CostAllocation] | None = None,
) -> PricingCalculation:
    with localcontext(FINANCIAL_CONTEXT):
        supplied = allocations is not None
        allocations = list(allocations or [])
        for ingredient in [] if supplied else recipe.ingredients:
            stock = next(stock for stock in snapshot.items if stock.id == ingredient.ingredient_id)
            if (
                stock.acquisition_total is None
                or stock.purchase_quantity_base is None
                or stock.acquisition_total <= 0
                or stock.purchase_quantity_base <= 0
                or stock.purchase_source is None
            ):
                raise InvalidOperation(
                    "Custo e denominador de aquisição completos são obrigatórios."
                )
            quantity = Decimal(ingredient.quantity.value) * item.batches
            if ingredient.quantity.unit in {"kg", "L"}:
                quantity *= 1000
            unit_cost = stock.acquisition_total / stock.purchase_quantity_base
            allocations.append(
                CostAllocation(
                    ingredient_id=str(stock.id),
                    plan_item_id=str(item.plan_item_id),
                    recipe_id=str(recipe.id),
                    source_id=str(snapshot.id),
                    source_version=snapshot.import_policy_version,
                    quantity=format(quantity, "f"),
                    unit=stock.dimension,
                    acquisition_total=format(stock.acquisition_total, "f"),
                    purchase_quantity_base=format(stock.purchase_quantity_base, "f"),
                    unit_cost=format(unit_cost, "f"),
                    subtotal=format(quantity * unit_cost, "f"),
                    source=stock.purchase_source.model_dump(mode="json"),
                )
            )
        production = sum((Decimal(a.subtotal) for a in allocations), Decimal("0"))
        servings = recipe.yield_per_batch.servings_per_batch * item.batches
        cost = production / servings
        calculation = PricingCalculation(
            id=str(uuid4()),
            recipe_id=str(recipe.id),
            acceptance_id=str(acceptance.id),
            fingerprint=acceptance.fingerprint,
            pricing_policy_version=policy,
            allocations=allocations,
            batches=item.batches,
            servings_per_batch=recipe.yield_per_batch.servings_per_batch,
            planned_servings=servings,
            sale_unit_label=recipe.yield_per_batch.sale_unit_label,
            cmv_production=format(production, "f"),
            cmv_average_batch=format(production / item.batches, "f"),
            cmv_per_serving=format(cost, "f"),
            minimum=price_option(cost, minimum_price(cost), Decimal("0"), "MINIMUM"),
            scenarios=[
                price_option(
                    cost, minimum_price(cost, Decimal(margin)), Decimal(margin), identifier
                )
                for identifier, margin in (("M10", "0.10"), ("M20", "0.20"), ("M30", "0.30"))
            ],
            explanation=[
                "CMV da produção soma quantidades consumidas × custos de aquisição; "
                "sobra não é consumo.",
                "CMV do lote é a média da produção planejada; CMV da porção usa "
                "o rendimento confirmado.",
                "Margens 10/20/30% sobre a venda após taxa e ingredientes são "
                "política didática, não markup.",
                "Exibição em centavos é aproximação didática, sem representar "
                "repasse efetivo do iFood.",
                "Resultado após taxa e ingredientes não é lucro líquido: não inclui "
                "gás, embalagem ou mão de obra sem dados.",
            ],
            calculated_at=now,
        )
        rounded_subtotals = sum(
            (Decimal(a.subtotal).quantize(CENT, rounding=ROUND_HALF_UP) for a in allocations),
            Decimal("0"),
        )
        if rounded_subtotals != production.quantize(CENT, rounding=ROUND_HALF_UP):
            calculation.explanation.append(
                "A soma dos subtotais arredondados difere do total arredondado; "
                "as parcelas técnicas foram preservadas."
            )
        if any(
            Decimal(s.result_theoretical) != Decimal(s.display["result"])
            for s in [calculation.minimum, *calculation.scenarios]
        ):
            calculation.explanation.append(
                "A exibição em centavos pode diferir do resultado técnico; "
                "piso e margem usam os valores técnicos."
            )
        return calculation


def allocate_plan_costs(candidates, plan, snapshot, quotes):
    """Aloca estoque primeiro; excedente usa a oferta selecionada, sem encargos no CMV."""
    allocations = []
    remaining = {stock.id: stock.stock_quantity_base for stock in snapshot.items}
    selected = {(s.ingredient_id): (s.quote_id, s.quote_version) for s in plan.quote_selections}
    offers = {(q.id, q.version): q for q in quotes}
    with localcontext(FINANCIAL_CONTEXT):
        for item in sorted(plan.items, key=lambda i: i.position):
            recipe = next(r for r in candidates if r.id == item.recipe_id)
            for ingredient in recipe.ingredients:
                stock = next(s for s in snapshot.items if s.id == ingredient.ingredient_id)
                quantity = Decimal(ingredient.quantity.value) * item.batches
                if ingredient.quantity.unit in {"kg", "L"}:
                    quantity *= 1000
                used = min(quantity, remaining[stock.id])
                remaining[stock.id] -= used
                for origin, amount in (("INVENTORY", used), ("QUOTE", quantity - used)):
                    if not amount:
                        continue
                    if origin == "INVENTORY":
                        total, base = stock.acquisition_total, stock.purchase_quantity_base
                        source_id, version = snapshot.id, snapshot.import_policy_version
                        source = (
                            stock.purchase_source.model_dump(mode="json")
                            if stock.purchase_source
                            else None
                        )
                        if source and source.get("kind") == "USER_PROVIDED":
                            origin = "REPORTED_ACQUISITION"
                            source_id = source["information_ref"]["entity_id"]
                            version = str(source["information_ref"]["version"])
                    else:
                        quote = offers[selected[stock.id]]
                        total, base = (
                            Decimal(quote.package_price),
                            Decimal(quote.package_quantity.value),
                        )
                        source_id, version = quote.id, str(quote.version)
                        source = quote.source.model_dump(mode="json")
                    if total is None or base is None or min(total, base) <= 0 or source is None:
                        raise InvalidOperation("Custo de aquisição da origem está incompleto.")
                    unit_cost = total / base
                    allocations.append(
                        CostAllocation(
                            ingredient_id=str(stock.id),
                            plan_item_id=str(item.plan_item_id),
                            recipe_id=str(recipe.id),
                            origin=origin,
                            source_id=str(source_id),
                            source_version=version,
                            quantity=format(amount, "f"),
                            unit=stock.dimension,
                            acquisition_total=format(total, "f"),
                            purchase_quantity_base=format(base, "f"),
                            unit_cost=format(unit_cost, "f"),
                            subtotal=format(amount * unit_cost, "f"),
                            source=source,
                        )
                    )
    return allocations
