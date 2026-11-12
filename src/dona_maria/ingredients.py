"""Overlays de medida com escopo explícito; nunca alteram a fotografia recebida."""

from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from dona_maria.candidates import (
    CandidateModel,
    Quantity,
    QuantityText,
    RecipeCandidate,
    ShortText,
    UUIDText,
    WebSource,
)
from dona_maria.inventory import InventoryItem
from dona_maria.production import CommandMeta, UserEvidence

_CONVERSION_CONTEXT = Context(prec=34, traps=[DivisionByZero, InvalidOperation, Overflow])
_STANDARD_UNITS = {
    "g": ("g", Decimal("1")),
    "kg": ("g", Decimal("1000")),
    "ml": ("ml", Decimal("1")),
    "L": ("ml", Decimal("1000")),
    "un": ("un", Decimal("1")),
}


class ConversionRequest(CommandMeta):
    ingredient_id: UUIDText
    from_unit: ShortText
    to_unit: Literal["g", "ml", "un"]
    factor: QuantityText
    context: ShortText
    scope: Literal["RECIPE_MEASURE", "HISTORICAL_PACKAGE"]
    evidence: UserEvidence | WebSource
    recipe_id: UUIDText | None = None
    recipe_version: Annotated[StrictInt, Field(gt=0)] | None = None
    line_id: UUIDText | None = None
    replaces_conversion_id: UUIDText | None = None
    from_preparation_basis: Literal["RAW", "COOKED"] = "RAW"

    @field_validator("factor")
    @classmethod
    def positive_factor(cls, value):
        if Decimal(value) <= 0:
            raise ValueError("Fator deve ser positivo.")
        with localcontext(_CONVERSION_CONTEXT):
            return format(Decimal(value).normalize(), "f")

    @field_validator("context", "from_unit")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Contexto/unidade obrigatório.")
        return value

    @model_validator(mode="after")
    def explicit_scope(self):
        target = (self.recipe_id, self.recipe_version, self.line_id)
        if self.scope == "HISTORICAL_PACKAGE":
            if (
                any(v is not None for v in target)
                or not isinstance(self.evidence, UserEvidence)
                or self.from_preparation_basis != "RAW"
            ):
                raise ValueError("Embalagem histórica exige fala humana e escopo do snapshot.")
        elif any(v is None for v in target):
            raise ValueError("Medida de receita exige receita/versão/linha.")
        return self


class IngredientConversion(ConversionRequest):
    id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    recorded_at: AwareDatetime

    def key(self):
        return self.ingredient_id, self.scope, self.recipe_id, self.line_id


class ResolveIngredientRequest(CommandMeta):
    recipe_id: UUIDText
    recipe_version: Annotated[StrictInt, Field(gt=0)]
    line_id: UUIDText
    existing_ingredient_id: UUIDText
    evidence: UserEvidence


class IngredientResolution(CandidateModel):
    recipe_id: UUIDText
    line_id: UUIDText
    ingredient_id: UUIDText
    alias: ShortText
    evidence: UserEvidence
    recorded_at: AwareDatetime


def current_conversions(conversions):
    latest = {}
    for conversion in conversions:
        latest[conversion.key()] = conversion
    return list(latest.values())


