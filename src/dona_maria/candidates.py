"""Contratos de candidatas pesquisadas, sem aceite ou decisões financeiras."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    StrictInt,
    field_validator,
    model_validator,
)


def require_uuid_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("UUID deve ser textual.")
    return value


UUIDText = Annotated[UUID, BeforeValidator(require_uuid_text)]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]
Note = Annotated[str, Field(min_length=1, max_length=4000)]
QuantityText = Annotated[str, Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,6})?$")]
Category = Literal["EQUIPMENT", "SKILL", "OPERATION"]


class CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WebSource(CandidateModel):
    kind: Literal["WEB"] = "WEB"
    url: HttpUrl
    title: ShortText
    excerpt: Note
    retrieved_at: AwareDatetime

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


class Quantity(CandidateModel):
    value: QuantityText
    unit: Literal["g", "kg", "ml", "L", "un"]

    @field_validator("value")
    @classmethod
    def positive_quantity(cls, value: str) -> str:
        number = Decimal(value)
        if number <= 0:
            raise ValueError("Consumo deve ser positivo.")
        return format(number.normalize(), "f")

    @model_validator(mode="after")
    def whole_units(self):
        if self.unit == "un" and Decimal(self.value) != Decimal(self.value).to_integral_value():
            raise ValueError("Contagem exige unidades inteiras.")
        return self


class OriginalMeasure(CandidateModel):
    raw_text: Note
    value: QuantityText | None = None
    unit_label: ShortText
    source: WebSource


class RecipeIngredientInput(CandidateModel):
    description: ShortText
    original_measure: OriginalMeasure
    ingredient_id: UUIDText | None = None
    quantity: Quantity | None = None
    quantity_gap: Note | None = None
    preparation_basis: Literal["RAW", "COOKED", "UNKNOWN"] = "UNKNOWN"
    source: WebSource

    @model_validator(mode="after")
    def explicit_quantity_gap(self):
        if self.quantity is None and self.quantity_gap is None:
            raise ValueError("Quantidade ausente exige lacuna explícita.")
        return self


class RecipeIngredient(RecipeIngredientInput):
    line_id: UUID = Field(default_factory=uuid4)


class RecipeYield(CandidateModel):
    servings_per_batch: Annotated[StrictInt, Field(gt=0)]
    sale_unit_label: ShortText
    source: WebSource


class CriticalRequirementInput(CandidateModel):
    category: Category
    key: ShortText
    condition: Literal[
        "PRESENT", "SKILL_KNOWN", "MIN_CAPACITY", "MIN_AVAILABLE_TIME", "EXPLICIT_CONDITION"
    ]
    value: str | bool | None = None
    unit: ShortText | None = None
    reason: Note
    source: WebSource


class CriticalRequirement(CriticalRequirementInput):
    id: UUID = Field(default_factory=uuid4)


class CategoryReview(CandidateModel):
    category: Category
    requirement_keys: list[ShortText]
    method_version: Annotated[StrictInt, Field(gt=0)]
    not_applicable_reason: Note | None = None
    source: WebSource

    @model_validator(mode="after")
    def explain_empty_category(self):
        if not self.requirement_keys and not self.not_applicable_reason:
            raise ValueError("Categoria sem requisitos exige justificativa fundamentada no método.")
        return self


class CandidateInput(CandidateModel):
    title: ShortText
    sources: list[WebSource] = []
    ingredients: list[RecipeIngredientInput]
    method: Annotated[str, Field(min_length=1, max_length=12000)] | None = None
    method_source: WebSource | None = None
    method_gap: Note | None = None
    yield_per_batch: RecipeYield | None = None
    yield_gap: Note | None = None
    operational_context: Note | None = None
    context_source: WebSource | None = None
    context_gap: Note | None = None
    requirements: list[CriticalRequirementInput] = []
    category_reviews: list[CategoryReview] = []
    declared_gaps: list[Note] = []

    @model_validator(mode="after")
    def validate_provenance(self):
        if self.method and not self.method_source:
            raise ValueError("Método exige fonte.")
        if not self.method and not self.method_gap:
            raise ValueError("Método ausente exige lacuna explícita.")
        if not self.yield_per_batch and not self.yield_gap:
            raise ValueError("Rendimento ausente exige lacuna explícita.")
        if self.operational_context and not self.context_source:
            raise ValueError("Contexto exige fonte.")
        if not self.operational_context and not self.context_gap:
            raise ValueError("Contexto ausente exige lacuna explícita.")
        urls = {str(source.url) for source in self.sources}
        references = [
            self.method_source,
            self.context_source,
            self.yield_per_batch.source if self.yield_per_batch else None,
        ]
        references += [
            source
            for item in self.ingredients
            for source in (item.source, item.original_measure.source)
        ]
        references += [item.source for item in [*self.requirements, *self.category_reviews]]
        if urls and any(str(source.url) not in urls for source in references if source):
            raise ValueError("Origem do dado não pertence às fontes da candidata.")
        categories = [review.category for review in self.category_reviews]
        if len(categories) != len(set(categories)):
            raise ValueError("Revisão de categoria duplicada.")
        keys = [(item.category, item.key) for item in self.requirements]
        if len(keys) != len(set(keys)):
            raise ValueError("Requisito duplicado.")
        for review in self.category_reviews:
            if set(review.requirement_keys) != {
                item.key for item in self.requirements if item.category == review.category
            }:
                raise ValueError("Revisão não corresponde aos requisitos da categoria.")
        return self


class RecipeCandidate(CandidateInput):
    ingredients: list[RecipeIngredient]
    requirements: list[CriticalRequirement] = []
    id: UUID
    version: Annotated[StrictInt, Field(gt=0)]
    business_version: Annotated[StrictInt, Field(gt=0)] = 1
    recorded_at: AwareDatetime

    def public(self) -> dict:
        data = self.model_dump(mode="json")
        gaps = list(self.declared_gaps)
        for value, gap in [
            (self.method, self.method_gap),
            (self.yield_per_batch, self.yield_gap),
            (self.operational_context, self.context_gap),
        ]:
            if value is None and gap:
                gaps.append(gap)
        if not self.ingredients:
            gaps.append("Ingredientes não informados.")
        for ingredient in self.ingredients:
            if ingredient.quantity is None:
                gaps.append(ingredient.quantity_gap)
            if ingredient.ingredient_id is None:
                gaps.append(f"Identidade pendente: {ingredient.description}.")
        category_status = {}
        for category in ("EQUIPMENT", "SKILL", "OPERATION"):
            reviewed = any(
                review.category == category and review.method_version == self.version
                for review in self.category_reviews
            )
            category_status[category] = "REVIEWED" if reviewed else "UNREVIEWED"
            if not reviewed:
                gaps.append(f"Categoria não revisada: {category}.")
        data.update(
            complete=not gaps, gaps=gaps, interest="UNDECIDED", category_status=category_status
        )
        for requirement in data["requirements"]:
            requirement["status"] = "UNKNOWN"
        return data

    def business_content(self) -> dict:
        payload = self.model_dump(mode="json")
        data = {name: payload[name] for name in CandidateInput.model_fields}
        data.pop("title")
        for ingredient in data["ingredients"]:
            ingredient.pop("line_id", None)
        for requirement in data["requirements"]:
            requirement.pop("id", None)
        for review in data["category_reviews"]:
            # Só uma revisão efetivamente atual pode preservar a base anterior.
            review["method_version"] = (
                "CURRENT" if review["method_version"] == self.version else "STALE"
            )
        return data


class RegisterCandidateRequest(CandidateModel):
    workspace_id: UUIDText
    operation_id: UUIDText
    expected_revision: Annotated[StrictInt, Field(ge=0)]
    recipe_id: UUIDText | None = None
    expected_recipe_version: Annotated[StrictInt, Field(gt=0)] | None = None
    candidate: CandidateInput

    @model_validator(mode="after")
    def revision_pair(self):
        if (self.recipe_id is None) != (self.expected_recipe_version is None):
            raise ValueError("Revisão exige ID e versão da receita juntos.")
        return self
