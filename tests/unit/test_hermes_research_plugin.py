"""Contrato na fronteira de registro do plugin; não representa host real."""

import json
import subprocess
import sys
import sysconfig
from hashlib import sha256
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from dona_maria.approvals import migrate_proposals
from dona_maria.bootstrap import bootstrap_workspace
from dona_maria.hermes_research import register
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.research import migrate_research


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def host_boundary(monkeypatch, tmp_path, inventory_file):
    database = tmp_path / "plugin.sqlite3"
    workspace = bootstrap_workspace(database, inventory_file, allowed_directory=tmp_path)[
        "workspace_id"
    ]
    repository = SQLiteWorkspaceRepository(database)
    migrate_proposals(repository, tmp_path / "v1.sqlite3")
    migrate_research(repository, tmp_path / "v2.sqlite3")
    queries, tools = [], {}

    def search(query, limit):
        queries.append((query, limit))
        return {
            "success": True,
            "data": {
                "web": [
                    {"url": "https://example.org/arroz", "title": "Arroz", "description": "Cozinhe"}
                ]
            },
        }

    identity = SimpleNamespace(
        base_version="0.23.1", commit="3b421578588243f920886e6fe79a6faa87ea026e"
    )
    modules = {
        "hermes_cli.version_info": {"get_version_info": lambda: identity},
        "agent.web_search_registry": {
            "_configured_backend": lambda capability: "fixture-provider",
            "get_provider": lambda name: SimpleNamespace(
                search=search, supports_search=lambda: True
            ),
        },
        "tools.url_safety": {"create_ssrf_safe_async_client": lambda **kwargs: None},
    }
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    settings = {
        "application_source": str(Path(__file__).resolve().parents[2] / "src"),
        "database": str(database),
        "workspace_id": workspace,
        "public_terms": {"arroz": "arroz"},
        "search_provider": "fixture-provider",
    }
    context = SimpleNamespace(
        get_config=lambda key, default=None: settings.get(key, default),
        register_tool=lambda **tool: tools.update({tool["name"]: tool}) or object(),
    )
    return context, tools, queries, identity


