"""S16 nas fronteiras públicas, com estado e auditoria sintéticos."""

import json
import sqlite3
from copy import deepcopy
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import AttendanceService, BusinessStateReader
from dona_maria.candidates import CandidateInput
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.planning import BusinessRuleError


@pytest.fixture
def own_recipe(recipe_candidate):
    def human(value):
        if isinstance(value, list):
            return [human(item) for item in value]
        if isinstance(value, dict):
            if value.get("kind") == "WEB":
                return {"kind": "USER_PROVIDED"}
            return {key: human(item) for key, item in value.items()}
        return value

    recipe = human(deepcopy(recipe_candidate))
    recipe["origin"] = {"source": {"kind": "USER_PROVIDED"}}
    return recipe


@pytest.fixture
def local_context(tmp_path, inventory_file):
    database = tmp_path / "context.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "backup.sqlite3")
    return ApprovalService(repository), workspace, database


def state(local, workspace):
    result = BusinessStateReader(local.repository).get_business_state({"workspace_id": workspace})
    assert result["ok"], result
    return result


def propose(local, workspace, candidate, **revision):
    return local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=state(local, workspace)["revision"],
            command=dict(
                kind="register_recipe_candidate", payload=dict(candidate=candidate, **revision)
            ),
        )
    )


def approve(local, workspace, proposal):
    return local.approve(workspace, proposal["id"], proposal["hash"], attest=True)


def test_reported_measurement_keeps_method_context_and_exact_local_approval(
    local_context, own_recipe
):
    local, workspace, database = local_context
    own_recipe["ingredients"][0]["original_measure"]["source"] = {
        "kind": "USER_REPORTED_MEASUREMENT",
        "method": "Pesei em minha balança doméstica.",
        "context": "Arroz cru, recipiente tarado, uma leitura reportada.",
    }
    before = state(local, workspace)
    proposal = propose(local, workspace, own_recipe)
    assert state(local, workspace) == before
    result = approve(local, workspace, proposal)
    assert result["ok"], result
    recipe = result["data"]["candidate"]
    measure = recipe["ingredients"][0]["original_measure"]
    assert (measure["value"], measure["unit_label"]) == ("100", "g")
    assert measure["source"]["method"] == "Pesei em minha balança doméstica."
    assert measure["source"]["context"] == "Arroz cru, recipiente tarado, uma leitura reportada."
    assert measure["source"]["evidence"]["turn_ref"].startswith("local:")
    assert "measured_at" not in measure["source"]
    assert recipe["ingredients"][0]["quantity_source"]["kind"] == "DERIVED"
    reopened = ApprovalService(SQLiteWorkspaceRepository(database))
    assert (
        state(reopened, workspace)["data"]["candidates"][0]
        == state(local, workspace)["data"]["candidates"][0]
    )
    assert approve(reopened, workspace, proposal) == result


def test_partial_adaptation_of_immutable_web_version_keeps_mixed_sources(
    pricing_workspace, tmp_path
):
    reader, workspace, original, _, _, database = pricing_workspace()
    migrate_proposals(reader.repository, tmp_path / "adapt-backup.sqlite3")
    local = ApprovalService(reader.repository)
    candidate = {
        key: deepcopy(value)
        for key, value in original.items()
        if key in CandidateInput.model_fields
    }
    for line in candidate["ingredients"]:
        line.pop("line_id", None)
    candidate["method"] = "Misture manualmente e divida, sem aquecer."
    candidate["method_source"] = {"kind": "USER_PROVIDED"}
    candidate["origin"] = {
        "source": {"kind": "USER_PROVIDED"},
        "derived_from": {"recipe_id": original["id"], "version": 1},
    }
    proposal = propose(
        local, workspace, candidate, recipe_id=original["id"], expected_recipe_version=1
    )
    result = approve(local, workspace, proposal)
    assert result["ok"], result
    adapted = result["data"]["candidate"]
    assert adapted["method_source"]["kind"] == "USER_PROVIDED"
    assert adapted["yield_per_batch"] == original["yield_per_batch"]
    assert (
        adapted["ingredients"][0]["original_measure"]
        == original["ingredients"][0]["original_measure"]
    )
    assert adapted["context_source"] == original["context_source"]
    assert adapted["category_status"] == dict.fromkeys(
        ("EQUIPMENT", "SKILL", "OPERATION"), "UNREVIEWED"
    )
    assert result["data"]["invalidated_decisions"]
    assert all(
        a["validity"] == "INVALIDATED" for a in state(local, workspace)["data"]["acceptances"]
    )
    assert state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)["ok"]
    assert approve(local, workspace, proposal) == result


