import hashlib
import io
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from dona_maria.inventory import import_inventory

ORIGINAL = Path(__file__).parents[2] / "doc-specs/despensa_dona_maria.xlsx"


def make_inventory(directory, *, stock=None, prices=None):
    """Fixture sintética, sem dependência do documento original privado."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Despensa"
    sheet.append(["Ingrediente", "Quantidade em estoque", "Unidade"])
    for row in stock or [["Arroz branco tipo 1", 5, "kg"]]:
        sheet.append(row)
    sheet = book.create_sheet("Precos")
    sheet.append(["Ingrediente", "Quantidade comprada", "Unidade", "Preço total pago (R$)"])
    for row in prices or [["Arroz branco tipo 1", 5, "kg", 24.9]]:
        sheet.append(row)
    path = directory / "synthetic.xlsx"
    book.save(path)
    book.close()
    return path


@pytest.mark.skipif(not ORIGINAL.exists(), reason="XLSX original fornecido somente localmente")
def test_original_inventory_preserves_provenance_and_uses_purchase_costs():
    before = ORIGINAL.read_bytes()

    snapshot = import_inventory(ORIGINAL, allowed_directory=ORIGINAL.parent)

    assert len(snapshot.items) == 37
    rice = next(item for item in snapshot.items if item.name_normalized == "arroz branco tipo 1")
    assert rice.stock_quantity_base == Decimal("5000")
    assert rice.purchase_quantity_base == Decimal("5000")
    assert rice.unit_cost == Decimal("0.00498")
    assert rice.unit_cost * Decimal("1000") == Decimal("4.98")
    assert rice.stock_source.sheet == "Despensa"
    assert rice.stock_source.cells == ["A2", "B2", "C2"]
    assert rice.purchase_source.sheet == "Precos"
    assert rice.purchase_source.cells == ["A2", "B2", "C2", "D2"]
    assert rice.purchase_source.loaded_values == ["Arroz branco tipo 1", "5", "kg", "24.9"]
    assert snapshot.historical_total == Decimal("663.39")
    chocolate = next(item for item in snapshot.items if "D34" in item.purchase_source.cells)
    assert chocolate.acquisition_total == Decimal("79.90")
    assert chocolate.purchase_source.raw_values[-1] == "79.90000000000001"
    assert any(
        issue.code == "MONEY_NORMALIZED" and issue.cells == ["D34"] for issue in chocolate.issues
    )
    assert snapshot.source_sha256 == hashlib.sha256(before).hexdigest()
    assert ORIGINAL.read_bytes() == before


def test_normalizing_import_noise_preserves_the_loaded_value_and_emits_a_warning(tmp_path):
    path = make_inventory(tmp_path, prices=[["Arroz branco tipo 1", 5, "kg", 79.9]])
    # O escritor XLSX reduz o float; preservar o literal numérico da fixture de origem.
    original_zip = io.BytesIO(path.read_bytes())
    with zipfile.ZipFile(original_zip) as source, zipfile.ZipFile(path, "w") as target:
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet2.xml":
                data = data.replace(b"<v>79.9</v>", b"<v>79.90000000000001</v>")
            target.writestr(entry, data)

    result = import_inventory(path, allowed_directory=tmp_path)

    item = result.items[0]
    assert item.acquisition_total == Decimal("79.90")
    assert item.purchase_source.loaded_values[-1] == "79.9"
    assert item.purchase_source.raw_values[-1] == "79.90000000000001"
    assert [(issue.code, issue.cells, issue.blocking) for issue in item.issues] == [
        ("MONEY_NORMALIZED", ["D2"], False)
    ]


@pytest.mark.parametrize(
    "cell,value",
    [
        ("D2", "12.345"),
        ("D2", None),
        ("D2", "=10+2"),
        ("D2", True),
        ("D2", "NaN"),
        ("D2", "1000000000000"),
        ("D2", "-1"),
        ("B2", 0),
        ("B2", -1),
        ("B2", None),
        ("B2", "=1+1"),
    ],
)
def test_invalid_purchase_data_is_diagnosed_without_an_invented_cost(tmp_path, cell, value):
    path = make_inventory(tmp_path)
    book = load_workbook(path)
    book["Precos"][cell] = value
    book.save(path)
    book.close()

    result = import_inventory(path, allowed_directory=tmp_path)

    item = result.items[0]
    assert item.unit_cost is None
    assert any(issue.blocking and cell in issue.cells for issue in item.issues)
    assert item.purchase_source.loaded_values[1 if cell == "B2" else 3] == (
        None if value is None else str(value)
    )
    if cell == "D2":
        assert item.acquisition_total is None
        assert result.historical_total is None


def test_local_import_refuses_paths_outside_the_configured_directory(tmp_path):
    path = make_inventory(tmp_path)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    before = path.read_bytes()

    with pytest.raises(ValueError, match="diretório autorizado"):
        import_inventory(path, allowed_directory=allowed)

    assert path.read_bytes() == before


def test_invalid_xlsx_container_has_a_safe_structural_diagnostic(tmp_path):
    path = tmp_path / "invalid.xlsx"
    path.write_bytes(b"synthetic invalid XLSX")
    with pytest.raises(ValueError, match="estrutura"):
        import_inventory(path, allowed_directory=tmp_path)


@pytest.mark.parametrize("duplicate", ["ARROZ BRANCO TIPO 1", "Ａｒｒｏｚ branco tipo 1"])
def test_ambiguous_normalized_identity_is_not_silently_joined(tmp_path, duplicate):
    path = make_inventory(
        tmp_path,
        prices=[
            ["Arroz branco tipo 1", 5, "kg", 24.9],
            [duplicate, 1, "kg", 99],
        ],
    )

    result = import_inventory(path, allowed_directory=tmp_path)

    rice = result.items[0]
    assert rice.unit_cost is None
    assert rice.acquisition_total is None
    assert any(issue.code == "AMBIGUOUS_IDENTITY" and issue.blocking for issue in rice.issues)
    assert set(rice.purchase_source.cells) == {"A2", "B2", "C2", "D2", "A3", "B3", "C3", "D3"}


@pytest.mark.parametrize("change", ["sheet", "header"])
def test_missing_sheets_or_required_headers_prevent_import(tmp_path, change):
    path = make_inventory(tmp_path)
    book = load_workbook(path)
    if change == "sheet":
        book["Precos"].title = "Outra"
    else:
        book["Precos"]["B1"] = "Saldo"
    book.save(path)
    book.close()

    with pytest.raises(ValueError, match="estrutura"):
        import_inventory(path, allowed_directory=tmp_path)


@pytest.mark.parametrize(
    "sheet,cell,value",
    [
        ("Precos", "A2", None),
        ("Precos", "A2", "=1+1"),
        ("Precos", "A2", "Outro ingrediente"),
        ("Despensa", "C2", "xícara"),
        ("Despensa", "C2", None),
        ("Precos", "C2", "L"),
    ],
)
def test_unresolved_identity_or_unit_stays_pending_instead_of_producing_a_cost(
    tmp_path, sheet, cell, value
):
    path = make_inventory(tmp_path)
    book = load_workbook(path)
    book[sheet][cell] = value
    book.save(path)
    book.close()

    result = import_inventory(path, allowed_directory=tmp_path)

    assert all(item.unit_cost is None for item in result.items)
    assert any(
        issue.blocking and issue.sheet == sheet and cell in issue.cells for issue in result.issues
    )


@pytest.mark.parametrize("unit", ["un", "balde 2kg", "un 500g"])
def test_indivisible_counts_are_not_silently_fractional(tmp_path, unit):
    path = make_inventory(
        tmp_path,
        stock=[["Arroz branco tipo 1", 1, unit]],
        prices=[["Arroz branco tipo 1", "0.5", unit, 24.9]],
    )
    result = import_inventory(path, allowed_directory=tmp_path)
    assert result.items[0].purchase_quantity_base is None
    assert result.items[0].unit_cost is None
    assert any(issue.blocking and issue.cells == ["B2"] for issue in result.items[0].issues)


def test_join_uses_names_and_stock_changes_do_not_change_acquisition_cost(tmp_path):
    path = make_inventory(
        tmp_path,
        stock=[
            [" Arroz  branco tipo 1 ", 0, "kg"],
            ["Feijão preto", 1, "kg"],
        ],
        prices=[
            ["Feijão preto", 1, "kg", 9.6],
            ["ARROZ BRANCO TIPO 1", 5, "kg", 24.9],
        ],
    )
    result = import_inventory(path, allowed_directory=tmp_path)
    rice = next(item for item in result.items if item.name_normalized == "arroz branco tipo 1")
    assert rice.stock_quantity_base == Decimal("0")
    assert rice.purchase_quantity_base == Decimal("5000")
    assert rice.unit_cost == Decimal("0.00498")
    assert rice.purchase_source.cells == ["A3", "B3", "C3", "D3"]


@pytest.mark.parametrize(
    "value,accepted",
    [
        ("12.340000001", True),
        ("12.3400000011", False),
        ("12.3400000010000000000000000000000000001", False),
    ],
)
def test_import_noise_has_an_absolute_boundary(tmp_path, value, accepted):
    path = make_inventory(tmp_path, prices=[["Arroz branco tipo 1", 5, "kg", value]])
    item = import_inventory(path, allowed_directory=tmp_path).items[0]
    assert item.acquisition_total == (Decimal("12.34") if accepted else None)
    assert any(issue.blocking for issue in item.issues) is not accepted


@pytest.mark.parametrize(
    "name,unit,total,cost",
    [
        ("Frango", "kg", "28.00", "0.028"),
        ("Ovo", "un", "24.00", "24.00"),
        ("Alcaparras", "balde 2kg", "82.00", "0.041"),
        ("Chantilly", "un 500g", "23.67", "0.04734"),
        ("Leite em pó", "un 400g", "15.18", "0.03795"),
        ("Azeite", "un 500ml", "30.99", "0.06198"),
        ("Adoçante", "un 100ml", "1.90", "0.019"),
    ],
)
def test_authorized_package_units_use_the_purchase_denominator(tmp_path, name, unit, total, cost):
    path = make_inventory(tmp_path, stock=[[name, 1, unit]], prices=[[name, 1, unit, total]])
    item = import_inventory(path, allowed_directory=tmp_path).items[0]
    assert item.unit_cost == Decimal(cost)
    assert not any(issue.blocking for issue in item.issues)


@pytest.mark.parametrize("quantity", ["1.000000000000000000000000000001", "1e-1000000"])
def test_quantity_precision_is_checked_without_rounding_or_underflow(tmp_path, quantity):
    path = make_inventory(tmp_path, prices=[["Arroz branco tipo 1", quantity, "kg", "24.90"]])

    item = import_inventory(path, allowed_directory=tmp_path).items[0]

    assert item.purchase_quantity_base is None
    assert item.unit_cost is None
    assert any(issue.code == "INVALID_VALUE" and issue.cells == ["B2"] for issue in item.issues)
    assert item.purchase_source.loaded_values[1] == quantity