@pytest.mark.anyio
async def test_exa_uses_native_anonymous_endpoint_without_registry_or_failover(
    host_boundary, monkeypatch
):
    context, tools, queries, _ = host_boundary
    original = context.get_config
    context.get_config = lambda key, default=None: (
        "exa" if key == "search_provider" else original(key, default)
    )
    registry = sys.modules["agent.web_search_registry"]
    native_search = registry.get_provider("fixture").search
    monkeypatch.setattr(registry, "_configured_backend", lambda _: "exa")
    monkeypatch.setattr(registry, "get_provider", lambda _: pytest.fail("No registry fallback"))
    native = ModuleType("plugins.web.keyless_mcp")
    native.exa_search_keyless = native_search
    monkeypatch.setitem(sys.modules, native.__name__, native)
    register(context)
    request = {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
    result = json.loads(await tools["search_culinary_sources"]["handler"](request))
    assert result["ok"] and result["data"]["provider"] == "exa"
    assert queries == [("receita arroz", 1)]
    database = Path(context.get_config("database"))
    before = sha256(database.read_bytes()).digest()
    for failure in ({"success": False, "error": "quota"}, {"success": True, "data": {"web": []}}):
        native.exa_search_keyless = lambda *args, response=failure: response
        refused = json.loads(await tools["search_culinary_sources"]["handler"](request))
        assert refused["error"]["code"] == "DATA_SOURCE_UNAVAILABLE"
        assert sha256(database.read_bytes()).digest() == before

    def unavailable(*args):
        raise ConnectionError("PRIVATE-CANARY")

    native.exa_search_keyless = unavailable
    refused = json.loads(await tools["search_culinary_sources"]["handler"](request))
    assert refused["error"]["code"] == "DATA_SOURCE_UNAVAILABLE"
    assert "PRIVATE-CANARY" not in str(refused)
    assert sha256(database.read_bytes()).digest() == before
    monkeypatch.setattr(registry, "_configured_backend", lambda _: "auto")
    refused = json.loads(await tools["search_culinary_sources"]["handler"](request))
    assert refused["error"]["code"] == "COMPATIBILITY_BLOCKED"


@pytest.mark.anyio
async def test_live_diagnostic_reads_profile_and_never_persists_research(
    host_boundary, monkeypatch
):
    from dona_maria.hermes_research_check import check

    context, _, queries, _ = host_boundary
    settings = {
        key: context.get_config(key)
        for key in ("database", "workspace_id", "search_provider", "public_terms")
    }
    database = Path(settings["database"])
    before = sha256(database.read_bytes()).digest()

    async def extract(self, url):
        return {"url": url, "content_sha256": "a" * 64, "text": "Ingredientes: arroz"}

    monkeypatch.setattr("dona_maria.research_network.SecureExtractor.extract", extract)
    report = await check(settings)
    assert queries == [("receita arroz", 1)]
    assert report["research"] == "LIVE_SEARCH_AND_EXTRACTION_PASS"
    assert report["business_writes"] is False
    assert report["desktop_conversation"] == "NOT_TESTED"
    assert sha256(database.read_bytes()).digest() == before


@pytest.mark.anyio
async def test_plugin_registers_only_two_bound_capabilities_and_dispatches_public_query(
    host_boundary,
):
    context, tools, queries, _ = host_boundary
    register(context)
    assert set(tools) == {"search_culinary_sources", "extract_culinary_source"}
    result = json.loads(
        await tools["search_culinary_sources"]["handler"](
            {"purpose": "RECIPE", "public_term_ids": ["arroz"]}
        )
    )
    assert result["ok"], result
    assert queries == [("receita arroz", 1)]
    refused = json.loads(
        await tools["extract_culinary_source"]["handler"](
            {"url": "https://evil.test", "research_result_id": "CANARY_PRIVATE"}
        )
    )
    assert not refused["ok"] and "CANARY_PRIVATE" not in str(refused)


def test_incompatible_host_registers_no_capability(host_boundary):
    context, tools, _, identity = host_boundary
    identity.commit = "unverified"
    with pytest.raises(RuntimeError, match="incompat"):
        register(context)
    assert tools == {}


def test_registration_failure_reports_only_safe_stage_and_exception_type(host_boundary):
    context, tools, _, _ = host_boundary
    context.get_config = lambda key: None
    with pytest.raises(RuntimeError, match=r"APPLICATION_SOURCE:ValueError") as error:
        register(context)
    assert tools == {}
    assert error.value.__suppress_context__
    assert isinstance(error.value.__context__, ValueError)


def test_registration_diagnostic_never_includes_private_exception_text(host_boundary, monkeypatch):
    def fail(source):
        raise OSError("PRIVATE-CANARY credential and local path")

    monkeypatch.setattr("dona_maria.hermes_research._load_application", fail)
    with pytest.raises(RuntimeError, match=r"APPLICATION_SOURCE:OSError") as error:
        register(host_boundary[0])
    assert "PRIVATE-CANARY" not in str(error.value)
    assert host_boundary[1] == {}


@pytest.mark.anyio
async def test_quote_search_requests_one_complete_result_without_trimming_metadata(
    host_boundary, monkeypatch
):
    context, tools, _, _ = host_boundary
    hits = [
        {"url": "https://example.org/oferta", "title": "Oferta de arroz", "description": "Arroz"},
        {"url": "https://example.org/outro", "title": "X" * 255, "description": "Outro"},
    ]

    def search(query, limit):
        assert query == "oferta arroz"
        return {"success": True, "data": {"web": hits[:limit]}}

    monkeypatch.setattr(
        sys.modules["agent.web_search_registry"],
        "get_provider",
        lambda name: SimpleNamespace(search=search, supports_search=lambda: True),
    )
    register(context)
    response = json.loads(
        await tools["search_culinary_sources"]["handler"](
            {"purpose": "QUOTE", "public_term_ids": ["arroz"]}
        )
    )
    assert response["ok"], response
    assert len(response["data"]["results"]) == 1
    result = response["data"]["results"][0]
    assert result["title"] == "Oferta de arroz"
    assert result["description"] == "Arroz" and result["status"] == "SEARCHED"


@pytest.mark.anyio
async def test_oversized_returned_title_is_refused_without_partial_database_write(
    host_boundary, monkeypatch
):
    context, tools, _, _ = host_boundary
    database = Path(context.get_config("database"))
    before = sha256(database.read_bytes()).digest()
    monkeypatch.setattr(
        sys.modules["agent.web_search_registry"],
        "get_provider",
        lambda name: SimpleNamespace(
            supports_search=lambda: True,
            search=lambda query, limit: {
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://example.org/oferta",
                            "title": "X" * 255,
                            "description": "Arroz",
                        }
                    ]
                },
            },
        ),
    )
    register(context)
    response = json.loads(
        await tools["search_culinary_sources"]["handler"](
            {"purpose": "QUOTE", "public_term_ids": ["arroz"]}
        )
    )
    assert response["ok"] is False and response["data"] is None
    assert response["error"]["code"] == "VALIDATION_ERROR"
    assert sha256(database.read_bytes()).digest() == before