def test_bootstrap_modes_use_separate_databases_and_cannot_be_promoted(tmp_path, inventory_file):
    real_db, simulated_db = tmp_path / "real.sqlite3", tmp_path / "simulation.sqlite3"
    real = bootstrap_workspace(
        real_db, inventory_file, allowed_directory=tmp_path, context_mode="REAL"
    )
    simulated = bootstrap_workspace(
        simulated_db, inventory_file, allowed_directory=tmp_path, context_mode="SIMULATION"
    )
    for database, created, mode in (
        (real_db, real, "REAL"),
        (simulated_db, simulated, "SIMULATION"),
    ):
        reader = BusinessStateReader(SQLiteWorkspaceRepository(database))
        current = reader.get_business_state({"workspace_id": created["workspace_id"]})
        assert current["data"]["context_mode"] == mode
        assert current["data"]["depends_on_simulation"] is False
        assert current["data"]["hypothetical"] is (mode == "SIMULATION")
        other = simulated if mode == "REAL" else real
        assert not reader.get_business_state({"workspace_id": other["workspace_id"]})["ok"]
        before = database.read_bytes()
        with pytest.raises((ValueError, BusinessRuleError)):
            bootstrap_workspace(
                database,
                inventory_file,
                allowed_directory=tmp_path,
                context_mode="SIMULATION" if mode == "REAL" else "REAL",
            )
        assert database.read_bytes() == before
    with sqlite3.connect(simulated_db) as db:
        document = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        document["context_mode"] = "REAL"
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(document),))
    assert not BusinessStateReader(SQLiteWorkspaceRepository(simulated_db)).get_business_state(
        {"workspace_id": simulated["workspace_id"]}
    )["ok"]


def decide(local, workspace, kind, **payload):
    proposal = local.propose(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=state(local, workspace)["revision"],
            command=dict(kind=kind, payload=payload),
        )
    )
    return approve(local, workspace, proposal)


def test_simulation_keeps_hypothetical_decisions_after_restart_and_all_guards(
    tmp_path, inventory_file, own_recipe
):
    database = tmp_path / "fiction.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode="SIMULATION"
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "fiction-backup.sqlite3")
    local = ApprovalService(repository)
    reader = BusinessStateReader(repository)
    source = {"kind": "USER_SIMULATION", "scenario": "Exemplo fictício, sem produção real."}
    own_recipe.update(
        origin=dict(source=source),
        sources=[source],
        method_source=source,
        operational_context="Uma tigela, um lote manual.",
        context_source=source,
        context_gap=None,
        yield_gap=None,
        yield_per_batch=dict(servings_per_batch=2, sale_unit_label="porção", source=source),
        category_reviews=[
            dict(
                category=c,
                requirement_keys=[],
                method_version=1,
                not_applicable_reason="Sem requisito nesta fixture.",
                source=source,
            )
            for c in ("EQUIPMENT", "SKILL", "OPERATION")
        ],
    )
    line = own_recipe["ingredients"][0]
    line["ingredient_id"] = reader.get_inventory_snapshot({"workspace_id": workspace})["data"][
        "items"
    ][0]["id"]
    line["source"] = source
    line["original_measure"]["source"] = source
    registered = approve(local, workspace, propose(local, workspace, own_recipe))
    assert registered["ok"], registered
    recipe = registered["data"]["candidate"]
    with pytest.raises(BusinessRuleError):
        decide(
            local,
            workspace,
            "accept_recipe",
            recipe_id=recipe["id"],
            plan_item_id=str(uuid4()),
            evaluation_id="0" * 64,
        )
    decide(
        local, workspace, "record_recipe_feedback", recipe_id=recipe["id"], feedback="INTERESTED"
    )
    decide(
        local,
        workspace,
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=1, batches=1, position=0)],
    )
    evaluation = state(local, workspace)["data"]["evaluation"]
    assert evaluation["data_complete"] is True
    assert evaluation["depends_on_simulation"] is True
    accepted = decide(
        local,
        workspace,
        "accept_recipe",
        recipe_id=recipe["id"],
        plan_item_id=state(local, workspace)["data"]["plan"]["items"][0]["plan_item_id"],
        evaluation_id=evaluation["evaluation_id"],
    )
    assert accepted["ok"], accepted
    acceptance = accepted["data"]["acceptance"]
    calculated = reader.calculate_pricing_scenarios(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=state(local, workspace)["revision"],
            recipe_id=recipe["id"],
            acceptance_id=acceptance["id"],
        )
    )
    assert calculated["ok"], calculated
    calculation = calculated["data"]["calculation"]
    assert calculation["minimum"]["price"] == "0.28"
    with pytest.raises(BusinessRuleError):
        decide(
            local,
            workspace,
            "save_menu_decision",
            recipe_id=recipe["id"],
            acceptance_id=acceptance["id"],
            calculation_id=calculation["id"],
            custom_price="0.01",
        )
    saved = decide(
        local,
        workspace,
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=calculation["id"],
        scenario_id="M20",
    )
    assert saved["ok"], saved
    reopened = state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)["data"]
    assert reopened["menu"][0]["hypothetical"] is True
    assert reopened["pricing_calculations"][0]["depends_on_simulation"] is True
    assert reopened["context_mode"] == "SIMULATION"
    assert reopened["budget_remaining"] == "80.00"
    decide(local, workspace, "set_production_plan", items=[])
    historical = state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)["data"]
    assert historical["evaluation"]["depends_on_simulation"] is False
    assert historical["pricing_calculations"][0]["depends_on_simulation"] is True
    assert historical["menu_decisions"][0]["depends_on_simulation"] is True
    with sqlite3.connect(database) as db:
        content = json.loads(db.execute("SELECT state_json FROM workspaces").fetchone()[0])
        content["decision_simulation_dependencies"][calculation["id"]] = False
        db.execute("UPDATE workspaces SET state_json=?", (json.dumps(content),))
    assert not BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )["ok"]


