"""Importação local da despensa; valores técnicos e origem permanecem separados."""

import hashlib
import io
import posixpath
import unicodedata
import zipfile
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict


class InventoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CellSource(InventoryModel):
    kind: Literal["XLSX"] = "XLSX"
    sha256: str
    sheet: str
    cells: list[str]
    loaded_values: list[str | None]
    raw_values: list[str | None]


class InventoryIssue(InventoryModel):
    code: str
    sheet: str
    cells: list[str]
    message: str
    blocking: bool = True


class InventoryItem(InventoryModel):
    id: UUID
    name_original: str
    name_normalized: str
    stock_quantity_original: str | None
    purchase_quantity_original: str | None
    stock_unit_original: str | None
    purchase_unit_original: str | None
    stock_quantity_base: Decimal | None
    purchase_quantity_base: Decimal | None
    dimension: Literal["g", "ml", "un"] | None
    acquisition_total: Decimal | None
    unit_cost: Decimal | None
    issues: list[InventoryIssue]
    stock_source: CellSource | None
    purchase_source: CellSource | None


class InventorySnapshot(InventoryModel):
    id: UUID
    source_sha256: str
    import_policy_version: Literal["1.0"] = "1.0"
    items: list[InventoryItem]
    historical_total: Decimal | None
    issues: list[InventoryIssue]


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


UNITS = {
    "kg": ("g", Decimal("1000")),
    "g": ("g", Decimal("1")),
    "L": ("ml", Decimal("1000")),
    "ml": ("ml", Decimal("1")),
    "un": ("un", Decimal("1")),
    "balde 2kg": ("g", Decimal("2000")),
    "un 500g": ("g", Decimal("500")),
    "un 400g": ("g", Decimal("400")),
    "un 500ml": ("ml", Decimal("500")),
    "un 100ml": ("ml", Decimal("100")),
}


def import_inventory(path: Path, *, allowed_directory: Path) -> InventorySnapshot:
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    path = path.resolve()
    if not path.is_relative_to(allowed_directory.resolve()) or path.suffix.lower() != ".xlsx":
        raise ValueError("Importação exige XLSX no diretório autorizado.")
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    snapshot_id = uuid5(NAMESPACE_URL, f"inventory:1.0:{digest}")
    try:
        raw = _numeric_literals(content)
        book = load_workbook(io.BytesIO(content), data_only=False, keep_links=False)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, InvalidFileException) as exc:
        raise ValueError("estrutura de XLSX inválida; conferir a origem.") from exc
    try:
        headers = {
            "Despensa": ["Ingrediente", "Quantidade em estoque", "Unidade"],
            "Precos": ["Ingrediente", "Quantidade comprada", "Unidade", "Preço total pago (R$)"],
        }
        for sheet, expected in headers.items():
            if (
                sheet not in book.sheetnames
                or [book[sheet].cell(1, column).value for column in range(1, len(expected) + 1)]
                != expected
            ):
                raise ValueError(f"estrutura inválida: conferir aba/cabeçalho {sheet}!A1.")
        stock_rows = list(book["Despensa"].iter_rows(min_row=2, max_col=3))
        price_rows = list(book["Precos"].iter_rows(min_row=2, max_col=4))
        prices = _group_rows(price_rows)
        stocks = _group_rows(stock_rows)
        items = []
        for key in dict.fromkeys([*stocks, *prices]):
            stock_matches, price_matches = stocks.get(key, []), prices.get(key, [])
            stock = stock_matches[0] if stock_matches else None
            price = price_matches[0] if price_matches else None
            name = _text((stock or price)[0].value) or ""
            invalid_names = any(
                not isinstance(row[0].value, str)
                or not normalize_name(row[0].value)
                or len(row[0].value) > 200
                or row[0].data_type == "f"
                for row in [*stock_matches, *price_matches]
            )
            if len(stock_matches) != 1 or len(price_matches) != 1 or invalid_names:
                issues = [
                    InventoryIssue(
                        code="AMBIGUOUS_IDENTITY" if len(rows) > 1 else "IDENTITY_REQUIRED",
                        sheet=sheet,
                        cells=[row[0].coordinate for row in rows],
                        message="Identidade inválida/ambígua ou sem contraparte; confirmar origem.",
                    )
                    for sheet, rows in [("Despensa", stock_matches), ("Precos", price_matches)]
                    if rows
                ]
                items.append(
                    InventoryItem(
                        id=uuid5(snapshot_id, key),
                        name_original=name,
                        name_normalized=key,
                        stock_quantity_original=_text(stock[1].value) if stock else None,
                        purchase_quantity_original=_text(price[1].value) if price else None,
                        stock_unit_original=_text(stock[2].value) if stock else None,
                        purchase_unit_original=_text(price[2].value) if price else None,
                        stock_quantity_base=None,
                        purchase_quantity_base=None,
                        dimension=None,
                        acquisition_total=None,
                        unit_cost=None,
                        issues=issues,
                        stock_source=_source(
                            tuple(c for row in stock_matches for c in row), "Despensa", digest, raw
                        )
                        if stock
                        else None,
                        purchase_source=_source(
                            tuple(c for row in price_matches for c in row), "Precos", digest, raw
                        )
                        if price
                        else None,
                    )
                )
                continue
            issues = []
            stock_dimension, stock_factor = _unit(stock[2], "Despensa", issues)
            price_dimension, price_factor = _unit(price[2], "Precos", issues)
            dimension = stock_dimension if stock_dimension == price_dimension else None
            if stock_dimension and price_dimension and not dimension:
                issues.append(
                    InventoryIssue(
                        code="UNIT_CONVERSION_REQUIRED",
                        sheet="Precos",
                        cells=[price[2].coordinate],
                        message="Dimensões incompatíveis entre estoque e aquisição.",
                    )
                )
            stock_value = _number(
                stock[1],
                "Despensa",
                raw,
                issues,
                positive=False,
                integral=stock[2].value not in {"kg", "g", "L", "ml"},
            )
            purchase_value = _number(
                price[1],
                "Precos",
                raw,
                issues,
                positive=True,
                integral=price[2].value not in {"kg", "g", "L", "ml"},
            )
            stock_base = (
                stock_value * stock_factor if stock_value is not None and stock_factor else None
            )
            purchase_base = (
                purchase_value * price_factor
                if purchase_value is not None and price_factor
                else None
            )
            total = _number(price[3], "Precos", raw, issues, positive=True, money=True)
            with localcontext() as context:
                context.prec = 34
                cost = (
                    total / purchase_base
                    if total is not None and purchase_base and dimension
                    else None
                )
            items.append(
                InventoryItem(
                    id=uuid5(snapshot_id, key),
                    name_original=name,
                    name_normalized=key,
                    stock_quantity_original=_text(stock[1].value),
                    purchase_quantity_original=_text(price[1].value),
                    stock_unit_original=_text(stock[2].value),
                    purchase_unit_original=_text(price[2].value),
                    stock_quantity_base=stock_base,
                    purchase_quantity_base=purchase_base,
                    dimension=dimension,
                    acquisition_total=total,
                    unit_cost=cost,
                    issues=issues,
                    stock_source=_source(stock, "Despensa", digest, raw),
                    purchase_source=_source(price, "Precos", digest, raw),
                )
            )
        return InventorySnapshot(
            id=snapshot_id,
            source_sha256=digest,
            items=items,
            historical_total=(
                sum((item.acquisition_total for item in items), Decimal("0"))
                if all(item.acquisition_total is not None for item in items)
                else None
            ),
            issues=[issue for item in items for issue in item.issues],
        )
    finally:
        book.close()


