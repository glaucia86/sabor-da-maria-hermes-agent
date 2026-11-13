from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from openpyxl import Workbook, load_workbook

from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository


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


def pricing_evidence(statement):
    return dict(
        turn_ref="synthetic-pricing-turn",
        statement=statement,
        captured_at="2026-11-11T00:00:00Z",
    )


@pytest.fixture
def pricing_workspace(tmp_path, inventory_file, recipe_candidate):
    def create(*, total="20.00", purchased="100", consumed="100", servings=2, batches=1, parts=1):
        book = load_workbook(inventory_file)
        book["Precos"]["B2"] = purchased
        book["Precos"]["C2"] = "g"
        book["Precos"]["D2"] = total
        book.save(inventory_file)
        book.close()
        database = tmp_path / f"pricing-{uuid4()}.sqlite3"
        workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
            "workspace_id"
        ]
        service = BusinessStateReader(
            SQLiteWorkspaceRepository(database), clock=lambda: datetime(2026, 11, 11, tzinfo=UTC)
        )

        def command(tool, **payload):
            revision = service.get_business_state({"workspace_id": workspace})["revision"]
            return getattr(service, tool)(
                dict(workspace_id=workspace, operation_id=str(uuid4()), expected_revision=revision)
                | payload
            )

        source = recipe_candidate["sources"][0]
        recipe_candidate.pop("yield_gap", None)
        recipe_candidate.pop("context_gap", None)
        recipe_candidate.update(
            yield_per_batch=dict(
                servings_per_batch=servings, sale_unit_label="porção", source=source
            ),
            operational_context=(
                "Fixture: preparo manual em um recipiente, sem equipamento compartilhado."
            ),
            context_source=source,
            category_reviews=[
                dict(
                    category=c,
                    requirement_keys=[],
                    method_version=1,
                    source=source,
                    not_applicable_reason="Fixture não exige condição específica nesta categoria.",
                )
                for c in ("EQUIPMENT", "SKILL", "OPERATION")
            ],
        )
        stock = service.get_inventory_snapshot({"workspace_id": workspace})["data"]["items"][0]
        recipe_candidate["ingredients"][0].update(
            ingredient_id=stock["id"], quantity=dict(value=consumed, unit="g")
        )
        recipe_candidate["ingredients"] = [
            deepcopy(recipe_candidate["ingredients"][0]) for _ in range(parts)
        ]
        recipe = command("register_recipe_candidate", candidate=recipe_candidate)["data"][
            "candidate"
        ]
        command(
            "record_recipe_feedback",
            recipe_id=recipe["id"],
            feedback="INTERESTED",
            evidence=pricing_evidence("Tenho interesse neste prato."),
        )
        plan = command(
            "set_production_plan",
            items=[dict(recipe_id=recipe["id"], recipe_version=1, position=0, batches=batches)],
            evidence=pricing_evidence("Confirmo esta produção."),
        )
        item = plan["data"]["plan"]["items"][0]
        if batches > 1:
            command(
                "record_kitchen_facts",
                facts=[
                    dict(
                        category="OPERATION",
                        key="production_arrangement",
                        value="SEQUENTIAL",
                        context=f"{plan['data']['plan']['id']}:1",
                        evidence=pricing_evidence(
                            "Confirmo sequência, capacidade e tempo para estes lotes."
                        ),
                    )
                ],
            )
        evaluation = service.evaluate_purchase_plan({"workspace_id": workspace})["data"]
        acceptance = command(
            "accept_recipe",
            recipe_id=recipe["id"],
            plan_item_id=item["plan_item_id"],
            evaluation_id=evaluation["evaluation_id"],
            evidence=pricing_evidence("Aceito este prato."),
        )
        assert acceptance["ok"], acceptance
        return service, workspace, recipe, acceptance["data"]["acceptance"], command, database

    return create


def s04_evidence(statement):
    return dict(turn_ref="synthetic-s04-user", statement=statement,
                captured_at="2026-11-12T12:00:00Z")