def adaptation_input(original, recipe):
    candidate = deepcopy(recipe)
    candidate["origin"] = dict(
        source={"kind": "USER_PROVIDED"},
        derived_from=dict(recipe_id=original["id"], version=original["version"]),
    )
    return candidate


def test_new_adapted_recipe_preserves_human_sources_and_transitive_measurement(
    local_context, own_recipe
):
    local, workspace, _ = local_context
    first_proposal = propose(local, workspace, own_recipe)
    first = approve(local, workspace, first_proposal)
    original = first["data"]["candidate"]
    changed = adaptation_input(original, own_recipe)
    measure = changed["ingredients"][0]["original_measure"]
    measure.update(value="200", raw_text="200 g de arroz")
    measure["source"] = dict(
        kind="USER_REPORTED_MEASUREMENT",
        method="Duas leituras de 100 g somadas.",
        context="Arroz cru em recipiente tarado.",
        inputs=original["ingredients"][0]["quantity_source"]["inputs"],
    )
    changed["ingredients"][0]["quantity"]["value"] = "200"
    second = approve(local, workspace, propose(local, workspace, changed))
    assert second["ok"], second
    adapted = second["data"]["candidate"]
    assert adapted["id"] != original["id"]
    assert adapted["method_source"] == original["method_source"]
    derived = adapted["ingredients"][0]["quantity_source"]
    assert original["ingredients"][0]["quantity_source"]["inputs"][0] in derived["inputs"]
    assert adapted["ingredients"][0]["quantity"]["value"] == "200"
    assert state(local, workspace)["ok"]
    assert approve(local, workspace, first_proposal) == first


@pytest.mark.parametrize("reference", ["missing", "future", "self", "foreign"])
def test_invalid_origin_does_not_write_proposal_or_operation(local_context, own_recipe, reference):
    local, workspace, database = local_context
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    candidate = adaptation_input(original, own_recipe)
    origin = candidate["origin"]["derived_from"]
    if reference in {"missing", "foreign"}:
        origin["recipe_id"] = str(uuid4())
    else:
        origin["version"] = 2
    before = database.read_bytes()
    with pytest.raises(BusinessRuleError):
        propose(local, workspace, candidate, recipe_id=original["id"], expected_recipe_version=1)
    assert database.read_bytes() == before


def test_adaptation_cannot_reuse_category_review_for_changed_yield(local_context, own_recipe):
    local, workspace, _ = local_context
    source = {"kind": "USER_PROVIDED"}
    own_recipe.update(
        yield_gap=None,
        yield_per_batch=dict(servings_per_batch=2, sale_unit_label="porção", source=source),
        category_reviews=[
            dict(
                category=c,
                requirement_keys=[],
                method_version=1,
                not_applicable_reason="Fixture sem requisito.",
                source=source,
            )
            for c in ("EQUIPMENT", "SKILL", "OPERATION")
        ],
    )
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    candidate = adaptation_input(original, own_recipe)
    candidate["yield_per_batch"]["servings_per_batch"] = 3
    # A próxima versão não é, por si só, uma nova revisão operacional.
    for review in candidate["category_reviews"]:
        review["method_version"] = 2
    adapted = approve(
        local,
        workspace,
        propose(local, workspace, candidate, recipe_id=original["id"], expected_recipe_version=1),
    )["data"]["candidate"]
    assert set(adapted["category_status"].values()) == {"UNREVIEWED"}


