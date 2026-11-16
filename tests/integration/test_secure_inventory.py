"""S18: fronteira local de importação, somente arquivos e bancos sintéticos."""

import io
import os
import subprocess
import zipfile
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import pytest
from openpyxl import load_workbook
from openpyxl.xml.constants import XLSM, XLSX, XLTM, XLTX

from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.inventory import import_inventory
from dona_maria.persistence import SQLiteWorkspaceRepository


@pytest.mark.parametrize("extra,accepted", [(0, True), (1, False)])
def test_xlsx_file_limit_preserves_existing_database(tmp_path, inventory_file, extra, accepted):
    database = tmp_path / "inventory.sqlite3"
    bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    before = database.read_bytes()
    content = inventory_file.read_bytes()
    inventory_file.write_bytes(b" " * (5 * 1024 * 1024 + extra - len(content)) + content)
    if accepted:
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    else:
        with pytest.raises(ValueError, match="limite"):
            bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
        assert database.read_bytes() == before


def rewrite_member(path, name, transform):
    content = path.read_bytes()
    with (
        zipfile.ZipFile(io.BytesIO(content)) as source,
        zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target,
    ):
        for entry in source.infolist():
            data = source.read(entry)
            target.writestr(entry.filename, transform(data) if entry.filename == name else data)


@pytest.mark.parametrize("extra,accepted", [(0, True), (1, False)])
def test_total_worksheet_rows_limit(tmp_path, inventory_file, extra, accepted):
    # Duas abas com dois registros cada; linhas vazias também consomem o limite.
    rows = b"".join(f'<row r="{i}"/>'.encode() for i in range(3, 19999 + extra))
    rewrite_member(
        inventory_file,
        "xl/worksheets/sheet1.xml",
        lambda data: data.replace(b"</sheetData>", rows + b"</sheetData>"),
    )
    database = tmp_path / "inventory.sqlite3"
    if accepted:
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    else:
        with pytest.raises(ValueError, match="linhas"):
            bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
        assert not database.exists()


@pytest.mark.parametrize("extra,accepted", [(0, True), (1, False)])
def test_implicit_rows_after_sparse_row_obey_aggregate_limit(
    tmp_path, inventory_file, extra, accepted
):
    database = tmp_path / "inventory.sqlite3"
    bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    before = database.read_bytes()
    rewrite_member(
        inventory_file,
        "xl/worksheets/sheet1.xml",
        lambda data: data.replace(
            b"</sheetData>",
            b'<row r="19997"/>' + b"<row/>" * (1 + extra) + b"</sheetData>",
        ),
    )
    if accepted:
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    else:
        with pytest.raises(ValueError, match="linhas"):
            bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
        assert database.read_bytes() == before


@pytest.mark.parametrize("extra,accepted", [(0, True), (1, False)])
def test_expanded_zip_limit_counts_all_members(tmp_path, inventory_file, extra, accepted):
    database = tmp_path / "inventory.sqlite3"
    bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    before = database.read_bytes()
    with zipfile.ZipFile(io.BytesIO(inventory_file.read_bytes())) as source:
        expanded = sum(info.file_size for info in source.infolist())
    with zipfile.ZipFile(inventory_file, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("padding.bin", b"x" * (50 * 1024 * 1024 + extra - expanded))
    assert inventory_file.stat().st_size < 5 * 1024 * 1024
    if accepted:
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    else:
        with pytest.raises(ValueError, match="limite"):
            bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
        assert database.read_bytes() == before


@pytest.mark.parametrize(
    "unsafe", ["formula", "macro", "external", "malformed", "xml", "root", "deflate"]
)
def test_unsafe_workbook_never_changes_snapshot(tmp_path, inventory_file, unsafe):
    database = tmp_path / "inventory.sqlite3"
    bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    before = database.read_bytes()
    if unsafe == "formula":
        rewrite_member(
            inventory_file,
            "xl/worksheets/sheet2.xml",
            lambda data: data.replace(b"<v>24.9</v>", b"<f>10+2</f><v>12</v>"),
        )
    elif unsafe in {"macro", "external"}:
        with zipfile.ZipFile(inventory_file, "a") as archive:
            archive.writestr(
                "xl/vbaProject.bin" if unsafe == "macro" else "xl/externalLinks/link.xml", b"x"
            )
    elif unsafe == "xml":
        rewrite_member(inventory_file, "xl/worksheets/sheet2.xml", lambda _: b"<invalid")
    elif unsafe == "root":
        rewrite_member(inventory_file, "xl/workbook.xml", lambda _: b"<invalid/>")
    elif unsafe == "deflate":
        with zipfile.ZipFile(inventory_file) as archive:
            entry = archive.infolist()[0]
        data = bytearray(inventory_file.read_bytes())
        start = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        data[start : start + 8] = b"\xff" * 8
        inventory_file.write_bytes(data)
    else:
        inventory_file.write_bytes(b"PK synthetic broken ZIP")
    original = inventory_file.read_bytes()
    with pytest.raises(ValueError):
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert database.read_bytes() == before
    assert inventory_file.read_bytes() == original


@pytest.mark.parametrize("link_kind", ["symlink", "junction"])
def test_directory_link_cannot_escape_authorized_root(tmp_path, inventory_file, link_kind):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    link = allowed / "escape"
    if link_kind == "junction":
        if os.name != "nt":
            pytest.skip("Junções pertencem ao Windows.")
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(tmp_path)],
            check=True,
            capture_output=True,
        )
    else:
        try:
            link.symlink_to(tmp_path, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"Criação de symlink indisponível: {error.winerror}")
    database = tmp_path / "existing.sqlite3"
    bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    before = database.read_bytes()
    try:
        with pytest.raises(ValueError, match="diretório autorizado"):
            bootstrap_workspace(database, link / inventory_file.name, allowed_directory=allowed)
        assert database.read_bytes() == before
    finally:
        link.rmdir() if link_kind == "junction" else link.unlink()