@pytest.fixture
def clarification(tmp_path, inventory_file, recipe_candidate):
    book = load_workbook(inventory_file)
    book["Despensa"].append(["Cobertura de chocolate", 1, "un"])
    book["Precos"].append(["Cobertura de chocolate", 1, "un", "79.90"])
    book.save(inventory_file)
    book.close()
    database = tmp_path / "clarification.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    service = BusinessStateReader(SQLiteWorkspaceRepository(database))
    stock = service.get_inventory_snapshot({"workspace_id": workspace})["data"]
    rice = next(i for i in stock["items"] if i["name_original"] == "Arroz")
    chocolate = next(i for i in stock["items"] if i["name_original"] != "Arroz")
    recipe_candidate["ingredients"][0]["ingredient_id"] = rice["id"]
    line = deepcopy(recipe_candidate["ingredients"][0])
    line.update(description="Cobertura", ingredient_id=chocolate["id"])
    recipe_candidate["ingredients"].append(line)
    source = recipe_candidate["sources"][0]
    recipe_candidate.pop("yield_gap")
    recipe_candidate.pop("context_gap")
    recipe_candidate.update(
        yield_per_batch=dict(servings_per_batch=2, sale_unit_label="porção", source=source),
        operational_context="Fixture de preparo manual em um recipiente.", context_source=source,
        category_reviews=[dict(category=c, requirement_keys=[], method_version=1, source=source,
                               not_applicable_reason="Fixture sem requisito nesta categoria.")
                          for c in ("EQUIPMENT", "SKILL", "OPERATION")],
    )

    def command(tool, **payload):
        revision = service.get_business_state({"workspace_id": workspace})["revision"]
        return getattr(service, tool)(dict(workspace_id=workspace, operation_id=str(uuid4()),
                                         expected_revision=revision) | payload)

    return service, workspace, command, recipe_candidate, chocolate, stock, inventory_file, database

@pytest.fixture
def shared_plan(clarification):
    """Dois pratos sintéticos, uma origem e uma oferta confirmada, pela API pública."""
    service, workspace, command, candidate, _, stock, path, database = clarification
    stamp = datetime.now(UTC).isoformat()
    evidence = dict(
        turn_ref="synthetic-s07-user", statement="Confirmo esta produção.", captured_at=stamp
    )

    def create(*, amounts=("4000", "3000"), complement=False, extra="0.00", minutes=None):
        recipes = []
        ingredient_id = candidate["ingredients"][0]["ingredient_id"]
        for index, amount in enumerate(amounts):
            payload = deepcopy(candidate)
            payload["title"] = f"Prato {index + 1} — fixture S07"
            payload["ingredients"] = payload["ingredients"][:1]
            payload["ingredients"][0].update(
                description="Mel" if complement else "Arroz",
                ingredient_id=None if complement and index == 0 else ingredient_id,
                quantity=dict(value=amount, unit="g"),
            )
            if minutes:
                payload["requirements"] = [
                    dict(
                        category="OPERATION",
                        key="time",
                        condition="MIN_AVAILABLE_TIME",
                        value=str(minutes[index]),
                        unit="min",
                        reason="Tempo da fixture.",
                        source=payload["sources"][0],
                    )
                ]
                review = next(
                    r for r in payload["category_reviews"] if r["category"] == "OPERATION"
                )
                review.update(requirement_keys=["time"], not_applicable_reason=None)
            result = command("register_recipe_candidate", candidate=payload)
            assert result["ok"], result
            recipe = result["data"]["candidate"]
            if complement and index == 0:
                result = command(
                    "resolve_recipe_ingredient",
                    recipe_id=recipe["id"],
                    recipe_version=1,
                    line_id=recipe["ingredients"][0]["line_id"],
                    new_ingredient=dict(name="Mel", dimension="g"),
                    evidence=evidence,
                )
                assert result["ok"], result
                recipe = result["data"]["candidate"]
                ingredient_id = result["data"]["ingredient_id"]
            recipes.append(recipe)
            assert command(
                "record_recipe_feedback",
                recipe_id=recipe["id"],
                feedback="INTERESTED",
                evidence=evidence,
            )["ok"]
        content, price = ("1000", "20.00") if complement else ("5000", "30.00")
        quote = command(
            "register_complement_quote",
            quote=dict(
                ingredient_id=ingredient_id,
                description="Oferta sintética S07",
                package_quantity=dict(value=content, unit="g"),
                package_price=price,
                purchase_extra_total=extra,
                extra_conditions="Retirada com encargos informados",
                availability="AVAILABLE",
                availability_context="Retirada hoje",
                max_packages=100,
                supplier="Fornecedor sintético",
                source=candidate["sources"][0],
            ),
        )
        assert quote["ok"], quote
        quote = quote["data"]["quote"]
        result = command(
            "confirm_complement_quote",
            quote_id=quote["id"],
            quote_version=1,
            scope=dict(
                package_quantity=dict(value=content, unit="g"),
                package_price=price,
                purchase_extra_total=extra,
                extra_conditions=quote["extra_conditions"],
                availability_context=quote["availability_context"],
                supplier=quote["supplier"],
                packages=100,
            ),
            evidence=evidence
            | {
                "statement": f"Confirmo 100 pacotes de {content} g a R$ {price.replace('.', ',')} "
                f"por pacote, encargos R$ {extra.replace('.', ',')}, "
                "Retirada com encargos informados, disponível em "
                "Fornecedor sintético: Retirada hoje."
            },
        )
        assert result["ok"], result
        return dict(
            service=service,
            workspace=workspace,
            command=command,
            recipes=recipes,
            quote=quote,
            evidence=evidence,
            original=stock,
            path=path,
            database=database,
        )

    return create