def test_reported_contextual_conversion_is_recomputed_from_attested_inputs(
    local_context, own_recipe
):
    local, workspace, _ = local_context
    reader = BusinessStateReader(local.repository)
    ingredient = reader.get_inventory_snapshot({"workspace_id": workspace})["data"]["items"][0][
        "id"
    ]
    line = own_recipe["ingredients"][0]
    line.update(ingredient_id=ingredient, quantity=None, quantity_gap="Medida doméstica pendente.")
    line["original_measure"].update(value="2", unit_label="xícara", raw_text="2 xícaras")
    recipe = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    converted = decide(
        local,
        workspace,
        "record_ingredient_conversion",
        ingredient_id=ingredient,
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][0]["line_id"],
        scope="RECIPE_MEASURE",
        from_unit="xícara",
        to_unit="g",
        factor="100",
        context="Mesma xícara, arroz cru, rasa.",
        source=dict(
            kind="USER_REPORTED_MEASUREMENT",
            method="Tarei o recipiente e pesei uma xícara rasa.",
            context="Arroz cru, leitura doméstica.",
            inputs=[
                dict(
                    entity="RECIPE",
                    entity_id=recipe["id"],
                    version=1,
                    field="ingredients/0/original_measure/source",
                )
            ],
        ),
    )
    assert converted["ok"], converted
    conversion = converted["data"]["conversion"]
    assert conversion["source"]["kind"] == "USER_REPORTED_MEASUREMENT"
    assert conversion["source"]["method"] == "Tarei o recipiente e pesei uma xícara rasa."
    effective = reader.get_business_state({"workspace_id": workspace})["data"]
    decide(
        local,
        workspace,
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=1, batches=1, position=0)],
    )
    evaluation = state(local, workspace)["data"]["evaluation"]
    assert evaluation["demand"][0]["required"] == "200"
    derived = evaluation["consumption_by_recipe"][0]["ingredients"][0]["quantity_sources"][0]
    assert derived["rule"] == "CONTEXTUAL_CONVERSION"
    assert {reference["entity"] for reference in derived["inputs"]} == {"RECIPE", "CONVERSION"}
    assert effective["ingredient_conversions"][0]["source"] == conversion["source"]


@pytest.mark.parametrize("target", ["missing", "future", "field"])
def test_measurement_inputs_are_resolved_before_proposal_write(local_context, own_recipe, target):
    local, workspace, database = local_context
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    own_recipe["ingredients"][0]["original_measure"]["source"] = dict(
        kind="USER_REPORTED_MEASUREMENT",
        method="Leitura reportada.",
        context="Arroz cru.",
        inputs=[
            dict(
                entity="RECIPE",
                entity_id=str(uuid4()) if target == "missing" else original["id"],
                version=2 if target == "future" else 1,
                field="not-a-field" if target == "field" else "method_source",
            )
        ],
    )
    before = database.read_bytes()
    with pytest.raises(BusinessRuleError):
        propose(local, workspace, own_recipe)
    assert database.read_bytes() == before


def test_partial_input_resolves_unchanged_fields_on_server(local_context, own_recipe):
    local, workspace, _ = local_context
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    candidate = dict(
        origin=dict(
            source={"kind": "USER_PROVIDED"}, derived_from=dict(recipe_id=original["id"], version=1)
        ),
        changes=dict(
            method="Misture e divida manualmente.", method_source={"kind": "USER_PROVIDED"}
        ),
    )
    result = approve(
        local,
        workspace,
        propose(local, workspace, candidate, recipe_id=original["id"], expected_recipe_version=1),
    )
    assert result["ok"], result
    adapted = result["data"]["candidate"]
    assert adapted["method"] == "Misture e divida manualmente."
    assert (
        adapted["ingredients"][0]["original_measure"]
        == original["ingredients"][0]["original_measure"]
    )
    assert adapted["method_source"]["local_event_id"] != original["method_source"]["local_event_id"]


def test_attendance_distinguishes_measurement_and_historical_fields_without_private_data(
    local_context, own_recipe
):
    local, workspace, database = local_context
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    candidate = dict(
        origin=dict(
            source={"kind": "USER_PROVIDED"}, derived_from=dict(recipe_id=original["id"], version=1)
        ),
        changes=dict(
            yield_per_batch=dict(
                servings_per_batch=2,
                sale_unit_label="porção",
                source=dict(
                    kind="USER_REPORTED_MEASUREMENT",
                    method="Contei duas porções iguais.",
                    context="Uma preparação doméstica.",
                ),
            ),
            yield_gap=None,
        ),
    )
    approve(
        local,
        workspace,
        propose(local, workspace, candidate, recipe_id=original["id"], expected_recipe_version=1),
    )
    projected = AttendanceService(database, workspace, "ATTENDANCE").call("get_business_state", {})
    assert projected["ok"], projected
    recipe = projected["data"]["recipes"][0]
    assert projected["data"]["context_mode"] == "REAL"
    assert recipe["adapted_from"] == {"recipe": 1, "version": 1}
    measurement = next(
        origin
        for origin in recipe["information_origins"]
        if origin["field"] == "yield_per_batch/source"
    )
    assert measurement["method"] == "Contei duas porções iguais."
    assert measurement["kind"] == "USER_REPORTED_MEASUREMENT"
    for private in (workspace, str(database), "local_event_id", "information_ref", "turn_ref"):
        assert private not in json.dumps(projected)


@pytest.mark.parametrize("mode", ["REAL", "SIMULATION"])
def test_local_approval_failure_rolls_back_state_operations_and_audit(
    tmp_path, inventory_file, own_recipe, mode
):
    database = tmp_path / "rollback.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode=mode
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "rollback-backup.sqlite3")
    local = ApprovalService(repository)
    proposal = propose(local, workspace, own_recipe)
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TRIGGER fail_approval BEFORE INSERT ON decisions "
            "WHEN NEW.kind='LOCAL_APPROVAL' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    before = database.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        approve(local, workspace, proposal)
    assert database.read_bytes() == before
    assert state(local, workspace)["data"]["candidates"] == []
    assert local.inspect(workspace, proposal["id"])["status"] == "PENDING"


