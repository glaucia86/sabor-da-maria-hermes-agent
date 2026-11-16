"""Aquisição reportada: overlay auditado, sem compra ou baixa física."""

from decimal import Decimal, localcontext
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from dona_maria.candidates import Quantity, QuantityText
from dona_maria.inventory import InventorySnapshot
from dona_maria.pricing import FINANCIAL_CONTEXT
from dona_maria.production import CommandMeta, UserEvidence
from dona_maria.provenance import InformationRef, Note, ShortText, UserProvidedSource, UUIDText
from dona_maria.quotes import MoneyText


class AvailableQuantity(Quantity):
    value: QuantityText

    @field_validator("value")
    @classmethod
    def positive_quantity(cls, value):
        return format(Decimal(value), "f")


class AcquisitionRequest(CommandMeta):
    ingredient_id: UUIDText
    available_quantity: AvailableQuantity
    acquired_quantity: Quantity | None = None
    acquisition_total: MoneyText | None = None
    acquisition_gap: Note | None = None
    basis: Literal["HISTORICAL_ACQUISITION"]
    context: Note
    replaces_acquisition_id: UUIDText | None = None
    evidence: UserEvidence

    @model_validator(mode="after")
    def supported_cost(self):
        if self.acquisition_total is not None and Decimal(self.acquisition_total) <= 0:
            raise ValueError("Aquisição conhecida exige valor positivo.")
        if (
            self.acquired_quantity is None or self.acquisition_total is None
        ) and not self.acquisition_gap:
            raise ValueError("Aquisição incompleta exige lacuna explícita.")
        if (
            self.acquired_quantity
            and base_quantity(self.acquired_quantity)[0]
            != base_quantity(self.available_quantity)[0]
        ):
            raise ValueError("Aquisição e disponibilidade exigem dimensões compatíveis.")
        if not self.context.strip():
            raise ValueError("Aquisição exige contexto da origem.")
        return self


class ReportedAcquisition(AcquisitionRequest):
    id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    snapshot_id: UUIDText
    recorded_at: AwareDatetime
    sources: dict[str, UserProvidedSource]


class ResourceQuantity(Quantity):
    unit: ShortText


class OperationalResourceRequest(CommandMeta):
    recipe_id: UUIDText
    recipe_version: Annotated[StrictInt, Field(gt=0)]
    resource_name: ShortText
    purpose: Note
    classification: Literal["EXTERNAL_OPERATIONAL_RESOURCE"]
    quantity: ResourceQuantity | None = None
    quantity_gap: Note | None = None
    cost: MoneyText | None = None
    cost_gap: Note | None = None
    context: Note
    replaces_resource_id: UUIDText | None = None
    evidence: UserEvidence

    @model_validator(mode="after")
    def explicit_gaps(self):
        if self.quantity is None and not self.quantity_gap:
            raise ValueError("Quantidade externa ausente exige lacuna explícita.")
        if self.cost is None and not self.cost_gap:
            raise ValueError("Custo externo ausente exige lacuna explícita.")
        if any(not value.strip() for value in (self.resource_name, self.purpose, self.context)):
            raise ValueError("Recurso externo exige nome, finalidade e contexto explícitos.")
        return self


class OperationalResource(OperationalResourceRequest):
    id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    business_recipe_version: Annotated[StrictInt, Field(gt=0)]
    recorded_at: AwareDatetime
    sources: dict[str, UserProvidedSource]


def current_resources(resources):
    replaced = {r.replaces_resource_id for r in resources}
    return [r for r in resources if r.id not in replaced]


def record_operational_resource(state, request, now):
    from dona_maria.inventory import normalize_name
    from dona_maria.planning import BusinessRuleError, _invalidate_acceptances

    recipe = next((r for r in state.candidates if r.id == request.recipe_id), None)
    if recipe is None:
        raise BusinessRuleError("NOT_FOUND", "Receita não pertence ao contexto.")
    if recipe.version != request.recipe_version:
        raise BusinessRuleError("STALE_REVISION", "Reconfirme a finalidade na receita vigente.")
    previous = next(
        (
            r
            for r in current_resources(state.operational_resources)
            if r.id == request.replaces_resource_id
            or request.replaces_resource_id is None
            and r.recipe_id == recipe.id
            and normalize_name(r.resource_name) == normalize_name(request.resource_name)
            and normalize_name(r.purpose) == normalize_name(request.purpose)
        ),
        None,
    )
    if request.replaces_resource_id != (previous.id if previous else None) or (
        previous and previous.recipe_id != recipe.id
    ):
        raise BusinessRuleError("STALE_REVISION", "Informe o recurso vigente a substituir.")
    identifier = str(uuid4())
    version = previous.version + 1 if previous else 1
    sources = {
        field: UserProvidedSource(
            kind="USER_PROVIDED",
            evidence=request.evidence,
            local_event_id=request.evidence.turn_ref.removeprefix("local:"),
            information_ref=InformationRef(
                entity="OPERATIONAL_RESOURCE",
                entity_id=identifier,
                version=version,
                field=field,
            ),
        )
        for field in (
            "resource_name",
            "purpose",
            "quantity",
            "quantity_gap",
            "cost",
            "cost_gap",
            "context",
            "classification",
        )
    }
    resource = OperationalResource(
        **request.model_dump(mode="json"),
        id=identifier,
        version=version,
        business_recipe_version=recipe.business_version,
        recorded_at=now,
        sources=sources,
    )
    state.operational_resources.append(resource)
    state.financial_data_version = "1.0"
    _invalidate_acceptances(state)
    return {"operational_resource": resource.model_dump(mode="json")}