@pytest.mark.parametrize(
    "damage", ["dimension", "duplicate", "entities", "sparse", "cell", "aggregate"]
)
def test_structural_abuse_never_creates_a_partial_snapshot(tmp_path, inventory_file, damage):
    if damage == "duplicate":
        with zipfile.ZipFile(inventory_file, "a") as archive:
            with pytest.warns(UserWarning, match="Duplicate"):
                archive.writestr("xl/workbook.xml", b"<invalid/>")
    else:

        def damage_xml(data):
            if damage == "dimension":
                return data.replace(b'ref="A1:C2"', b'ref="A1:C20001"')
            if damage == "sparse":
                return data.replace(b'<row r="2">', b'<row r="20001">')
            if damage == "cell":
                return data.replace(b'r="A2"', b'r="A20001"')
            if damage == "aggregate":
                return data.replace(b'r="A2"', b'r="A20000"')
            return b'<!DOCTYPE worksheet [<!ENTITY data "unsafe">]>' + data

        rewrite_member(inventory_file, "xl/worksheets/sheet1.xml", damage_xml)
    database = tmp_path / "uncreated.sqlite3"
    with pytest.raises(ValueError):
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert not database.exists()


@pytest.mark.parametrize("damage", ["formula", "rows"])
def test_nonstandard_worksheet_relationship_still_enforces_guards(tmp_path, inventory_file, damage):
    content = inventory_file.read_bytes()
    old, new = "xl/worksheets/sheet1.xml", "xl/custom/stock.data"
    with (
        zipfile.ZipFile(io.BytesIO(content)) as source,
        zipfile.ZipFile(inventory_file, "w") as target,
    ):
        for entry in source.infolist():
            data = source.read(entry)
            if entry.filename == old:
                data = (
                    data.replace(b"<v>5</v>", b"<f>1+1</f><v>2</v>")
                    if damage == "formula"
                    else data.replace(b'r="A2"', b'r="A20001"')
                )
            if entry.filename in {"xl/_rels/workbook.xml.rels", "[Content_Types].xml"}:
                data = data.replace(old.encode(), new.encode())
            target.writestr(new if entry.filename == old else entry.filename, data)
    with pytest.raises(ValueError):
        bootstrap_workspace(
            tmp_path / "uncreated.sqlite3", inventory_file, allowed_directory=tmp_path
        )