def test_origin_and_measurement_cannot_reference_another_workspace(
    local_context, own_recipe, inventory_file, tmp_path
):
    local, workspace, database = local_context
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    other = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    foreign = adaptation_input(original, own_recipe)
    before = database.read_bytes()
    with pytest.raises(BusinessRuleError):
        propose(local, other, foreign)
    foreign.pop("origin")
    foreign["origin"] = {"source": {"kind": "USER_PROVIDED"}}
    foreign["method_source"] = dict(
        kind="USER_REPORTED_MEASUREMENT",
        method="Relato.",
        context="Teste.",
        inputs=[dict(entity="RECIPE", entity_id=original["id"], version=1, field="method_source")],
    )
    with pytest.raises(BusinessRuleError):
        propose(local, other, foreign)
    assert database.read_bytes() == before


def test_fictional_dependency_propagates_through_reported_measurement(
    tmp_path, inventory_file, own_recipe
):
    database = tmp_path / "transitive-simulation.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode="SIMULATION"
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "transitive-backup.sqlite3")
    local = ApprovalService(repository)
    ingredient = BusinessStateReader(repository).get_inventory_snapshot(
        {"workspace_id": workspace}
    )["data"]["items"][0]["id"]
    own_recipe["ingredients"][0]["ingredient_id"] = ingredient
    own_recipe["ingredients"][0]["original_measure"]["source"] = dict(
        kind="USER_SIMULATION", scenario="Hipótese de 100 g."
    )
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    candidate = adaptation_input(original, own_recipe)
    candidate["ingredients"][0]["original_measure"].update(
        value="200",
        raw_text="200 g",
        source=dict(
            kind="USER_REPORTED_MEASUREMENT",
            method="Dobro da entrada anterior, relato humano.",
            context="Referência fictícia mantida.",
            inputs=original["ingredients"][0]["quantity_source"]["inputs"],
        ),
    )
    candidate["ingredients"][0]["quantity"]["value"] = "200"
    adapted = approve(local, workspace, propose(local, workspace, candidate))["data"]["candidate"]
    assert (
        adapted["ingredients"][0]["original_measure"]["source"]["kind"]
        == "USER_REPORTED_MEASUREMENT"
    )
    assert adapted["ingredients"][0]["quantity_source"]["depends_on_simulation"] is True
    decide(
        local,
        workspace,
        "set_production_plan",
        items=[dict(recipe_id=adapted["id"], recipe_version=1, batches=1, position=0)],
    )
    current = state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)["data"]
    assert current["evaluation"]["depends_on_simulation"] is True
    assert current["evaluation"]["data_complete"] is False
    assert current["evaluation"]["hypothetical"] is True
    candidate["ingredients"][0].update(quantity=None, quantity_gap="Normalização ainda pendente.")
    incomplete = approve(local, workspace, propose(local, workspace, candidate))["data"][
        "candidate"
    ]
    assert incomplete["complete"] is False
    assert incomplete["depends_on_simulation"] is True


def test_reported_package_conversion_has_exact_provenance_after_reopen(local_context):
    local, workspace, database = local_context
    reader = BusinessStateReader(local.repository)
    ingredient = reader.get_inventory_snapshot({"workspace_id": workspace})["data"]["items"][0][
        "id"
    ]
    result = decide(
        local,
        workspace,
        "record_ingredient_conversion",
        ingredient_id=ingredient,
        scope="HISTORICAL_PACKAGE",
        from_unit="g",
        to_unit="g",
        factor="1",
        context="Pacote reportado em gramas.",
        source=dict(
            kind="USER_REPORTED_MEASUREMENT",
            method="Conferi a massa reportada do pacote.",
            context="Compra histórica sintética.",
        ),
    )
    assert result["ok"], result
    current = state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)
    conversion = current["data"]["ingredient_conversions"][0]
    assert conversion["source"]["information_ref"]["field"] == "conversion"


@pytest.mark.parametrize("field", ["operational_context", "requirements"])
def test_new_adaptation_revalidates_changed_operational_dependencies(
    local_context, own_recipe, field
):
    local, workspace, _ = local_context
    source = {"kind": "USER_PROVIDED"}
    own_recipe.update(
        operational_context="Um lote em uma tigela.",
        context_source=source,
        context_gap=None,
        requirements=[
            dict(
                category="OPERATION",
                key="bancada",
                condition="EXPLICIT_CONDITION",
                value=True,
                reason="Condição desta fixture.",
                source=source,
            )
        ],
        category_reviews=[
            dict(
                category=c,
                requirement_keys=["bancada"] if c == "OPERATION" else [],
                method_version=1,
                not_applicable_reason=None if c == "OPERATION" else "Não necessário nesta fixture.",
                source=source,
            )
            for c in ("EQUIPMENT", "SKILL", "OPERATION")
        ],
    )
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    candidate = adaptation_input(original, own_recipe)
    if field == "operational_context":
        candidate[field] = "Dois lotes simultâneos, outro recipiente."
    else:
        candidate[field][0]["value"] = False
    adapted = approve(local, workspace, propose(local, workspace, candidate))["data"]["candidate"]
    assert set(adapted["category_status"].values()) == {"UNREVIEWED"}