def _source(row, sheet: str, digest: str, raw: dict) -> CellSource:
    return CellSource(
        sha256=digest,
        sheet=sheet,
        cells=[cell.coordinate for cell in row],
        loaded_values=[None if cell.value is None else str(cell.value) for cell in row],
        raw_values=[
            raw[sheet].get(cell.coordinate, None if cell.value is None else str(cell.value))
            for cell in row
        ],
    )


def _group_rows(rows) -> dict:
    grouped = defaultdict(list)
    for row in rows:
        if any(cell.value is not None for cell in row):
            grouped[normalize_name(_text(row[0].value) or "")].append(row)
    return grouped


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _unit(cell, sheet: str, issues: list) -> tuple[str | None, Decimal | None]:
    if cell.data_type != "f" and isinstance(cell.value, str) and cell.value in UNITS:
        return UNITS[cell.value]
    issues.append(
        InventoryIssue(
            code="UNIT_CONVERSION_REQUIRED",
            sheet=sheet,
            cells=[cell.coordinate],
            message="Unidade ausente ou sem conversão autorizada.",
        )
    )
    return None, None


def _number(
    cell,
    sheet: str,
    raw: dict,
    issues: list,
    *,
    positive: bool,
    money: bool = False,
    integral: bool = False,
) -> Decimal | None:
    literal = raw[sheet].get(cell.coordinate, _text(cell.value))
    try:
        if cell.data_type in {"f", "b", "e"} or literal is None or len(literal) > 100:
            raise ValueError
        value = Decimal(literal)
        if not value.is_finite() or value < 0 or (positive and value == 0) or value >= 10**12:
            raise ValueError
        if not money and value.as_tuple().exponent < -6:
            raise ValueError
        if integral and value != value.to_integral_value():
            raise ValueError
    except (InvalidOperation, ValueError):
        issues.append(
            InventoryIssue(
                code="INVALID_VALUE",
                sheet=sheet,
                cells=[cell.coordinate],
                message="Valor obrigatório inválido; confirmar a origem, sem valor implícito.",
            )
        )
        return None
    if money:
        with localcontext() as context:
            context.prec = 34
            normalized = value.quantize(Decimal("0.01"), ROUND_HALF_UP)
            tolerance = Decimal("0.000000001")
            outside_tolerance = not normalized - tolerance <= value <= normalized + tolerance
        if outside_tolerance or normalized == 0:
            issues.append(
                InventoryIssue(
                    code="MONEY_CONFIRMATION_REQUIRED",
                    sheet=sheet,
                    cells=[cell.coordinate],
                    message="Quantia exige confirmação; diferença material não foi arredondada.",
                )
            )
            return None
        if value != normalized:
            issues.append(
                InventoryIssue(
                    code="MONEY_NORMALIZED",
                    sheet=sheet,
                    cells=[cell.coordinate],
                    message="Resíduo normalizado para centavos; origem preservada.",
                    blocking=False,
                )
            )
        return normalized
    return value


def _numeric_literals(content: bytes) -> dict[str, dict[str, str]]:
    """Léxicos numéricos OOXML, antes da conversão do leitor para float."""
    main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    relationship = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        result = {}
        for sheet in workbook.find(f"{main}sheets"):
            target = targets[sheet.attrib[f"{relationship}id"]]
            member = (
                target.lstrip("/")
                if target.startswith("/")
                else posixpath.normpath(posixpath.join("xl", target))
            )
            tree = ElementTree.fromstring(archive.read(member))
            result[sheet.attrib["name"]] = {
                cell.attrib["r"]: cell.find(f"{main}v").text
                for cell in tree.iter(f"{main}c")
                if cell.attrib.get("t", "n") == "n"
                and cell.find(f"{main}v") is not None
                and cell.find(f"{main}v").text is not None
            }
        return result