def validate_conversion_measure(
    conversion: ConversionRequest, stock: InventoryItem, recipe: RecipeCandidate | None = None
) -> None:
    standard = _STANDARD_UNITS.get(conversion.from_unit)
    factor = Decimal(conversion.factor)
    if (
        standard
        and standard[0] == conversion.to_unit
        and conversion.from_preparation_basis == "RAW"
        and factor != standard[1]
    ):
        raise ValueError("Equivalência métrica não pode ser redefinida.")
    if conversion.scope == "HISTORICAL_PACKAGE":
        if (
            stock.dimension != conversion.from_unit
            or stock.stock_quantity_base is None
            or stock.purchase_quantity_base is None
            or stock.purchase_quantity_base <= 0
            or stock.acquisition_total is None
            or stock.issues
        ):
            raise ValueError("Base histórica incompleta/incompatível.")
        quantities = (stock.stock_quantity_base, stock.purchase_quantity_base)
    else:
        if recipe is None:
            raise ValueError("Receita da conversão ausente.")
        if recipe.version != conversion.recipe_version:
            return  # A medida original de uma versão histórica não está mais disponível.
        line = next(
            (line for line in recipe.ingredients if line.line_id == conversion.line_id), None
        )
        if (
            line is None
            or line.ingredient_id != conversion.ingredient_id
            or line.original_measure.value is None
            or line.original_measure.unit_label != conversion.from_unit
            or line.preparation_basis != conversion.from_preparation_basis
        ):
            raise ValueError("Medida/base ainda sem quantidade sustentada.")
        quantities = (Decimal(line.original_measure.value),)
    with localcontext(_CONVERSION_CONTEXT) as context:
        for quantity in quantities:
            # Verificar contagens antes que o arredondamento técnico oculte uma fração.
            context.prec = max(34, len(quantity.as_tuple().digits) + len(factor.as_tuple().digits))
            amount = quantity * factor
            if (
                amount < 0
                or (conversion.scope == "RECIPE_MEASURE" and amount == 0)
                or (conversion.to_unit == "un" and amount != amount.to_integral_value())
            ):
                raise ValueError("Consumo deve ser positivo e contagem inteira.")


def validate_overlay_references(state, snapshot):
    stocks = {i.id: i for i in snapshot.items}
    recipes = {r.id: r for r in state.candidates}
    previous = {}
    identifiers = set()
    for conversion in state.ingredient_conversions:
        stock = stocks.get(conversion.ingredient_id)
        prior = previous.get(conversion.key())
        if (
            stock is None
            or conversion.workspace_id != state.id
            or conversion.id in identifiers
            or conversion.replaces_conversion_id != (prior.id if prior else None)
            or conversion.version != (prior.version + 1 if prior else 1)
        ):
            raise ValueError("Histórico/referência de conversão inválido.")
        recipe = recipes.get(conversion.recipe_id)
        if conversion.scope == "RECIPE_MEASURE":
            if recipe is None or conversion.recipe_version > recipe.version:
                raise ValueError("Receita da conversão inválida.")
        validate_conversion_measure(conversion, stock, recipe)
        identifiers.add(conversion.id)
        previous[conversion.key()] = conversion
    if any(
        r.ingredient_id not in stocks or r.recipe_id not in recipes
        for r in state.ingredient_resolutions
    ):
        raise ValueError("Resolução fora do workspace.")


def apply_overlays(candidates, snapshot, conversions):
    recipes = [recipe.model_copy(deep=True) for recipe in candidates]
    effective = snapshot.model_copy(deep=True)
    with localcontext(_CONVERSION_CONTEXT):
        for conversion in current_conversions(conversions):
            if conversion.scope == "HISTORICAL_PACKAGE":
                stock = next(i for i in effective.items if i.id == conversion.ingredient_id)
                factor = Decimal(conversion.factor)
                stock.stock_quantity_base *= factor
                stock.purchase_quantity_base *= factor
                stock.unit_cost = stock.acquisition_total / stock.purchase_quantity_base
                stock.dimension = conversion.to_unit
            else:
                recipe = next((r for r in recipes if r.id == conversion.recipe_id), None)
                if recipe is None or recipe.version != conversion.recipe_version:
                    continue
                line = next(
                    (i for i in recipe.ingredients if i.line_id == conversion.line_id), None
                )
                if line is None or line.ingredient_id != conversion.ingredient_id:
                    continue
                measure = line.original_measure
                if (
                    measure.value is None
                    or measure.unit_label != conversion.from_unit
                    or line.preparation_basis != conversion.from_preparation_basis
                ):
                    continue
                amount = Decimal(measure.value) * Decimal(conversion.factor)
                # Resultado técnico não se limita às seis casas permitidas na entrada.
                line.quantity = Quantity.model_construct(
                    value=format(amount, "f"), unit=conversion.to_unit
                )
                line.quantity_gap = None
                line.preparation_basis = "RAW"
    return recipes, effective