def test_new_web_conversion_cannot_bypass_registered_source_channel(
    local_context, recipe_candidate
):
    local, workspace, database = local_context
    ingredient = BusinessStateReader(local.repository).get_inventory_snapshot(
        {"workspace_id": workspace}
    )["data"]["items"][0]["id"]
    before = database.read_bytes()
    with pytest.raises(BusinessRuleError):
        decide(
            local,
            workspace,
            "record_ingredient_conversion",
            ingredient_id=ingredient,
            scope="HISTORICAL_PACKAGE",
            from_unit="g",
            to_unit="g",
            factor="1",
            context="Teste.",
            source=recipe_candidate["sources"][0],
        )
    assert database.read_bytes() == before


def test_bound_partial_input_preserves_omitted_fields(local_context, own_recipe):
    local, workspace, _ = local_context
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    result = local.propose_bound(
        workspace,
        dict(
            operation_id=str(uuid4()),
            command=dict(
                kind="register_recipe_candidate",
                payload=dict(
                    recipe_id=1,
                    candidate=dict(
                        origin=dict(
                            source={"kind": "USER_PROVIDED"},
                            derived_from=dict(recipe_id=1, version=1),
                        ),
                        changes=dict(
                            method="Outro método reportado.",
                            method_source={"kind": "USER_PROVIDED"},
                        ),
                    ),
                ),
            ),
        ),
    )
    assert result["status"] == "PENDING"
    adapted = approve(local, workspace, local.list(workspace)[-1])["data"]["candidate"]
    assert adapted["title"] == original["title"]


def test_new_reported_measurement_can_attest_the_same_numeric_value(local_context, own_recipe):
    local, workspace, _ = local_context
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    candidate = adaptation_input(original, own_recipe)
    candidate["ingredients"][0]["original_measure"]["source"] = dict(
        kind="USER_REPORTED_MEASUREMENT",
        method="Pesei os mesmos 100 g antes declarados.",
        context="Arroz cru em recipiente tarado.",
    )
    result = approve(
        local,
        workspace,
        propose(local, workspace, candidate, recipe_id=original["id"], expected_recipe_version=1),
    )
    assert (
        result["data"]["candidate"]["ingredients"][0]["original_measure"]["source"]["kind"]
        == "USER_REPORTED_MEASUREMENT"
    )


def test_simulation_preserves_aggregate_budget_guard(
    tmp_path, inventory_file, own_recipe, recipe_candidate
):
    from openpyxl import load_workbook

    book = load_workbook(inventory_file)
    book["Despensa"]["B2"] = 0
    book.save(inventory_file)
    book.close()
    database = tmp_path / "budget-simulation.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode="SIMULATION"
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    reader = BusinessStateReader(repository)
    ingredient = reader.get_inventory_snapshot({"workspace_id": workspace})["data"]["items"][0][
        "id"
    ]
    # Fixture histórica de cotação na API local anterior à migração S14.
    quote = reader.register_complement_quote(
        dict(
            workspace_id=workspace,
            operation_id=str(uuid4()),
            expected_revision=0,
            quote=dict(
                ingredient_id=ingredient,
                description="Oferta sintética de arroz.",
                package_quantity=dict(value="1000", unit="g"),
                package_price="99.00",
                purchase_extra_total="0.00",
                extra_conditions="Retirada gratuita",
                availability="AVAILABLE",
                availability_context="Disponível hoje",
                supplier="Fornecedor sintético",
                source=recipe_candidate["sources"][0],
            ),
        )
    )["data"]["quote"]
    migrate_proposals(repository, tmp_path / "budget-backup.sqlite3")
    local = ApprovalService(repository)
    source = {"kind": "USER_PROVIDED"}
    own_recipe["ingredients"][0]["ingredient_id"] = ingredient
    own_recipe.update(
        yield_gap=None,
        yield_per_batch=dict(servings_per_batch=2, sale_unit_label="porção", source=source),
        operational_context="Um lote manual em uma tigela.",
        context_source=source,
        context_gap=None,
        category_reviews=[
            dict(
                category=c,
                requirement_keys=[],
                method_version=1,
                not_applicable_reason="Sem condição adicional nesta fixture.",
                source=source,
            )
            for c in ("EQUIPMENT", "SKILL", "OPERATION")
        ],
    )
    recipe = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    decide(
        local, workspace, "record_recipe_feedback", recipe_id=recipe["id"], feedback="INTERESTED"
    )
    decide(
        local,
        workspace,
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=1, batches=1, position=0)],
        quote_selections=[dict(ingredient_id=ingredient, quote_id=quote["id"], quote_version=1)],
    )
    decide(
        local,
        workspace,
        "confirm_complement_quote",
        quote_id=quote["id"],
        quote_version=1,
        scope={
            key: quote[key]
            for key in (
                "package_quantity",
                "package_price",
                "purchase_extra_total",
                "extra_conditions",
                "availability_context",
                "supplier",
            )
        }
        | {"packages": 1},
    )
    current = state(local, workspace)["data"]
    assert current["evaluation"]["purchase_status"] == "OVER_BUDGET"
    assert current["evaluation"]["remaining_budget"] == "-19.00"
    with pytest.raises(BusinessRuleError):
        decide(
            local,
            workspace,
            "accept_recipe",
            recipe_id=recipe["id"],
            plan_item_id=current["plan"]["items"][0]["plan_item_id"],
            evaluation_id=current["evaluation"]["evaluation_id"],
        )
    # A proposta pode existir; nenhuma decisão ou operação de aceite foi comprometida.
    assert state(local, workspace)["data"]["acceptances"] == []
    with sqlite3.connect(database) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM operations WHERE tool='accept_recipe'").fetchone()[0]
            == 0
        )


