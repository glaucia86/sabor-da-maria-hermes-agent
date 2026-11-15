"""Contratos de produção e decisões humanas; sem transporte, banco ou rede."""

import re
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, field_validator, model_validator

from dona_maria.candidates import (
    CandidateModel,
    Category,
    ShortText,
    UUIDText,
)
from dona_maria.inventory import normalize_name
from dona_maria.provenance import UserEvidence as UserEvidence


class CommandMeta(CandidateModel):
    workspace_id: UUIDText
    operation_id: UUIDText
    expected_revision: Annotated[StrictInt, Field(ge=0)]


class FeedbackRequest(CommandMeta):
    recipe_id: UUIDText
    feedback: Literal["INTERESTED", "REJECTED", "UNDECIDED"]
    evidence: UserEvidence


class RecipeFeedback(CandidateModel):
    recipe_id: UUIDText
    feedback: Literal["INTERESTED", "REJECTED", "UNDECIDED"]
    evidence: UserEvidence


class PreferenceInput(CandidateModel):
    category: Literal["INGREDIENT", "DISH_STYLE", "PREPARATION", "OTHER"]
    term: ShortText
    value: Literal["LIKE", "AVOID"]
    evidence: UserEvidence
    replaces_preference_id: UUIDText | None = None

    @field_validator("term")
    @classmethod
    def nonblank_term(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Preferência exige termo com conteúdo.")
        return value


class PreferencesRequest(CommandMeta):
    preferences: Annotated[list[PreferenceInput], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_terms(self):
        keys = [(p.category, normalize_name(p.term)) for p in self.preferences]
        if len(keys) != len(set(keys)):
            raise ValueError("Preferência duplicada no comando.")
        return self


class UserPreference(PreferenceInput):
    id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    recorded_at: AwareDatetime


class PlanItemInput(CandidateModel):
    recipe_id: UUIDText
    recipe_version: Annotated[StrictInt, Field(gt=0)]
    position: Annotated[StrictInt, Field(ge=0)]
    batches: Annotated[StrictInt, Field(gt=0)]
    requested_servings: Annotated[StrictInt, Field(gt=0)] | None = None


class QuoteSelection(CandidateModel):
    ingredient_id: UUIDText
    quote_id: UUIDText
    quote_version: Annotated[StrictInt, Field(gt=0)]


class PlanRequest(CommandMeta):
    items: list[PlanItemInput]
    quote_selections: list[QuoteSelection] = []
    evidence: UserEvidence

    @model_validator(mode="after")
    def unique_items(self):
        for values in (
            [item.recipe_id for item in self.items],
            [item.position for item in self.items],
            [selection.ingredient_id for selection in self.quote_selections],
        ):
            if len(values) != len(set(values)):
                raise ValueError("Receitas e posições do plano devem ser únicas.")
        return self


class PlanItem(PlanItemInput):
    plan_item_id: UUIDText
    servings: Annotated[StrictInt, Field(gt=0)] | None
    surplus_servings: Annotated[StrictInt, Field(ge=0)] | None
    business_recipe_version: Annotated[StrictInt, Field(gt=0)]


class ProductionPlan(CandidateModel):
    id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    items: list[PlanItem]
    inventory_snapshot_id: UUIDText
    evidence: UserEvidence
    quote_selections: list[QuoteSelection] = []


class KitchenFactInput(CandidateModel):
    category: Category
    key: ShortText
    value: StrictBool | ShortText
    unit: ShortText | None = None
    context: ShortText | None = None
    evidence: UserEvidence
    replaces_fact_id: UUIDText | None = None


class KitchenFactsRequest(CommandMeta):
    facts: Annotated[list[KitchenFactInput], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [(fact.category, fact.key) for fact in self.facts]
        if len(keys) != len(set(keys)):
            raise ValueError("Chave de fato duplicada.")
        return self


class KitchenFact(KitchenFactInput):
    id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    recorded_at: AwareDatetime


class FeasibilityRequest(CandidateModel):
    workspace_id: UUIDText
    recipe_id: UUIDText
    plan_item_id: UUIDText


class AcceptanceRequest(CommandMeta):
    recipe_id: UUIDText
    plan_item_id: UUIDText
    evaluation_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    evidence: UserEvidence


class RecipeAcceptance(CandidateModel):
    id: UUIDText
    recipe_id: UUIDText
    recipe_version: Annotated[StrictInt, Field(gt=0)]
    plan_item_id: UUIDText
    batches: Annotated[StrictInt, Field(gt=0)]
    evaluation_id: str
    fingerprint: str
    evidence: UserEvidence
    accepted_at: AwareDatetime


def explicit_acceptance(evidence: UserEvidence) -> bool:
    # Conservador: frases ambíguas pedem esclarecimento; não pretende autenticar a fala.
    statement = " ".join(evidence.statement.casefold().strip().rstrip(".! ").split())
    return (
        re.fullmatch(
            r"(?:sim,? )?aceito(?: (?:este|esse|o) prato| (?:esta|essa|a) receita)?"
            r"(?: conforme (?:este|esse|o) resumo)?",
            statement,
        )
        is not None
    )