@pytest.mark.parametrize("source", [None, "relative/source"])
def test_plugin_refuses_missing_or_relative_application_source(host_boundary, source):
    context, tools, _, _ = host_boundary
    original = context.get_config
    context.get_config = lambda key, default=None: (
        source if key == "application_source" else original(key, default)
    )
    with pytest.raises(RuntimeError):
        register(context)
    assert tools == {}


def test_plugin_does_not_replace_application_from_another_workspace(host_boundary, tmp_path):
    import dona_maria

    original_module = sys.modules["dona_maria"]
    foreign = tmp_path / "foreign-source"
    package = foreign / "dona_maria"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "raise AssertionError('must not execute')", encoding="utf-8"
    )
    context, tools, _, _ = host_boundary
    original = context.get_config
    context.get_config = lambda key, default=None: (
        str(foreign) if key == "application_source" else original(key, default)
    )
    with pytest.raises(RuntimeError):
        register(context)
    assert tools == {} and sys.modules["dona_maria"] is original_module
    assert dona_maria is original_module


def test_cold_plugin_loads_from_explicit_source_without_pythonpath_or_excel_dependency(
    host_boundary, tmp_path
):
    context, _, _, _ = host_boundary
    settings = {
        key: context.get_config(key)
        for key in ("database", "workspace_id", "public_terms", "search_provider")
    }
    source = Path(__file__).resolve().parents[2] / "src"
    settings["application_source"] = str(source)
    settings["plugin_file"] = str(source / "dona_maria/hermes_research/__init__.py")
    settings["site_packages"] = sysconfig.get_path("purelib")
    script = r"""
import asyncio, importlib.abc, importlib.util, json, sys
from types import ModuleType, SimpleNamespace
settings = json.loads(sys.stdin.read())
sys.path.insert(0, settings.pop("site_packages"))
assert importlib.util.find_spec("dona_maria") is None
class NoExcel(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "openpyxl" or fullname.startswith("openpyxl."):
            raise ModuleNotFoundError("Excel is unavailable in the host", name="openpyxl")
sys.meta_path.insert(0, NoExcel())
def search(query, limit):
    assert query == "receita arroz" and limit == 1
    return {"success": True, "data": {"web": [
        {"url": "https://example.org/arroz", "title": "Arroz", "description": "Fixture"}
    ]}}
for name, values in {
    "hermes_cli.version_info": {"get_version_info": lambda: SimpleNamespace(
        base_version="0.23.1", commit="3b421578588243f920886e6fe79a6faa87ea026e")},
    "agent.web_search_registry": {"_configured_backend": lambda _: "fixture-provider",
        "get_provider": lambda _: SimpleNamespace(search=search, supports_search=lambda: True)},
    "tools.url_safety": {"create_ssrf_safe_async_client": lambda **kw: None},
}.items():
    module = ModuleType(name)
    module.__dict__.update(values)
    sys.modules[name] = module
plugin_file = settings.pop("plugin_file")
spec = importlib.util.spec_from_file_location("cold_plugin", plugin_file,
    submodule_search_locations=[str(__import__("pathlib").Path(plugin_file).parent)])
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)
tools = {}
context = SimpleNamespace(get_config=lambda k, default=None: settings.get(k, default),
    register_tool=lambda **tool: tools.update({tool["name"]: tool}) or object())
paths_before = list(sys.path)
plugin.register(context)
assert sys.path == paths_before
assert set(tools) == {"search_culinary_sources", "extract_culinary_source"}
result = json.loads(asyncio.run(tools["search_culinary_sources"]["handler"](
    {"purpose": "RECIPE", "public_term_ids": ["arroz"]})))
assert result["ok"], result
print("cold registration and mediated dispatch passed")
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-I", "-S", "-c", script],
        input=json.dumps(settings),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cold registration and mediated dispatch passed"