def test_conversion_chain_keeps_fictional_origin_and_recomputes_quantity(
    tmp_path, inventory_file, own_recipe
):
    database = tmp_path / "conversion-chain.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode="SIMULATION"
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "conversion-backup.sqlite3")
    local = ApprovalService(repository)
    ingredient = BusinessStateReader(repository).get_inventory_snapshot(
        {"workspace_id": workspace}
    )["data"]["items"][0]["id"]
    line = own_recipe["ingredients"][0]
    line.update(ingredient_id=ingredient, quantity=None, quantity_gap="Conversão pendente.")
    line["original_measure"].update(value="2", unit_label="xícara", raw_text="2 xícaras")
    recipe = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    payload = dict(
        ingredient_id=ingredient,
        recipe_id=recipe["id"],
        recipe_version=1,
        line_id=recipe["ingredients"][0]["line_id"],
        scope="RECIPE_MEASURE",
        from_unit="xícara",
        to_unit="g",
        factor="100",
        context="Mesmo recipiente e ingrediente.",
        source=dict(kind="USER_SIMULATION", scenario="Equivalência fictícia para demonstração."),
    )
    first = decide(local, workspace, "record_ingredient_conversion", **payload)["data"][
        "conversion"
    ]
    reference = dict(entity="CONVERSION", entity_id=first["id"], version=1, field="conversion")
    payload.update(
        factor="110",
        replaces_conversion_id=first["id"],
        source=dict(
            kind="USER_REPORTED_MEASUREMENT",
            method="Relato de ajuste sobre a entrada anterior.",
            context="Mantém dependência fictícia.",
            inputs=[reference],
        ),
    )
    decide(local, workspace, "record_ingredient_conversion", **payload)
    decide(
        local,
        workspace,
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=1, batches=1, position=0)],
    )
    evaluation = state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)["data"][
        "evaluation"
    ]
    assert evaluation["demand"][0]["required"] == "220"
    assert evaluation["depends_on_simulation"] is True
    derived = evaluation["consumption_by_recipe"][0]["ingredients"][0]["quantity_sources"][0]
    assert reference in derived["inputs"]
    assert derived["depends_on_simulation"] is True


@pytest.mark.parametrize("count", [200, 201])
def test_measurement_reference_collection_limit_is_explicit(local_context, own_recipe, count):
    local, workspace, database = local_context
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    own_recipe["method_source"] = dict(
        kind="USER_REPORTED_MEASUREMENT",
        method="Relato sintético.",
        context="Condições reportadas.",
        inputs=[
            dict(entity="RECIPE", entity_id=original["id"], version=1, field="method_source")
            for _ in range(count)
        ],
    )
    before = database.read_bytes()
    if count == 201:
        with pytest.raises(BusinessRuleError, match="limite"):
            propose(local, workspace, own_recipe)
        assert database.read_bytes() == before
    else:
        result = approve(local, workspace, propose(local, workspace, own_recipe))
        assert result["ok"], result
        assert len(result["data"]["candidate"]["method_source"]["inputs"]) == 200


@settings(
    max_examples=12, database=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(event=st.uuids())
def test_arbitrary_measurement_event_cannot_create_local_authority(
    local_context, own_recipe, event
):
    local, workspace, database = local_context
    candidate = deepcopy(own_recipe)
    candidate["method_source"] = dict(
        kind="USER_REPORTED_MEASUREMENT",
        method="Relato.",
        context="Teste.",
        local_event_id=str(event),
    )
    before = database.read_bytes()
    with pytest.raises(BusinessRuleError):
        propose(local, workspace, candidate)
    assert database.read_bytes() == before
    assert local.list(workspace) == []


def test_simulation_refuses_malformed_operation_without_recreating_database(
    tmp_path, inventory_file
):
    database = tmp_path / "corrupt-operation.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode="SIMULATION"
    )["workspace_id"]
    with sqlite3.connect(database) as db:
        db.execute("UPDATE operations SET result_json='[]'")
    before = database.read_bytes()
    result = BusinessStateReader(SQLiteWorkspaceRepository(database)).get_business_state(
        {"workspace_id": workspace}
    )
    assert result["ok"] is False
    assert result["data"] is None
    assert database.read_bytes() == before


