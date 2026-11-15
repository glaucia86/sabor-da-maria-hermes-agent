"""S17: fixtures de rede sintéticas; nenhuma pesquisa real é alegada."""

import json
import sqlite3
import ssl
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest
from conftest import pricing_evidence, synthetic_web_extraction

from dona_maria.approvals import ApprovalService, migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.business_state import AttendanceService, BusinessStateReader
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.planning import BusinessRuleError
from dona_maria.provenance import source_fields
from dona_maria.research import ResearchService, migrate_research


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def research_workspace(tmp_path, inventory_file):
    database = tmp_path / "research.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "v1.sqlite3")
    migrate_research(repository, tmp_path / "v2.sqlite3")
    return AttendanceService(database, workspace, "ATTENDANCE")


@pytest.mark.anyio
async def test_approved_query_is_built_locally_and_observation_survives_restart(research_workspace):
    queries = []

    async def search(query):
        queries.append(query)
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Cozinhe."}]

    binding = research_workspace
    reader = BusinessStateReader(SQLiteWorkspaceRepository(binding.database))
    before = reader.get_business_state({"workspace_id": binding.workspace_id})
    service = ResearchService(binding, {"arroz": "arroz"}, search=search)
    request = {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    result = await service.call("search_culinary_sources", request)
    assert result["ok"], result
    assert queries == ["receita arroz"]
    assert result["data"]["query"] == "receita arroz"
    assert result["data"]["provider"] == "controlled-fixture"
    observation = result["data"]["results"][0]
    assert observation["status"] == "SEARCHED"
    assert datetime.fromisoformat(observation["observed_at"]).tzinfo == UTC
    assert observation["research_result_id"]
    restarted = ResearchService(binding, {"arroz": "arroz"}, search=search)
    assert restarted.inspect_result(observation["research_result_id"]) == observation
    refreshed = await restarted.call("search_culinary_sources", request)
    assert refreshed["ok"]
    assert (
        refreshed["data"]["results"][0]["research_result_id"] != observation["research_result_id"]
    )
    assert queries == ["receita arroz", "receita arroz"]
    assert reader.get_business_state({"workspace_id": binding.workspace_id}) == before


@pytest.mark.anyio
@pytest.mark.parametrize(
    "arguments",
    [
        {"purpose": "RECIPE", "public_term_ids": ["segredo"]},
        {"purpose": "RECIPE", "public_term_ids": ["arroz"], "query": "CANARY_PRIVATE"},
        {"purpose": "RECIPE", "public_term_ids": ["arroz"], "url": "https://evil.test"},
        {"purpose": "QUOTE", "public_term_ids": ["arroz"], "workspace_id": "CANARY_PRIVATE"},
    ],
)
async def test_unapproved_or_free_query_never_reaches_search(research_workspace, arguments):
    async def forbidden(query):
        pytest.fail("Dados não liberados chegaram à rede")

    service = ResearchService(research_workspace, {"arroz": "arroz"}, search=forbidden)
    result = await service.call("search_culinary_sources", arguments)
    assert not result["ok"]
    assert "CANARY_PRIVATE" not in str(result)


@pytest.mark.anyio
async def test_unsafe_provider_result_is_refused_without_caching(research_workspace):
    calls = []

    async def search(query):
        calls.append(query)
        return [{"url": "http://127.0.0.1/", "title": "Interno", "description": "Dado"}]

    service = ResearchService(research_workspace, {"arroz": "arroz"}, search=search)
    request = {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    result = await service.call("search_culinary_sources", request)
    assert not result["ok"]
    assert not (await service.call("search_culinary_sources", request))["ok"]
    assert len(calls) == 2


@pytest.mark.anyio
async def test_registered_extraction_materializes_exact_web_source_and_replays(research_workspace):
    fetched = []

    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            fetched.append(url)
            return synthetic_web_extraction(url, "100 g de arroz; cozinhe.")

    service = ResearchService(
        research_workspace, {"arroz": "arroz"}, search=search, extractor=Extractor()
    )
    found = await service.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    identifier = found["data"]["results"][0]["research_result_id"]
    extracted = await service.call("extract_culinary_source", {"research_result_id": identifier})
    assert extracted["ok"], extracted
    source = service.materialize_source(identifier, "segment-1", purpose="RECIPE")
    assert source["excerpt"] == "100 g de arroz; cozinhe."
    assert source["url"] == "https://example.org/arroz"
    assert source["kind"] == "WEB" and source["research_result_id"] == identifier
    assert source["content_sha256"] == sha256(b"100 g de arroz; cozinhe.").hexdigest()
    restarted = ResearchService(
        research_workspace, {"arroz": "arroz"}, search=search, extractor=Extractor()
    )
    assert (
        await restarted.call("extract_culinary_source", {"research_result_id": identifier})
        == extracted
    )
    assert fetched == ["https://example.org/arroz"]


@pytest.mark.anyio
async def test_recipe_proposal_uses_only_registered_reference_and_approval_replays(
    research_workspace, recipe_candidate
):
    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            return synthetic_web_extraction(url, "100 g de arroz; cozinhe em água.")

    binding = research_workspace
    service = ResearchService(binding, {"arroz": "arroz"}, search=search, extractor=Extractor())
    found = await service.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    identifier = found["data"]["results"][0]["research_result_id"]
    assert (await service.call("extract_culinary_source", {"research_result_id": identifier}))["ok"]
    ref = {"kind": "WEB", "research_result_id": identifier, "segment": "segment-1"}

    def replace(value):
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            return (
                dict(ref)
                if value.get("kind") == "WEB"
                else {k: replace(v) for k, v in value.items()}
            )
        return value

    local = ApprovalService(SQLiteWorkspaceRepository(binding.database))
    before = local.repository.load(binding.workspace_id)
    arguments = {
        "operation_id": str(uuid4()),
        "command": {
            "kind": "register_recipe_candidate",
            "payload": {"candidate": replace(recipe_candidate)},
        },
    }
    local.propose_bound(binding.workspace_id, arguments)
    assert local.repository.load(binding.workspace_id) == before
    proposal = local.list(binding.workspace_id)[-1]
    approved = local.approve(binding.workspace_id, proposal["id"], proposal["hash"], attest=True)
    assert approved["ok"]
    source = approved["data"]["candidate"]["method_source"]
    assert source == service.materialize_source(identifier, "segment-1", purpose="RECIPE")
    restarted = ApprovalService(SQLiteWorkspaceRepository(binding.database))
    assert (
        restarted.approve(binding.workspace_id, proposal["id"], proposal["hash"], attest=True)[
            "data"
        ]
        == approved["data"]
    )
    public = AttendanceService(binding.database, binding.workspace_id, "ATTENDANCE").call(
        "get_business_state", {}
    )
    assert public["ok"]
    assert "Pesquisa web registrada" in public["data"]["recipes"][0]["origin"]
    assert public["data"]["recipes"][0]["sources"][0]["url"] == source["url"]
    assert identifier not in str(public)


@pytest.mark.anyio
async def test_large_complete_text_keeps_segment_order_and_hash_after_restart(research_workspace):
    text = "".join(chr(65 + i) * 4000 for i in range(16)) + "Z" * 1536

    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            return synthetic_web_extraction(url, text)

    service = ResearchService(
        research_workspace, {"arroz": "arroz"}, search=search, extractor=Extractor()
    )
    found = await service.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    identifier = found["data"]["results"][0]["research_result_id"]
    assert (await service.call("extract_culinary_source", {"research_result_id": identifier}))["ok"]
    restarted = ResearchService(
        research_workspace, {"arroz": "arroz"}, search=search, extractor=Extractor()
    )
    source = restarted.materialize_source(identifier, "segment-10", purpose="RECIPE")
    assert source["excerpt"] == "J" * 4000
    assert (
        restarted.materialize_source(identifier, "segment-17", purpose="RECIPE")["excerpt"]
        == "Z" * 1536
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        BusinessRuleError("RESOURCE_LIMIT_EXCEEDED", "Conteúdo excede o limite."),
        BusinessRuleError("SOURCE_INCOMPLETE", "Resposta parcial."),
        BusinessRuleError("DESTINATION_REFUSED", "Destino recusado."),
        TimeoutError("CANARY_PRIVATE"),
        OSError("CANARY_PRIVATE"),
        ssl.SSLError("CANARY_PRIVATE"),
    ],
)
async def test_extraction_refusal_preserves_search_and_business_state(research_workspace, failure):
    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            raise failure

    binding = research_workspace
    reader = BusinessStateReader(SQLiteWorkspaceRepository(binding.database))
    before = reader.get_business_state({"workspace_id": binding.workspace_id})
    service = ResearchService(binding, {"arroz": "arroz"}, search=search, extractor=Extractor())
    query = {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    found = await service.call("search_culinary_sources", query)
    identifier = found["data"]["results"][0]["research_result_id"]
    result = await service.call("extract_culinary_source", {"research_result_id": identifier})
    assert not result["ok"] and "CANARY_PRIVATE" not in str(result)
    assert service.inspect_result(identifier) == found["data"]["results"][0]
    assert reader.get_business_state({"workspace_id": binding.workspace_id}) == before
    with pytest.raises(BusinessRuleError):
        service.materialize_source(identifier, "segment-1", purpose="RECIPE")


@pytest.mark.anyio
async def test_unknown_unextracted_foreign_and_missing_segment_cannot_materialize(
    research_workspace, inventory_file, tmp_path
):
    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            return synthetic_web_extraction(url, "100 g de arroz; cozinhe.")

    binding = research_workspace
    service = ResearchService(binding, {"arroz": "arroz"}, search=search, extractor=Extractor())
    found = await service.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    identifier = found["data"]["results"][0]["research_result_id"]
    with pytest.raises(BusinessRuleError):
        service.materialize_source(identifier, "segment-1", purpose="RECIPE")
    assert not (
        await service.call("extract_culinary_source", {"research_result_id": str(uuid4())})
    )["ok"]
    assert not (
        await service.call(
            "extract_culinary_source",
            {"research_result_id": identifier, "url": "https://evil.test"},
        )
    )["ok"]
    assert (await service.call("extract_culinary_source", {"research_result_id": identifier}))["ok"]
    with pytest.raises(BusinessRuleError):
        service.materialize_source(identifier, "segment-2", purpose="RECIPE")
    with pytest.raises(BusinessRuleError):
        service.materialize_source(identifier, "segment-1", purpose="QUOTE")
    foreign = bootstrap_workspace(binding.database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    assert foreign != binding.workspace_id
    other = ResearchService(
        AttendanceService(binding.database, foreign, "ATTENDANCE"),
        {"arroz": "arroz"},
        search=search,
        extractor=Extractor(),
    )
    result = await other.call("extract_culinary_source", {"research_result_id": identifier})
    assert not result["ok"]
    with pytest.raises(BusinessRuleError):
        other.materialize_source(identifier, "segment-1", purpose="RECIPE")


@pytest.mark.anyio
async def test_forged_receipt_cannot_create_proposal(research_workspace, recipe_candidate):
    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            return synthetic_web_extraction(url, "100 g de arroz; cozinhe.")

    binding = research_workspace
    service = ResearchService(binding, {"arroz": "arroz"}, search=search, extractor=Extractor())
    found = await service.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    identifier = found["data"]["results"][0]["research_result_id"]
    await service.call("extract_culinary_source", {"research_result_id": identifier})
    local = ApprovalService(SQLiteWorkspaceRepository(binding.database))
    before = local.repository.load(binding.workspace_id)
    for field, value in {
        "url": "https://evil.test/",
        "excerpt": "fabricado",
        "title": "Outro",
        "retrieved_at": "2020-01-01T00:00:00Z",
        "content_sha256": "0" * 64,
    }.items():
        candidate = deepcopy(recipe_candidate)
        candidate["method_source"] = service.materialize_source(
            identifier, "segment-1", purpose="RECIPE"
        )
        candidate["method_source"][field] = value
        with pytest.raises(BusinessRuleError):
            local.propose(
                {
                    "workspace_id": binding.workspace_id,
                    "operation_id": str(uuid4()),
                    "expected_revision": before[0],
                    "command": {
                        "kind": "register_recipe_candidate",
                        "payload": {"candidate": candidate},
                    },
                }
            )
    assert local.list(binding.workspace_id) == []
    assert local.repository.load(binding.workspace_id) == before


@pytest.mark.anyio
async def test_future_or_corrupt_observation_is_refused_without_rewrite(research_workspace):
    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    service = ResearchService(research_workspace, {"arroz": "arroz"}, search=search)
    query = {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    await service.call("search_culinary_sources", query)
    # Corrupção sintética na fronteira de persistência, não uma consulta auxiliar de negócio.
    with sqlite3.connect(research_workspace.database) as db:
        payload = json.loads(
            db.execute("SELECT payload_json FROM research_observations").fetchone()[0]
        )
        payload["version"] = "999"
        encoded = json.dumps(payload)
        db.execute("UPDATE research_observations SET payload_json=?", (encoded,))
    with pytest.raises(sqlite3.DatabaseError):
        service.inspect_result(payload["results"][0]["research_result_id"])
    with sqlite3.connect(research_workspace.database) as db:
        assert db.execute("SELECT payload_json FROM research_observations").fetchone()[0] == encoded


@pytest.mark.anyio
async def test_external_typed_exception_is_not_an_authority_to_expose_private_error(
    research_workspace,
):
    async def search(query):
        raise BusinessRuleError("CANARY_CODE", "CANARY_PRIVATE", details={"path": "CANARY_PATH"})

    service = ResearchService(research_workspace, {"arroz": "arroz"}, search=search)
    result = await service.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    assert not result["ok"]
    assert "CANARY" not in str(result)


@pytest.mark.anyio
async def test_quote_from_registered_offer_remains_unconfirmed_after_local_registration(
    research_workspace,
):
    async def search(query):
        assert query == "oferta arroz"
        return [{"url": "https://example.org/oferta", "title": "Oferta", "description": "Arroz"}]

    class Extractor:
        async def extract(self, url):
            return synthetic_web_extraction(url, "Arroz 1 kg por R$ 5,00; encargos não informados.")

    binding = research_workspace
    service = ResearchService(binding, {"arroz": "arroz"}, search=search, extractor=Extractor())
    found = await service.call(
        "search_culinary_sources", {"purpose": "QUOTE", "public_term_ids": ["arroz"]}
    )
    identifier = found["data"]["results"][0]["research_result_id"]
    assert (await service.call("extract_culinary_source", {"research_result_id": identifier}))["ok"]
    request = {
        "operation_id": str(uuid4()),
        "command": {
            "kind": "register_complement_quote",
            "payload": {
                "quote": {
                    "ingredient_id": 1,
                    "description": "Arroz",
                    "supplier": "Fornecedor sintético",
                    "package_quantity": {"value": "1000", "unit": "g"},
                    "package_price": "5.00",
                    "purchase_extra_total_gap": "Fonte não informa encargos",
                    "availability": "UNKNOWN",
                    "availability_context": "Fonte não confirma estoque atual",
                    "source": {
                        "kind": "WEB",
                        "research_result_id": identifier,
                        "segment": "segment-1",
                    },
                }
            },
        },
    }
    assert binding.call("propose_user_change", request)["ok"]
    local = ApprovalService(SQLiteWorkspaceRepository(binding.database))
    proposal = local.list(binding.workspace_id)[-1]
    result = local.approve(binding.workspace_id, proposal["id"], proposal["hash"], attest=True)
    assert result["ok"], result
    loaded = local.repository.load(binding.workspace_id)[1]
    assert len(loaded.complement_quotes) == 1 and loaded.quote_confirmations == []
    assert loaded.complement_quotes[0].source.model_dump(mode="json") == service.materialize_source(
        identifier, "segment-1", purpose="QUOTE"
    )


@pytest.mark.anyio
async def test_a_new_search_can_observe_offer_after_an_empty_result(research_workspace):
    searches = []

    async def search(query):
        searches.append(query)
        return (
            []
            if len(searches) == 1
            else [
                {
                    "url": "https://example.org/oferta",
                    "title": "Oferta nova",
                    "description": "Arroz",
                }
            ]
        )

    service = ResearchService(research_workspace, {"arroz": "arroz"}, search=search)
    request = {"purpose": "QUOTE", "public_term_ids": ["arroz"]}
    assert (await service.call("search_culinary_sources", request))["data"]["results"] == []
    second = await service.call("search_culinary_sources", request)
    assert len(second["data"]["results"]) == 1
    assert searches == ["oferta arroz", "oferta arroz"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad",
    [
        {"complete": False},
        {"decoded_bytes": 1024 * 1024 + 1},
        {"received_bytes": 1024 * 1024 + 1},
        {"destinations": []},
    ],
)
async def test_incomplete_transport_record_never_acquires_trusted_web_origin(
    research_workspace, bad
):
    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            return {
                "url": url,
                "text": "Arroz",
                "content_sha256": sha256(b"Arroz").hexdigest(),
                "complete": True,
                "received_bytes": 5,
                "decoded_bytes": 5,
                "destinations": [
                    {"url": url, "hostname": "example.org", "address": "93.184.216.34", "port": 443}
                ],
            } | bad

    service = ResearchService(
        research_workspace, {"arroz": "arroz"}, search=search, extractor=Extractor()
    )
    found = await service.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    before = found["data"]["results"][0]
    identifier = before["research_result_id"]
    assert not (await service.call("extract_culinary_source", {"research_result_id": identifier}))[
        "ok"
    ]
    assert service.inspect_result(identifier) == before
    with pytest.raises(BusinessRuleError):
        service.materialize_source(identifier, "segment-1", purpose="RECIPE")


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["title", "provider", "query"])
@pytest.mark.parametrize("invalid_value", [None, "", 123])
async def test_incomplete_persisted_metadata_is_refused_even_with_matching_document_hash(
    research_workspace, field, invalid_value
):
    from dona_maria.planning import fingerprint
    from dona_maria.research import ADAPTER_VERSION

    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            return synthetic_web_extraction(url, "100 g de arroz; cozinhe.")

    service = ResearchService(
        research_workspace, {"arroz": "arroz"}, search=search, extractor=Extractor()
    )
    found = await service.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    identifier = found["data"]["results"][0]["research_result_id"]
    assert (await service.call("extract_culinary_source", {"research_result_id": identifier}))["ok"]
    with sqlite3.connect(research_workspace.database) as db:
        payload = json.loads(
            db.execute("SELECT payload_json FROM research_observations").fetchone()[0]
        )
        metadata = payload["results"][0] if field == "title" else payload
        if invalid_value is None:
            del metadata[field]
        else:
            metadata[field] = invalid_value
        encoded = json.dumps(payload)
        db.execute(
            "UPDATE research_observations SET payload_json=?, receipt_hash=?, query_hash=?",
            (
                encoded,
                fingerprint(payload),
                fingerprint(
                    [
                        ADAPTER_VERSION,
                        payload["purpose"],
                        payload.get("query"),
                        payload["observation_id"],
                    ]
                ),
            ),
        )
    with pytest.raises(sqlite3.DatabaseError):
        service.inspect_result(identifier)
    with pytest.raises(sqlite3.DatabaseError):
        service.materialize_source(identifier, "segment-1", purpose="RECIPE")
    with sqlite3.connect(research_workspace.database) as db:
        assert db.execute("SELECT payload_json FROM research_observations").fetchone()[0] == encoded


@pytest.mark.parametrize("revise_existing", [False, True])
def test_research_migration_preserves_adaptation_of_historical_legacy_web_recipe(
    pricing_workspace, recipe_candidate, tmp_path, revise_existing
):
    recipe_candidate["method_source"] = recipe_candidate["method_source"] | {
        "title": "Método histórico distinto",
    }
    reader, workspace, original, _, _, database = pricing_workspace()
    migrate_proposals(reader.repository, tmp_path / "adaptation-v1.sqlite3")
    local = ApprovalService(reader.repository)
    changed = local.propose(
        {
            "workspace_id": workspace,
            "operation_id": str(uuid4()),
            "expected_revision": reader.repository.load(workspace)[0],
            "command": {
                "kind": "register_recipe_candidate",
                "payload": {
                    "recipe_id": original["id"],
                    "expected_recipe_version": 1,
                    "candidate": {
                        "origin": {
                            "source": {"kind": "USER_PROVIDED"},
                            "derived_from": {"recipe_id": original["id"], "version": 1},
                        },
                        "changes": {
                            "method": "Método substituído pela cozinheira na versão dois.",
                            "method_source": {"kind": "USER_PROVIDED"},
                        },
                    },
                },
            },
        }
    )
    assert local.approve(workspace, changed["id"], changed["hash"], attest=True)["ok"]
    migrate_research(reader.repository, tmp_path / "adaptation-v2.sqlite3")
    binding = AttendanceService(database, workspace, "ATTENDANCE")
    before = reader.repository.load(workspace)
    proposed = binding.call(
        "propose_user_change",
        {
            "operation_id": str(uuid4()),
            "command": {
                "kind": "register_recipe_candidate",
                "payload": {
                    **({"recipe_id": 1} if revise_existing else {}),
                    "candidate": {
                        "origin": {
                            "source": {"kind": "USER_PROVIDED"},
                            "derived_from": {"recipe_id": 1, "version": 1},
                        },
                        "changes": {"title": "Outra candidata da mesma receita histórica"},
                    },
                },
            },
        },
    )
    assert proposed["ok"], proposed
    assert reader.repository.load(workspace) == before
    proposal = local.list(workspace)[-1]
    applied = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
    assert applied["ok"], applied
    adapted = applied["data"]["candidate"]
    assert (adapted["id"] == original["id"]) is revise_existing
    assert adapted["sources"] == original["sources"]
    assert adapted["method_source"] == original["method_source"]
    assert "research_result_id" not in adapted["method_source"]
    assert adapted["ingredients"][0]["quantity_source"]["kind"] == "DERIVED"
    reopened = ApprovalService(SQLiteWorkspaceRepository(database))
    after = reopened.repository.load(workspace)
    assert reopened.approve(workspace, proposal["id"], proposal["hash"], attest=True) == applied
    assert reopened.repository.load(workspace) == after
    if not revise_existing:
        assert after[1].candidates[0] == before[1].candidates[0]


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["REAL", "SIMULATION"])
async def test_registered_web_adaptation_keeps_reported_measurement_and_context(
    tmp_path, inventory_file, recipe_candidate, mode
):
    database = tmp_path / "mixed-context.sqlite3"
    workspace = bootstrap_workspace(
        database, inventory_file, allowed_directory=tmp_path, context_mode=mode
    )["workspace_id"]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "mixed-v1.sqlite3")
    migrate_research(repository, tmp_path / "mixed-v2.sqlite3")
    binding = AttendanceService(database, workspace, "ATTENDANCE")

    async def search(query):
        return [{"url": "https://example.org/arroz", "title": "Arroz", "description": "Receita"}]

    class Extractor:
        async def extract(self, url):
            return synthetic_web_extraction(url, "100 g de arroz; cozinhe em água.")

    research = ResearchService(binding, {"arroz": "arroz"}, search=search, extractor=Extractor())
    found = await research.call(
        "search_culinary_sources", {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    )
    identifier = found["data"]["results"][0]["research_result_id"]
    assert (await research.call("extract_culinary_source", {"research_result_id": identifier}))[
        "ok"
    ]
    for _, source in source_fields(recipe_candidate):
        source.clear()
        source.update(kind="WEB", research_result_id=identifier, segment="segment-1")
    local = ApprovalService(repository)

    def apply(candidate):
        result = binding.call(
            "propose_user_change",
            {
                "operation_id": str(uuid4()),
                "command": {
                    "kind": "register_recipe_candidate",
                    "payload": {"candidate": candidate},
                },
            },
        )
        assert result["ok"], result
        proposal = local.list(workspace)[-1]
        applied = local.approve(workspace, proposal["id"], proposal["hash"], attest=True)
        assert applied["ok"], applied
        return proposal, applied

    _, registered = apply(recipe_candidate)
    source = registered["data"]["candidate"]["method_source"]
    origin = (
        {"kind": "USER_SIMULATION", "scenario": "Demonstração fictícia isolada"}
        if mode == "SIMULATION"
        else {"kind": "USER_PROVIDED"}
    )
    measurement = {
        "kind": "USER_REPORTED_MEASUREMENT",
        "method": "Relato de contagem de porções pela cozinheira.",
        "context": "Um lote da ficha, sem certificação independente.",
    }
    proposal, adapted = apply(
        {
            "origin": {"source": origin, "derived_from": {"recipe_id": 1, "version": 1}},
            "changes": {
                "title": "Ficha adaptada com rendimento reportado",
                "yield_per_batch": {
                    "servings_per_batch": 2,
                    "sale_unit_label": "porção",
                    "source": measurement,
                },
                "yield_gap": None,
            },
        }
    )
    candidate = adapted["data"]["candidate"]
    assert candidate["method_source"] == source
    assert source == research.materialize_source(identifier, "segment-1", purpose="RECIPE")
    measured = candidate["yield_per_batch"]["source"]
    assert all(measured[key] == value for key, value in measurement.items())
    assert measured["local_event_id"]
    reopened = ApprovalService(SQLiteWorkspaceRepository(database))
    after = reopened.repository.load(workspace)
    assert reopened.approve(workspace, proposal["id"], proposal["hash"], attest=True) == adapted
    assert reopened.repository.load(workspace) == after
    projected = AttendanceService(database, workspace, "ATTENDANCE").call("get_business_state", {})
    assert projected["ok"], projected
    assert projected["data"]["context_mode"] == mode
    assert projected["data"]["hypothetical"] is (mode == "SIMULATION")
    assert after[1].candidates[1].depends_on_simulation is (mode == "SIMULATION")
    assert projected["data"]["recipes"][1]["sources"][0]["url"] == source["url"]
    before_promotion = database.read_bytes()
    with pytest.raises(ValueError, match="Modo imutável"):
        bootstrap_workspace(
            database,
            inventory_file,
            allowed_directory=tmp_path,
            context_mode="REAL" if mode == "SIMULATION" else "SIMULATION",
        )
    assert database.read_bytes() == before_promotion


def test_migration_keeps_legacy_sources_decisions_hashes_and_pricing_replay(
    pricing_workspace, tmp_path
):
    reader, workspace, recipe, acceptance, command, database = pricing_workspace()
    request = {
        "workspace_id": workspace,
        "operation_id": str(uuid4()),
        "expected_revision": reader.repository.load(workspace)[0],
        "recipe_id": recipe["id"],
        "acceptance_id": acceptance["id"],
    }
    priced = reader.calculate_pricing_scenarios(request)
    assert priced["ok"], priced
    selected = command(
        "save_menu_decision",
        recipe_id=recipe["id"],
        acceptance_id=acceptance["id"],
        calculation_id=priced["data"]["calculation"]["id"],
        scenario_id="M20",
        evidence=pricing_evidence("Escolho M20"),
    )
    assert selected["ok"], selected
    before = reader.repository.load(workspace, with_snapshot=True)
    migrate_proposals(reader.repository, tmp_path / "legacy-v1.sqlite3")
    migrate_research(reader.repository, tmp_path / "legacy-v2.sqlite3")
    assert reader.repository.load(workspace, with_snapshot=True) == before
    assert (
        SQLiteWorkspaceRepository(tmp_path / "legacy-v2.sqlite3").load(
            workspace, with_snapshot=True
        )
        == before
    )
    assert reader.calculate_pricing_scenarios(request)["data"] == priced["data"]
    source = (
        reader.repository.load(workspace)[1].candidates[0].method_source.model_dump(mode="json")
    )
    assert "research_result_id" not in source and "content_sha256" not in source
    public = AttendanceService(database, workspace, "ATTENDANCE").call("get_business_state", {})
    assert public["ok"] and public["data"]["recipes"][0]["origin"] == "Fonte histórica preservada."
    assert reader.repository.load(workspace, with_snapshot=True) == before


@pytest.mark.parametrize("damage", ["future_schema", "existing_backup"])
def test_refused_migration_preserves_database_and_existing_backup(tmp_path, inventory_file, damage):
    database = tmp_path / "migration-refusal.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "refusal-v1.sqlite3")
    backup = tmp_path / "refused-backup.sqlite3"
    if damage == "future_schema":
        with sqlite3.connect(database) as db:
            db.execute("INSERT INTO schema_migrations VALUES (999, '2026-11-15T00:00:00Z')")
    else:
        backup.write_bytes(b"existing synthetic backup")
    before = database.read_bytes()
    with pytest.raises((sqlite3.DatabaseError, FileExistsError)):
        migrate_research(repository, backup)
    assert database.read_bytes() == before
    if damage == "future_schema":
        assert not backup.exists()
    else:
        assert backup.read_bytes() == b"existing synthetic backup"
        assert repository.load(workspace) is not None
