"""Ofertas comerciais pesquisadas; registro não representa confirmação nem compra."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from dona_maria.candidates import CandidateModel, Note, Quantity, ShortText, UUIDText, WebSource
from dona_maria.pricing import FINANCIAL_CONTEXT
from dona_maria.production import CommandMeta, UserEvidence

MoneyText = Annotated[str, Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,2})?$")]


class PackageQuantity(Quantity):
    unit: Literal["g", "ml", "un"]

    @field_validator("value")
    @classmethod
    def positive_quantity(cls, value):
        number = Decimal(value)
        if number <= 0:
            raise ValueError("Conteúdo conhecido deve ser positivo.")
        with localcontext(FINANCIAL_CONTEXT):
            return format(number.normalize(), "f")


class QuoteInput(CandidateModel):
    ingredient_id: UUIDText
    description: ShortText
    package_quantity: PackageQuantity | None = None
    package_quantity_gap: Note | None = None
    package_price: MoneyText | None = None
    package_price_gap: Note | None = None
    purchase_extra_total: MoneyText | None = None
    purchase_extra_total_gap: Note | None = None
    extra_conditions: Note | None = None
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    availability_context: Note
    max_packages: Annotated[StrictInt, Field(ge=0)] | None = None
    supplier: ShortText
    source: WebSource | None = None
    valid_until: AwareDatetime | None = None

    @field_validator("valid_until", mode="before")
    @classmethod
    def textual_deadline(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("Prazo exige data RFC 3339 textual com timezone.")
        return value

    @field_validator("valid_until")
    @classmethod
    def utc_deadline(cls, value):
        return value.astimezone(UTC) if value is not None else None

    @field_validator("package_price", "purchase_extra_total")
    @classmethod
    def money_text(cls, value, info):
        if value is None:
            return None
        number = Decimal(value)
        if info.field_name == "package_price" and number <= 0:
            raise ValueError("Preço conhecido deve ser positivo.")
        return format(number, ".2f")

    @model_validator(mode="after")
    def explicit_gaps(self):
        for field in (
            "description",
            "supplier",
            "availability_context",
            "extra_conditions",
            "package_quantity_gap",
            "package_price_gap",
            "purchase_extra_total_gap",
        ):
            value = getattr(self, field)
            if value is not None and not value.strip():
                raise ValueError(f"{field} deve ter conteúdo.")
        for field in ("package_quantity", "package_price", "purchase_extra_total"):
            value, gap = getattr(self, field), getattr(self, f"{field}_gap")
            if value is None and (gap is None or not gap.strip()):
                raise ValueError(f"{field} ausente exige lacuna explícita.")
        if self.purchase_extra_total is not None and not self.extra_conditions:
            raise ValueError("Encargos conhecidos exigem condições da oferta.")
        return self


class RegisterQuoteRequest(CommandMeta):
    quote: QuoteInput
    quote_id: UUIDText | None = None
    expected_quote_version: Annotated[StrictInt, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def revision_pair(self):
        if (self.quote_id is None) != (self.expected_quote_version is None):
            raise ValueError("Revisão exige ID e versão da cotação juntos.")
        return self


class ConfirmationScope(CandidateModel):
    package_quantity: PackageQuantity
    package_price: MoneyText
    purchase_extra_total: MoneyText
    extra_conditions: Note
    availability_context: Note
    supplier: ShortText
    packages: Annotated[StrictInt, Field(gt=0)]


class ConfirmQuoteRequest(CommandMeta):
    quote_id: UUIDText
    quote_version: Annotated[StrictInt, Field(gt=0)]
    scope: ConfirmationScope
    evidence: UserEvidence


class QuoteConfirmation(CandidateModel):
    quote_id: UUIDText
    quote_version: Annotated[StrictInt, Field(gt=0)]
    scope: ConfirmationScope
    evidence: UserEvidence
    confirmed_at: AwareDatetime
    confirmation_valid_until: AwareDatetime

    def status_at(self, now: datetime) -> Literal["ESTIMATED", "EXPIRED", "CONFIRMED"]:
        if now < self.confirmed_at:
            return "ESTIMATED"
        return "EXPIRED" if now >= self.confirmation_valid_until else "CONFIRMED"


def _confirmation_deadline(confirmed_at: datetime, valid_until: datetime | None) -> datetime:
    try:
        operational_deadline = confirmed_at + timedelta(hours=24)
    except OverflowError as exc:
        raise ValueError("Data de confirmação fora do intervalo de validade suportado.") from exc
    return min(operational_deadline, valid_until) if valid_until else operational_deadline


def explicit_quote_confirmation(request):
    scope = request.scope
    price = format(Decimal(scope.package_price), ".2f").replace(".", ",")
    extra = format(Decimal(scope.purchase_extra_total), ".2f").replace(".", ",")
    expected = (
        f"Confirmo {scope.packages} pacote{'s' if scope.packages != 1 else ''} de "
        f"{scope.package_quantity.value} {scope.package_quantity.unit} a R$ {price} por pacote, "
        f"encargos R$ {extra}, {scope.extra_conditions}, disponível em "
        f"{scope.supplier}: {scope.availability_context}"
    )

    def normalized(text):
        return " ".join(text.casefold().strip().rstrip(".! ").split())

    return normalized(request.evidence.statement) == normalized(expected)


def create_confirmation(quote, request):
    confirmed_at = request.evidence.captured_at
    return QuoteConfirmation(
        quote_id=str(quote.id),
        quote_version=quote.version,
        scope=request.scope,
        evidence=request.evidence,
        confirmed_at=confirmed_at,
        confirmation_valid_until=_confirmation_deadline(confirmed_at, quote.valid_until),
    )


def scope_matches_quote(scope, quote):
    return (
        not quote.public()["gaps"]
        and quote.availability == "AVAILABLE"
        and (quote.max_packages is None or scope.packages <= quote.max_packages)
        and scope.package_quantity == quote.package_quantity
        and Decimal(scope.package_price) == Decimal(quote.package_price)
        and Decimal(scope.purchase_extra_total) == Decimal(quote.purchase_extra_total)
        and all(
            getattr(scope, field) == getattr(quote, field)
            for field in ("extra_conditions", "availability_context", "supplier")
        )
    )


class ComplementQuote(QuoteInput):
    source: WebSource
    id: UUIDText
    version: Annotated[StrictInt, Field(gt=0)]
    recorded_at: AwareDatetime

    def public(self, confirmation=None, now=None):
        now = now or datetime.now(UTC)
        return self.model_dump(mode="json") | {
            "status": confirmation.status_at(now) if confirmation else "ESTIMATED",
            "confirmation": confirmation.model_dump(mode="json") if confirmation else None,
            "gaps": [
                field
                for field in ("package_quantity", "package_price", "purchase_extra_total")
                if getattr(self, field) is None
            ]
            + (["availability"] if self.availability == "UNKNOWN" else []),
        }


def current_confirmation(quote, confirmations):
    return next(
        (
            c
            for c in reversed(confirmations)
            if c.quote_id == quote.id and c.quote_version == quote.version
        ),
        None,
    )


def validate_quote_references(state, snapshot):
    ingredients = {i.id for i in snapshot.items} | {i.id for i in state.complement_ingredients}
    history, latest = {}, {}
    for quote in state.complement_quotes:
        previous = latest.get(quote.id)
        if (
            quote.ingredient_id not in ingredients
            or quote.version != (previous.version + 1 if previous else 1)
            or (previous and previous.ingredient_id != quote.ingredient_id)
        ):
            raise ValueError("Histórico/referência de cotação inválido.")
        history[quote.id, quote.version] = quote
        latest[quote.id] = quote
    for confirmation in state.quote_confirmations:
        quote = history.get((confirmation.quote_id, confirmation.quote_version))
        if quote is None:
            raise ValueError("Confirmação referencia oferta inexistente.")
        deadline = _confirmation_deadline(confirmation.confirmed_at, quote.valid_until)
        if (
            not scope_matches_quote(confirmation.scope, quote)
            or not explicit_quote_confirmation(confirmation)
            or confirmation.confirmation_valid_until != deadline
            or confirmation.confirmed_at != confirmation.evidence.captured_at
            or deadline <= confirmation.confirmed_at
        ):
            raise ValueError("Confirmação não corresponde à oferta/validade histórica.")
    selected = set()
    for selection in state.plan.quote_selections if state.plan else []:
        quote = history.get((selection.quote_id, selection.quote_version))
        if (
            quote is None
            or quote.ingredient_id != selection.ingredient_id
            or selection.ingredient_id in selected
        ):
            raise ValueError("Seleção de cotação inválida.")
        selected.add(selection.ingredient_id)


def simulate_purchases(lines, selections, quotes, gaps, confirmations=(), now=None):
    now = now or datetime.now(UTC)
    total = Decimal("0")
    totals_known = not gaps
    selections_by_ingredient = {str(s.ingredient_id): s for s in selections}
    latest_quotes = {quote.id: quote for quote in quotes}
    with localcontext(FINANCIAL_CONTEXT):
        for line in lines:
            if line["shortage"] is None:
                totals_known = False
                continue
            shortage = Decimal(line["shortage"])
            if shortage == 0:
                line["purchase"] = dict(
                    packages=0,
                    purchased_quantity="0",
                    planned_surplus="0",
                    disbursement="0.00",
                    consumed_ingredient_cost="0.00",
                    status="NO_PURCHASE_NEEDED",
                )
                continue
            selection = selections_by_ingredient.get(line["ingredient_id"])
            quote = latest_quotes.get(selection.quote_id) if selection else None
            if quote and quote.version != selection.quote_version:
                gaps.append(f"STALE_QUOTE: {quote.id}; selecione a versão {quote.version}")
                totals_known = False
                continue
            if quote is None:
                gaps.append(f"MISSING_INFORMATION: selecione cotação para {line['ingredient_id']}")
                totals_known = False
                continue
            confirmation = current_confirmation(quote, confirmations)
            source = quote.public(confirmation, now)
            purchase = dict(
                quote_id=str(quote.id),
                quote_version=quote.version,
                packages=None,
                purchased_quantity=None,
                planned_surplus=None,
                disbursement=None,
                consumed_ingredient_cost=None,
                confirmation=source["confirmation"],
                source=source,
            )
            line["purchase"] = purchase
            for gap in purchase["source"]["gaps"]:
                gaps.append(f"MISSING_INFORMATION: {gap} de {quote.id}")
            if source["status"] == "ESTIMATED":
                gaps.append(f"PRICE_UNCONFIRMED: {quote.id}")
            elif source["status"] == "EXPIRED":
                gaps.append(f"QUOTE_EXPIRED: {quote.id}")
            if quote.package_quantity is None:
                totals_known = False
                continue
            if quote.package_quantity.unit != line["unit"]:
                gaps.append(f"UNIT_CONVERSION_REQUIRED: embalagem de {quote.id}")
                totals_known = False
                continue
            content = Decimal(quote.package_quantity.value)
            packages = int((shortage / content).to_integral_value(rounding=ROUND_CEILING))
            if confirmation and packages > confirmation.scope.packages:
                gaps.append(
                    f"CONFIRMATION_INSUFFICIENT: {quote.id}; necessários {packages}; "
                    f"confirmados {confirmation.scope.packages}"
                )
            purchased = content * packages
            purchase.update(
                packages=packages,
                purchased_quantity=format(purchased, "f"),
                planned_surplus=format(purchased - shortage, "f"),
            )
            if quote.availability == "UNAVAILABLE" or (
                quote.max_packages is not None and packages > quote.max_packages
            ):
                gaps.append(
                    f"OFFER_INSUFFICIENT: {quote.id}; necessários {packages}; "
                    f"limite {quote.max_packages}; disponibilidade {quote.availability}"
                )
            if quote.package_price is not None:
                purchase["consumed_ingredient_cost"] = format(
                    shortage * Decimal(quote.package_price) / content, "f"
                )
                purchase["package_spend"] = format(Decimal(quote.package_price) * packages, ".2f")
            purchase["purchase_extra_total"] = quote.purchase_extra_total
            if quote.package_price is None or quote.purchase_extra_total is None:
                totals_known = False
                continue
            disbursement = Decimal(quote.package_price) * packages + Decimal(
                quote.purchase_extra_total
            )
            purchase["disbursement"] = format(disbursement, ".2f")
            total += disbursement
    return format(total, ".2f") if totals_known else None
