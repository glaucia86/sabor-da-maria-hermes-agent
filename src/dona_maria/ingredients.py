"""Overlays de medida com escopo explícito; nunca alteram a fotografia recebida."""

from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from dona_maria.candidates import (
    CandidateModel,
    Note,
    Quantity,
    QuantityText,
    RecipeCandidate,
    ShortText,
    UUIDText,
    WebSource,
)
from dona_maria.inventory import InventoryItem, InventorySnapshot, normalize_name
from dona_maria.production import CommandMeta, UserEvidence
from dona_maria.provenance import DerivedProvenance, InformationRef, PrimaryProvenance

_CONVERSION_CONTEXT = Context(prec=34, traps=[DivisionByZero, InvalidOperation, Overflow])
_STANDARD_UNITS = {
    "g": ("g", Decimal("1")),
    "kg": ("g", Decimal("1000")),
    "ml": ("ml", Decimal("1")),
    "L": ("ml", Decimal("1000")),
    "un": ("un", Decimal("1")),
}


def materialize_recipe_quantities(recipe):
    """Confere equivalência métrica e atribui origem apenas à saída calculada."""
    for index, line in enumerate(recipe.ingredients):
        if line.quantity is None:
            continue
        measure = line.original_measure
        original = _STANDARD_UNITS.get(measure.unit_label)
        target = _STANDARD_UNITS[line.quantity.unit]
        if measure.value is None or original is None or original[0] != target[0]:
            raise ValueError("Medida exige conversão contextual confirmada; mantenha a lacuna.")
        with localcontext(_CONVERSION_CONTEXT):
            if Decimal(measure.value) * original[1] != Decimal(line.quantity.value) * target[1]:
                raise ValueError("Quantidade diverge da medida original atestada.")
        line.quantity_source = DerivedProvenance(
            rule="STANDARD_UNIT",
            rule_version="1.0",
            inputs=[
                InformationRef(
                    entity="RECIPE",
                    entity_id=str(recipe.id),
                    version=recipe.version,
                    field=f"ingredients/{index}/original_measure/source",
                )
            ],
        )


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
    source: PrimaryProvenance | None = Field(default=None, exclude_if=lambda value: value is None)
    id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    recorded_at: AwareDatetime

    def key(self):
        return self.ingredient_id, self.scope, self.recipe_id, self.line_id


class NewIngredient(CandidateModel):
    name: ShortText
    dimension: Literal["g", "ml", "un"]

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("Nome do complemento obrigatório.")
        return value


class ComplementIngredient(CandidateModel):
    id: UUIDText
    name_original: ShortText
    name_normalized: ShortText
    dimension: Literal["g", "ml", "un"]
    origin: Literal["COMPLEMENT"] = "COMPLEMENT"
    stock_quantity_base: Literal["0"] = "0"
    availability_basis: Literal["ABSENT_FROM_SNAPSHOT"] = "ABSENT_FROM_SNAPSHOT"
    availability_note: Note = (
        "Ausente da fotografia; pergunte sobre estoque adicional antes de comprar."
    )
    acquisition_total: None = None
    evidence: UserEvidence | WebSource


def with_complements(snapshot: InventorySnapshot, ingredients) -> InventorySnapshot:
    """Disponibilidade registrada por ausência; nunca altera o snapshot original."""
    result = snapshot.model_copy(deep=True)
    result.items.extend(
        InventoryItem(
            id=ingredient.id,
            name_original=ingredient.name_original,
            name_normalized=ingredient.name_normalized,
            stock_quantity_original=None,
            purchase_quantity_original=None,
            stock_unit_original=None,
            purchase_unit_original=None,
            stock_quantity_base=Decimal("0"),
            purchase_quantity_base=None,
            dimension=ingredient.dimension,
            acquisition_total=None,
            unit_cost=None,
            issues=[],
            stock_source=None,
            purchase_source=None,
        )
        for ingredient in ingredients
    )
    return result


class ResolveIngredientRequest(CommandMeta):
    recipe_id: UUIDText
    recipe_version: Annotated[StrictInt, Field(gt=0)]
    line_id: UUIDText
    existing_ingredient_id: UUIDText | None = None
    new_ingredient: NewIngredient | None = None
    evidence: UserEvidence | WebSource

    @model_validator(mode="after")
    def exactly_one_identity(self):
        if (self.existing_ingredient_id is None) == (self.new_ingredient is None):
            raise ValueError("Informe exatamente uma identidade existente ou novo complemento.")
        if self.existing_ingredient_id is not None and not isinstance(self.evidence, UserEvidence):
            raise ValueError("Equivalência exige evidência humana.")
        return self


class IngredientResolution(CandidateModel):
    recipe_id: UUIDText
    line_id: UUIDText
    ingredient_id: UUIDText
    alias: ShortText
    evidence: UserEvidence | WebSource
    recorded_at: AwareDatetime


def current_conversions(conversions):
    latest = {}
    for conversion in conversions:
        latest[conversion.key()] = conversion
    return list(latest.values())


def recipe_conversion_applies(conversion: ConversionRequest, recipe: RecipeCandidate) -> bool:
    """Linhas preservadas ligam a conversão a revisões sem mudança material."""
    return (
        recipe.id == conversion.recipe_id
        and conversion.recipe_version is not None
        and recipe.version >= conversion.recipe_version
        and any(
            line.line_id == conversion.line_id and line.ingredient_id == conversion.ingredient_id
            for line in recipe.ingredients
        )
    )


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
        if recipe.version != conversion.recipe_version and not recipe_conversion_applies(
            conversion, recipe
        ):
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
    identifiers = {i.id for i in snapshot.items}
    names = {i.name_normalized for i in snapshot.items}
    for ingredient in state.complement_ingredients:
        if (
            ingredient.id in identifiers
            or ingredient.name_normalized in names
            or ingredient.name_normalized != normalize_name(ingredient.name_original)
            or not ingredient.name_normalized
        ):
            raise ValueError("Identidade complementar inválida ou em colisão.")
        identifiers.add(ingredient.id)
        names.add(ingredient.name_normalized)
    stocks = {i.id: i for i in with_complements(snapshot, state.complement_ingredients).items}
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
                if recipe is None or not recipe_conversion_applies(conversion, recipe):
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
                if recipe.provenance_version == "2.0":
                    line.quantity_source = DerivedProvenance(
                        rule="CONTEXTUAL_CONVERSION",
                        rule_version="1.0",
                        inputs=[
                            InformationRef(
                                entity="RECIPE",
                                entity_id=str(recipe.id),
                                version=recipe.version,
                                field=f"ingredients/{recipe.ingredients.index(line)}/original_measure/source",
                            ),
                            InformationRef(
                                entity="CONVERSION",
                                entity_id=str(conversion.id),
                                version=conversion.version,
                                field="conversion",
                            ),
                        ],
                    )
                line.quantity_gap = None
                line.preparation_basis = "RAW"
    return recipes, effective