@pytest.mark.parametrize("original_kind", ["USER_PROVIDED", "USER_SIMULATION"])
def test_adaptation_keeps_new_simulation_source_for_unchanged_value(
    tmp_path, inventory_file, own_recipe, original_kind
):
    database = tmp_path / "source-change.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode="SIMULATION"
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "source-backup.sqlite3")
    local = ApprovalService(repository)
    if original_kind == "USER_SIMULATION":
        own_recipe["method_source"] = dict(kind=original_kind, scenario="Cenário anterior.")
    original = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    candidate = dict(
        origin=dict(
            source=dict(kind="USER_PROVIDED"),
            derived_from=dict(recipe_id=original["id"], version=1),
        ),
        changes=dict(method_source=dict(kind="USER_SIMULATION", scenario="Novo cenário.")),
    )
    adapted = approve(
        local,
        workspace,
        propose(local, workspace, candidate, recipe_id=original["id"], expected_recipe_version=1),
    )["data"]["candidate"]
    assert adapted["method"] == original["method"]
    assert adapted["method_source"]["kind"] == "USER_SIMULATION"
    assert adapted["method_source"]["scenario"] == "Novo cenário."
    assert adapted["method_source"]["local_event_id"] != original["method_source"]["local_event_id"]
    assert adapted["depends_on_simulation"] is True
    reopened = state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)["data"]
    assert reopened["candidates"][0]["method_source"] == adapted["method_source"]


@pytest.mark.parametrize("conversion,count", [(False, 200), (True, 199), (True, 200)])
def test_quantity_derivation_keeps_all_distinct_measurement_inputs(
    local_context, own_recipe, conversion, count
):
    local, workspace, database = local_context
    original_input = deepcopy(own_recipe)
    original_input["sources"] = [dict(kind="USER_PROVIDED") for _ in range(count)]
    original = approve(local, workspace, propose(local, workspace, original_input))["data"][
        "candidate"
    ]
    references = [
        dict(entity="RECIPE", entity_id=original["id"], version=1, field=f"sources/{index}")
        for index in range(count)
    ]
    measurement = dict(
        kind="USER_REPORTED_MEASUREMENT",
        method="Medição reportada com entradas distintas.",
        context="Fixture sintética.",
        inputs=references,
    )
    ingredient = BusinessStateReader(local.repository).get_inventory_snapshot(
        {"workspace_id": workspace}
    )["data"]["items"][0]["id"]
    line = own_recipe["ingredients"][0]
    line["ingredient_id"] = ingredient
    if conversion:
        line.update(quantity=None, quantity_gap="Conversão contextual pendente.")
        line["original_measure"].update(value="2", unit_label="xícara", raw_text="2 xícaras")
    else:
        line["original_measure"]["source"] = measurement
    recipe = approve(local, workspace, propose(local, workspace, own_recipe))["data"]["candidate"]
    if conversion:
        decide(
            local,
            workspace,
            "record_ingredient_conversion",
            ingredient_id=ingredient,
            recipe_id=recipe["id"],
            recipe_version=1,
            line_id=recipe["ingredients"][0]["line_id"],
            scope="RECIPE_MEASURE",
            from_unit="xícara",
            to_unit="g",
            factor="100",
            context="Mesma xícara e ingrediente.",
            source=measurement,
        )
    decide(
        local,
        workspace,
        "set_production_plan",
        items=[dict(recipe_id=recipe["id"], recipe_version=1, batches=1, position=0)],
    )
    reopened = state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)["data"]
    derived = reopened["evaluation"]["consumption_by_recipe"][0]["ingredients"][0][
        "quantity_sources"
    ][0]
    assert all(reference in derived["inputs"] for reference in references)
    assert len(derived["inputs"]) == count + (2 if conversion else 1)
    if not conversion:
        adaptation = dict(
            origin=dict(
                source=dict(kind="USER_PROVIDED"),
                derived_from=dict(recipe_id=recipe["id"], version=1),
            ),
            changes=dict(title="Título adaptado, medida preservada"),
        )
        adapted = approve(
            local,
            workspace,
            propose(
                local,
                workspace,
                adaptation,
                recipe_id=recipe["id"],
                expected_recipe_version=1,
            ),
        )["data"]["candidate"]
        assert adapted["ingredients"][0]["quantity_source"]["inputs"] == derived["inputs"]
        assert state(ApprovalService(SQLiteWorkspaceRepository(database)), workspace)["ok"]