@pytest.mark.parametrize("content_type", [XLSX, XLTX, XLSM, XLTM])
def test_alternative_main_part_cannot_bypass_validation(tmp_path, inventory_file, content_type):
    database = tmp_path / "inventory.sqlite3"
    bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    before = database.read_bytes()
    content = inventory_file.read_bytes()
    with (
        zipfile.ZipFile(io.BytesIO(content)) as source,
        zipfile.ZipFile(inventory_file, "w") as target,
    ):
        for entry in source.infolist():
            data = source.read(entry)
            if entry.filename == "[Content_Types].xml":
                if content_type == XLSX:
                    data = data.replace(b"/xl/workbook.xml", b"/xl/alternate.xml")
                else:
                    override = (
                        f'<Override PartName="/xl/alternate.xml" ContentType="{content_type}"/>'
                    ).encode()
                    data = data.replace(b"</Types>", override + b"</Types>")
            target.writestr(entry.filename, data)
        target.writestr("xl/alternate.xml", source.read("xl/workbook.xml"))
        target.writestr(
            "xl/_rels/alternate.xml.rels",
            source.read("xl/_rels/workbook.xml.rels").replace(
                b"/xl/worksheets/sheet1.xml", b"/xl/worksheets/actual.xml"
            ),
        )
        target.writestr(
            "xl/worksheets/actual.xml",
            source.read("xl/worksheets/sheet1.xml").replace(
                b"</sheetData>", b'<row r="20001"/></sheetData>'
            ),
        )
    with pytest.raises(ValueError):
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert database.read_bytes() == before


def test_new_import_policy_does_not_reuse_or_rewrite_legacy_incomplete_snapshot(
    tmp_path, inventory_file
):
    book = load_workbook(inventory_file)
    book["Precos"].delete_rows(2)
    book.save(inventory_file)
    book.close()
    current = import_inventory(inventory_file, allowed_directory=tmp_path)
    legacy = current.model_copy(
        deep=True,
        update={
            "id": uuid5(NAMESPACE_URL, f"inventory:1.0:{current.source_sha256}"),
            "import_policy_version": "1.0",
        },
    )
    legacy.items[0].stock_quantity_base = legacy.items[0].dimension = None
    database = tmp_path / "legacy.sqlite3"
    repository = SQLiteWorkspaceRepository(database)
    old = repository.bootstrap(legacy, datetime.now(UTC))
    reader = BusinessStateReader(repository)
    before = reader.get_inventory_snapshot({"workspace_id": old["workspace_id"]})
    fresh = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    imported = reader.get_inventory_snapshot({"workspace_id": fresh["workspace_id"]})["data"]
    assert imported["items"][0]["stock_quantity_base"] == "5000"
    assert fresh["snapshot_id"] != old["snapshot_id"]
    assert imported["import_policy_version"] == "2.0"
    assert reader.get_inventory_snapshot({"workspace_id": old["workspace_id"]}) == before


@pytest.mark.parametrize("feature", ["alias", "mergeCell", "hyperlink"])
def test_repeated_parts_and_expanding_ranges_are_refused_before_loading(
    tmp_path, inventory_file, feature
):
    if feature == "alias":
        rewrite_member(
            inventory_file,
            "xl/workbook.xml",
            lambda data: data.replace(
                b"</sheets>",
                b'<sheet xmlns:r="http://schemas.openxmlformats.org/'
                b'officeDocument/2006/relationships" '
                b'name="Alias" sheetId="3" r:id="rId1"/></sheets>',
            ),
        )
    else:
        # O retângulo pequeno comprova recusa do recurso, sem executar expansão maliciosa.
        xml = (
            b'<mergeCells><mergeCell ref="E1:F3"/></mergeCells>'
            if feature == "mergeCell"
            else b'<hyperlinks><hyperlink ref="E1:F3" location="A1"/></hyperlinks>'
        )
        rewrite_member(
            inventory_file,
            "xl/worksheets/sheet1.xml",
            lambda data: data.replace(b"</worksheet>", xml + b"</worksheet>"),
        )
    database = tmp_path / "uncreated.sqlite3"
    with pytest.raises(ValueError):
        bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)
    assert not database.exists()


def test_understated_dimension_cannot_silently_truncate_inventory(tmp_path, inventory_file):
    rewrite_member(
        inventory_file,
        "xl/worksheets/sheet1.xml",
        lambda data: data.replace(b'ref="A1:C2"', b'ref="A1:A1"'),
    )
    snapshot = import_inventory(inventory_file, allowed_directory=tmp_path)
    assert len(snapshot.items) == 1
    assert str(snapshot.items[0].stock_quantity_base) == "5000"
    assert str(snapshot.items[0].acquisition_total) == "24.90"
