"""CLI de onboarding com fixtures temporárias; nunca atesta decisões."""

import json
import subprocess
import sys

import pytest


def cli(*args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "dona_maria.onboarding", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def test_prepare_is_idempotent_and_preserves_business_state(tmp_path):
    target = tmp_path / "demo com espaços"
    first = cli("prepare", "--directory", target)
    assert first.returncode == 0, first.stderr
    manifest = json.loads((target / "demo.json").read_text(encoding="utf-8"))
    database = target / "workspace.sqlite3"
    before = database.read_bytes()
    second = cli("prepare", "--directory", target)
    assert second.returncode == 0, second.stderr
    assert json.loads((target / "demo.json").read_text(encoding="utf-8")) == manifest
    assert database.read_bytes() == before
    checked = cli("check", "--directory", target)
    assert checked.returncode == 0, checked.stderr
    report = json.loads(checked.stdout)
    assert report["mcp"] == "PASS"
    assert report["context_mode"] == "SIMULATION"
    assert report["human_decisions"] == 0


def test_prepare_refuses_existing_unowned_directory(tmp_path):
    marker = tmp_path / "personal.txt"
    marker.write_text("preserve", encoding="utf-8")
    result = cli("prepare", "--directory", tmp_path)
    assert result.returncode != 0
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert not (tmp_path / "workspace.sqlite3").exists()


def test_invalid_manifest_is_a_clear_error_without_traceback(tmp_path):
    (tmp_path / "demo.json").write_text("[]", encoding="utf-8")
    result = cli("check", "--directory", tmp_path)
    assert result.returncode == 1
    assert "manifesto" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_setup_child_environment_excludes_personal_context(monkeypatch):
    from dona_maria.onboarding import environment

    for key in ("OPENAI_API_KEY", "PYTHONPATH", "HERMES_HOME", "DONA_MARIA_DB_PATH"):
        monkeypatch.setenv(key, "PRIVATE-CANARY")
    result = environment()
    assert "PRIVATE-CANARY" not in result.values()


def test_review_cannot_override_binding_or_migrate(tmp_path):
    target = tmp_path / "demo"
    assert cli("prepare", "--directory", target).returncode == 0
    other = tmp_path / "other.sqlite3"
    for arguments in (("--database", other, "list"), ("migrate", "--backup", other)):
        result = cli("review", "--directory", target, *arguments)
        assert result.returncode != 0
        assert "Argumentos de revisão" in result.stderr
        assert not other.exists()


def test_setup_does_not_install_into_an_ambient_project(monkeypatch, tmp_path):
    from dona_maria.onboarding import main

    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(tmp_path / "personal-venv"))
    monkeypatch.setenv("PYTHONPATH", "other-checkout")
    monkeypatch.setattr(sys, "argv", ["demo", "setup", "--directory", str(tmp_path / "demo")])
    monkeypatch.setattr("shutil.which", lambda name: name)
    environments = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: environments.append(kw.get("env")))
    main()
    assert environments and all(env is not None for env in environments)
    assert all(
        "UV_PROJECT_ENVIRONMENT" not in env and "PYTHONPATH" not in env for env in environments
    )


def workbook(path, ingredient="Feijão", price="27.00"):
    from openpyxl import Workbook

    book = Workbook()
    pantry = book.active
    pantry.title = "Despensa"
    pantry.append(["Ingrediente", "Quantidade em estoque", "Unidade"])
    pantry.append([ingredient, 3, "kg"])
    prices = book.create_sheet("Precos")
    prices.append(["Ingrediente", "Quantidade comprada", "Unidade", "Preço total pago (R$)"])
    prices.append([ingredient, 3, "kg", price])
    book.save(path)
    book.close()


def test_real_setup_imports_given_workbook_and_resumes_without_writes(tmp_path):
    source = tmp_path / "minha despensa.xlsx"
    workbook(source)
    original = source.read_bytes()
    target = tmp_path / "atendimento real"
    first = cli("setup-real", "--inventory", source, "--directory", target)
    assert first.returncode == 0, first.stderr
    report = json.loads(first.stdout)
    assert report["context_mode"] == "REAL"
    assert report["inventory"]["items"][0]["name_original"] == "Feijão"
    assert report["inventory"]["items"][0]["unit_cost"] == "0.009"
    assert source.read_bytes() == original
    before = (target / "workspace.sqlite3").read_bytes()
    second = cli("setup-real", "--inventory", source, "--directory", target)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["workspace_id"] == report["workspace_id"]
    assert (target / "workspace.sqlite3").read_bytes() == before
    checked = cli("check", "--directory", target)
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["context_mode"] == "REAL"
    assert json.loads(checked.stdout)["human_decisions"] == 0


def test_real_setup_rejects_replacement_and_simulation_conversion(tmp_path):
    source = tmp_path / "despensa.xlsx"
    workbook(source)
    target = tmp_path / "real"
    assert cli("setup-real", "--inventory", source, "--directory", target).returncode == 0
    before = (target / "workspace.sqlite3").read_bytes()
    workbook(source, "Batata", "18.00")
    assert cli("setup-real", "--inventory", source, "--directory", target).returncode != 0
    assert cli("prepare", "--directory", target).returncode != 0
    assert (target / "workspace.sqlite3").read_bytes() == before
    simulation = tmp_path / "sim"
    assert cli("prepare", "--directory", simulation).returncode == 0
    before = (simulation / "workspace.sqlite3").read_bytes()
    assert cli("setup-real", "--inventory", source, "--directory", simulation).returncode != 0
    assert (simulation / "workspace.sqlite3").read_bytes() == before


