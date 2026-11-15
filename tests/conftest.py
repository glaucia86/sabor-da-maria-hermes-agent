from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import Workbook, load_workbook

from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository

OPERATOR_STDIO_ARGS = [
    "-X",
    "utf8",
    "-B",
    str(Path(__file__).resolve().parents[1] / "evals/operator_stdio.py"),
]


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
def reconfirm_attendance():
    """Manifestação/atestação sintéticas explícitas para fixtures anteriores ao S14."""
    from dona_maria.approvals import ApprovalService, migrate_proposals
    from dona_maria.production import KitchenFactInput, PlanItemInput, PreferenceInput

    def prepare(reader, workspace, database):
        migrate_proposals(reader.repository, database.with_name(f"s14-backup-{uuid4()}.sqlite3"))
        local = ApprovalService(reader.repository, clock=reader.clock)

        def decide(kind, **payload):
            proposal = local.propose(
                dict(
                    workspace_id=workspace,
                    operation_id=str(uuid4()),
                    expected_revision=reader.get_business_state({"workspace_id": workspace})[
                        "revision"
                    ],
                    command={"kind": kind, "payload": payload},
                )
            )
            return local.approve(workspace, proposal["id"], proposal["hash"], attest=True)

        previous = reader.get_business_state({"workspace_id": workspace})["data"]
        for preference in previous["preferences"]:
            if preference["validity"] == "VALID":
                fields = {
                    k: v
                    for k, v in preference.items()
                    if k in PreferenceInput.model_fields and k != "evidence"
                }
                fields["replaces_preference_id"] = preference["id"]
                decide("record_user_preferences", preferences=[fields])
        if previous["plan"]:
            for item in previous["plan"]["items"]:
                decide("record_recipe_feedback", recipe_id=item["recipe_id"], feedback="INTERESTED")
            plan = decide(
                "set_production_plan",
                items=[
                    {k: v for k, v in item.items() if k in PlanItemInput.model_fields}
                    for item in previous["plan"]["items"]
                ],
                quote_selections=previous["plan"]["quote_selections"],
            )["data"]["plan"]
        else:
            plan = None
        for fact in previous["kitchen_facts"]:
            fields = {
                k: v
                for k, v in fact.items()
                if k in KitchenFactInput.model_fields and k != "evidence"
            }
            fields["replaces_fact_id"] = fact["id"]
            if plan and fact["key"] == "production_arrangement":
                fields["context"] = f"{plan['id']}:{plan['version']}"
            decide("record_kitchen_facts", facts=[fields])
        if plan:
            for item in plan["items"]:
                evaluation = reader.evaluate_purchase_plan({"workspace_id": workspace})["data"]
                accepted = decide(
                    "accept_recipe",
                    recipe_id=item["recipe_id"],
                    plan_item_id=item["plan_item_id"],
                    evaluation_id=evaluation["evaluation_id"],
                )
                choice = next(
                    (d for d in previous["menu"] if d["recipe_id"] == item["recipe_id"]), None
                )
                if choice:
                    acceptance = accepted["data"]["acceptance"]
                    revision = reader.get_business_state({"workspace_id": workspace})["revision"]
                    calculation = reader.calculate_pricing_scenarios(
                        dict(
                            workspace_id=workspace,
                            operation_id=str(uuid4()),
                            expected_revision=revision,
                            recipe_id=item["recipe_id"],
                            acceptance_id=acceptance["id"],
                        )
                    )["data"]["calculation"]
                    decide(
                        "save_menu_decision",
                        recipe_id=item["recipe_id"],
                        acceptance_id=acceptance["id"],
                        calculation_id=calculation["id"],
                        scenario_id=choice["scenario_id"],
                        custom_price=choice["custom_price"],
                    )
        return decide

    return prepare


@pytest.fixture
def pricing_workspace(tmp_path, inventory_file, recipe_candidate):
    def create(
        *, total="20.00", purchased="100", consumed="100", servings=2, batches=1, parts=1,
        accept=True, unit="g",
    ):
        book = load_workbook(inventory_file)
        book["Precos"]["B2"] = purchased
        book["Precos"]["C2"] = unit
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
            ingredient_id=stock["id"], quantity=dict(value=consumed, unit=unit)
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
        if not accept:
            return service, workspace, recipe, None, command, database
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
    return dict(
        turn_ref="synthetic-s04-user", statement=statement, captured_at="2026-11-12T12:00:00Z"
    )


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
        operational_context="Fixture de preparo manual em um recipiente.",
        context_source=source,
        category_reviews=[
            dict(
                category=c,
                requirement_keys=[],
                method_version=1,
                source=source,
                not_applicable_reason="Fixture sem requisito nesta categoria.",
            )
            for c in ("EQUIPMENT", "SKILL", "OPERATION")
        ],
    )

    def command(tool, **payload):
        revision = service.get_business_state({"workspace_id": workspace})["revision"]
        return getattr(service, tool)(
            dict(workspace_id=workspace, operation_id=str(uuid4()), expected_revision=revision)
            | payload
        )

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