def base_quantity(quantity):
    unit = {"kg": "g", "L": "ml"}.get(quantity.unit, quantity.unit)
    return unit, Decimal(quantity.value) * (1000 if quantity.unit in {"kg", "L"} else 1)


def current_acquisitions(acquisitions):
    return {a.ingredient_id: a for a in acquisitions}.values()


def apply_acquisitions(snapshot: InventorySnapshot, acquisitions):
    if not acquisitions:
        return snapshot
    effective = snapshot.model_copy(deep=True)
    with localcontext(FINANCIAL_CONTEXT):
        for acquisition in current_acquisitions(acquisitions):
            stock = next(i for i in effective.items if i.id == acquisition.ingredient_id)
            stock.dimension, stock.stock_quantity_base = base_quantity(
                acquisition.available_quantity
            )
            stock.stock_source = acquisition.sources["available_quantity"]
            stock.acquisition_total = (
                Decimal(acquisition.acquisition_total) if acquisition.acquisition_total else None
            )
            stock.purchase_quantity_base = (
                base_quantity(acquisition.acquired_quantity)[1]
                if acquisition.acquired_quantity
                else None
            )
            stock.purchase_source = acquisition.sources["acquisition_total"]
            stock.unit_cost = (
                stock.acquisition_total / stock.purchase_quantity_base
                if stock.acquisition_total is not None and stock.purchase_quantity_base
                else None
            )
    return effective


def record_acquisition(state, request, snapshot, now):
    # O repositório exige aprovação local antes de chegar a esta regra de domínio.
    from dona_maria.ingredients import apply_overlays, with_complements
    from dona_maria.planning import BusinessRuleError, _invalidate_acceptances

    _, effective = apply_overlays(state.candidates, snapshot, state.ingredient_conversions)
    stocks = {i.id: i for i in with_complements(effective, state.complement_ingredients).items}
    if request.ingredient_id not in stocks:
        raise BusinessRuleError("NOT_FOUND", "Ingrediente não pertence à fotografia local.")
    stock = stocks[request.ingredient_id]
    if stock.dimension and base_quantity(request.available_quantity)[0] != stock.dimension:
        raise BusinessRuleError("UNIT_CONVERSION_REQUIRED", "Unidade não corresponde ao estoque.")
    previous = next(
        (
            a
            for a in reversed(state.inventory_acquisitions)
            if a.ingredient_id == request.ingredient_id
        ),
        None,
    )
    if request.replaces_acquisition_id != (previous.id if previous else None):
        raise BusinessRuleError("STALE_REVISION", "Informe a aquisição vigente a substituir.")
    identifier = str(uuid4())
    version = previous.version + 1 if previous else 1
    fields = (
        "available_quantity",
        "acquired_quantity",
        "acquisition_total",
        "context",
        "acquisition_gap",
    )
    sources = {
        field: UserProvidedSource(
            kind="USER_PROVIDED",
            evidence=request.evidence,
            local_event_id=request.evidence.turn_ref.removeprefix("local:"),
            information_ref=InformationRef(
                entity="INVENTORY_ACQUISITION",
                entity_id=identifier,
                version=version,
                field=field,
            ),
        )
        for field in fields
    }
    acquisition = ReportedAcquisition(
        **request.model_dump(mode="json"),
        id=identifier,
        version=version,
        snapshot_id=str(snapshot.id),
        recorded_at=now,
        sources=sources,
    )
    state.inventory_acquisitions.append(acquisition)
    state.financial_data_version = "1.0"
    _invalidate_acceptances(state)
    return {"acquisition": acquisition.model_dump(mode="json")}


def validate_acquisitions(state, snapshot):
    ingredients = {i.id for i in [*snapshot.items, *state.complement_ingredients]}
    previous, identifiers = {}, set()
    for acquisition in state.inventory_acquisitions:
        prior = previous.get(acquisition.ingredient_id)
        if (
            acquisition.workspace_id != state.id
            or acquisition.snapshot_id != snapshot.id
            or acquisition.ingredient_id not in ingredients
            or acquisition.id in identifiers
            or acquisition.version != (prior.version + 1 if prior else 1)
            or acquisition.replaces_acquisition_id != (prior.id if prior else None)
        ):
            raise ValueError("Histórico/referência de aquisição inválido.")
        previous[acquisition.ingredient_id] = acquisition
        identifiers.add(acquisition.id)
