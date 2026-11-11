import pytest
from openpyxl import Workbook


@pytest.fixture
def inventory_file(tmp_path):
    """Fotografia sintética e pública; não representa a planilha original."""
    book = Workbook()
    book.active.title = "Despensa"
    book.active.append(["Ingrediente", "Quantidade em estoque", "Unidade"])
    book.active.append(["Arroz", 5, "kg"])
    prices = book.create_sheet("Precos")
    prices.append(["Ingrediente", "Quantidade comprada", "Unidade", "Preço total pago (R$)"])
    prices.append(["Arroz", 5, "kg", 24.9])
    path = tmp_path / "synthetic.xlsx"
    book.save(path)
    book.close()
    return path


@pytest.fixture
def recipe_candidate():
    source = {
        "kind": "WEB",
        "url": "https://example.org/receita-fixture",
        "title": "Fixture sintética offline",
        "excerpt": "100 g de arroz; cozinhe em água.",
        "retrieved_at": "2026-11-11T12:00:00Z",
    }
    return {
        "title": "Arroz — fixture sintética offline",
        "sources": [source],
        "ingredients": [
            {
                "description": "Arroz",
                "original_measure": {
                    "raw_text": "100 g de arroz",
                    "value": "100",
                    "unit_label": "g",
                    "source": source,
                },
                "quantity": {"value": "100", "unit": "g"},
                "preparation_basis": "RAW",
                "source": source,
            }
        ],
        "method": "Cozinhe em água.",
        "method_source": source,
        "yield_gap": "Fonte não informa rendimento.",
        "context_gap": "Fonte não informa duração nem contexto operacional.",
    }