@pytest.mark.parametrize("kind", ["missing", "invalid", "no_argument"])
def test_real_setup_diagnoses_bad_input_without_creating_workspace(tmp_path, kind):
    source = tmp_path / "despensa.xlsx"
    if kind == "invalid":
        source.write_text("not an XLSX", encoding="utf-8")
    target = tmp_path / "new"
    arguments = [] if kind == "no_argument" else ["--inventory", source]
    result = cli("setup-real", "--directory", target, *arguments)
    assert result.returncode == 1
    assert "planilha" in result.stderr.lower()
    assert "Traceback" not in result.stderr
    assert not target.exists()


def test_missing_cost_is_reported_without_inventing_a_price(tmp_path):
    source = tmp_path / "despensa.xlsx"
    workbook(source, price=None)
    result = cli("setup-real", "--inventory", source, "--directory", tmp_path / "real")
    assert result.returncode == 0, result.stderr
    item = json.loads(result.stdout)["inventory"]["items"][0]
    assert item["unit_cost"] is None
    assert item["issues"]


def test_real_profile_and_desktop_use_owned_context_and_human_approved_search(
    tmp_path, monkeypatch, capsys
):
    from dona_maria.onboarding import main

    source = tmp_path / "despensa.xlsx"
    workbook(source)
    target = tmp_path / "real"
    assert cli("setup-real", "--inventory", source, "--directory", target).returncode == 0
    host = tmp_path / "hermes pessoal"
    host.mkdir()
    secret = host / ".env"
    secret.write_text("PRIVATE-CANARY", encoding="utf-8")
    config = {}
    calls = []

    def host_process(command, **kwargs):
        calls.append((command, kwargs))
        if command[1:3] == ["profile", "create"]:
            (host / "profiles" / command[3]).mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0, "", "")
        profile, arguments = command[2], command[3:]
        profile_path = host if profile == "default" else host / "profiles" / profile
        output = ""
        if arguments == ["config", "path"]:
            output = str(profile_path / "config.yaml")
        elif arguments == ["--version"]:
            output = config.get("host_version", "Hermes Agent v0.23.1 · local 3b4215785882")
        elif arguments[:2] == ["config", "set"]:
            try:
                config[arguments[2]] = json.loads(arguments[3])
            except ValueError:
                config[arguments[2]] = arguments[3]
        elif arguments[:2] == ["config", "get"]:
            output = json.dumps(config[arguments[2]])
        elif arguments[:2] == ["skills", "list"]:
            output = "dona-maria-cardapio"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(subprocess, "run", host_process)
    monkeypatch.setattr("shutil.which", lambda name: "hermes")
    answers = iter(["feijão, arroz", "LIBERAR PESQUISA"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(sys, "argv", ["onboarding", "configure", "--directory", str(target)])
    main()
    assert secret.read_text(encoding="utf-8") == "PRIVATE-CANARY"
    assert "model.default" not in config
    assert config["web.search_backend"] == "ddgs"
    assert config["web.keyless_fallback"] is False
    assert config["platform_toolsets.cli"] == ["mcp-dona_maria", "culinary_research"]
    research = config["plugins.entries.dona-maria-mediated-research"]
    assert set(research["settings"]["public_terms"].values()) == {"feijão", "arroz"}
    assert research["settings"]["database"] == str(target / "workspace.sqlite3")
    assert research["allow_tool_override"] is False
    assert "PRIVATE-CANARY" not in json.dumps(calls, default=str)
    config["model.default"] = ""
    monkeypatch.setattr(sys, "argv", ["onboarding", "desktop", "--directory", str(target)])
    with pytest.raises(SystemExit):
        main()
    assert not any(command[3:4] == ["desktop"] for command, _ in calls)
    config["model.default"] = "my-provider/my-tool-model"
    monkeypatch.setattr(sys, "argv", ["onboarding", "desktop", "--directory", str(target)])
    main()
    command, options = calls[-1]
    assert command[3:5] == ["desktop", "--cwd"]
    assert (options["cwd"] / ".hermes.md").is_file()
    assert options["cwd"] == host / "profiles" / command[2] / "conversation"
    assert command[5] == str(options["cwd"])
    assert "## Início e retomada" in (options["cwd"] / ".hermes.md").read_text(encoding="utf-8")
    assert "NOT_RUN" in capsys.readouterr().out
    for incompatible in (
        "Hermes Agent v99.0.0 · local 000000000000",
        "Hermes Agent v0.23.1 · local 3b4215780000",
    ):
        config["host_version"] = incompatible
        calls.clear()
        with pytest.raises(SystemExit):
            main()
        assert not any(command[3:4] == ["desktop"] for command, _ in calls)


@pytest.mark.parametrize("answers", [["arroz", "não"], ["https://private.example"]])
def test_research_requires_explicit_valid_public_terms_before_touching_hermes(
    tmp_path, monkeypatch, answers
):
    from dona_maria.onboarding import main

    source = tmp_path / "despensa.xlsx"
    workbook(source)
    target = tmp_path / "real"
    assert cli("setup-real", "--inventory", source, "--directory", target).returncode == 0
    responses = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt: next(responses))
    monkeypatch.setattr(sys, "argv", ["onboarding", "configure", "--directory", str(target)])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Hermes must not run"))
    with pytest.raises(SystemExit):
        main()
    assert not (target / "research.json").exists()
    assert not (target / "profile-ready.json").exists()
