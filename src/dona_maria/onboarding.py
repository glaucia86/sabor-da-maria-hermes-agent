"""Preparação local de atendimento REAL ou demo SIMULATION; fora do catálogo MCP."""

import argparse
import asyncio
import importlib.metadata
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = (
    "get_business_state",
    "get_inventory_snapshot",
    "evaluate_recipe_feasibility",
    "evaluate_purchase_plan",
    "propose_user_change",
    "calculate_pricing_scenarios",
)


class SetupError(ValueError):
    """Mensagem local controlada, sem conteúdo de arquivos ou subprocessos."""


def environment(home=None):
    # Não herdar credenciais, binding ou PYTHONPATH de outro checkout/perfil.
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "LANG",
        "TERM",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    if home is not None:
        env["HERMES_HOME"] = str(home)
    return env


def doctor():
    report = {"python": sys.version.split()[0], "python_3_13": sys.version_info[:2] == (3, 13)}
    for command in ("uv", "hermes"):
        executable = shutil.which(command)
        if not executable:
            report[command] = "MISSING: instale pelo guia docs/setup.md"
            continue
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        report[command] = (
            result.stdout.splitlines()[0] if result.returncode == 0 and result.stdout else "ERROR"
        )
    for package in ("mcp", "pydantic", "openpyxl"):
        try:
            report[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report[package] = "MISSING: execute uv sync --locked --python 3.13"
    return report


def manifest(directory):
    data = json.loads((directory / "demo.json").read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("format") != "sabor-demo-1"
        or data.get("context_mode") not in {"SIMULATION", "REAL"}
        or not isinstance(data.get("workspace_id"), str)
    ):
        raise SetupError("Manifesto de demo inválido.")
    from uuid import UUID

    UUID(data["workspace_id"])
    inventory_name = "inventory.xlsx" if data["context_mode"] == "REAL" else "synthetic.xlsx"
    for name in ("workspace.sqlite3", inventory_name, "demo.json"):
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
            raise SetupError("Arquivo ausente ou redirecionado; preserve a pasta e use outra demo.")
    from dona_maria.business_state import AttendanceService
    from dona_maria.persistence import SQLiteWorkspaceRepository

    service = AttendanceService(directory / "workspace.sqlite3", data["workspace_id"], "ATTENDANCE")
    loaded = SQLiteWorkspaceRepository(directory / "workspace.sqlite3").load(data["workspace_id"])
    if loaded is None or loaded[1].context_mode != data["context_mode"]:
        raise SetupError("Contexto do banco não corresponde ao manifesto.")
    return data, service


def prepare(directory):
    if directory.exists():
        data, _ = manifest(directory)
        if data["context_mode"] != "SIMULATION":
            raise SetupError("prepare exige SIMULATION; preserve o atendimento REAL.")
        return data
    from openpyxl import Workbook

    from dona_maria.approvals import migrate_proposals
    from dona_maria.bootstrap import bootstrap_workspace
    from dona_maria.persistence import SQLiteWorkspaceRepository

    directory.mkdir(parents=True, exist_ok=False)
    workbook = Workbook()
    pantry = workbook.active
    pantry.title = "Despensa"
    pantry.append(["Ingrediente", "Quantidade em estoque", "Unidade"])
    pantry.append(["Arroz", 5, "kg"])
    prices = workbook.create_sheet("Precos")
    prices.append(["Ingrediente", "Quantidade comprada", "Unidade", "Preço total pago (R$)"])
    prices.append(["Arroz", 5, "kg", "24.90"])
    inventory = directory / "synthetic.xlsx"
    workbook.save(inventory)
    workbook.close()
    database = directory / "workspace.sqlite3"
    result = bootstrap_workspace(
        database, inventory, allowed_directory=directory, context_mode="SIMULATION"
    )
    migrate_proposals(SQLiteWorkspaceRepository(database), directory / "before-proposals.sqlite3")
    data = {
        "format": "sabor-demo-1",
        "workspace_id": result["workspace_id"],
        "context_mode": "SIMULATION",
    }
    (directory / "demo.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def setup_real(directory, inventory):
    from dona_maria.approvals import migrate_proposals
    from dona_maria.bootstrap import bootstrap_workspace
    from dona_maria.inventory import import_inventory
    from dona_maria.persistence import SQLiteWorkspaceRepository
    from dona_maria.research import migrate_research

    if inventory is None:
        raise SetupError("setup-real exige --inventory com sua planilha XLSX real.")
    try:
        inventory = inventory.resolve(strict=True)
        snapshot = import_inventory(inventory, allowed_directory=inventory.parent)
    except (OSError, ValueError) as exc:
        raise SetupError(
            "Planilha ausente, inválida ou acima dos limites. Confira --inventory, "
            "as abas Despensa/Precos e os cabeçalhos do README."
        ) from exc
    if directory.exists():
        data, _ = manifest(directory)
        if data["context_mode"] != "REAL" or data.get("inventory_sha256") != snapshot.source_sha256:
            raise SetupError("Outra planilha ou contexto: use um diretório novo.")
        copied = import_inventory(directory / "inventory.xlsx", allowed_directory=directory)
        loaded = SQLiteWorkspaceRepository(directory / "workspace.sqlite3").load(
            data["workspace_id"], with_snapshot=True
        )
        if copied.source_sha256 != snapshot.source_sha256 or loaded[2].id != snapshot.id:
            raise SetupError("Cópia, manifesto e banco divergem; preserve o diretório.")
    else:
        directory.mkdir(parents=True, exist_ok=False)
        copied_path = directory / "inventory.xlsx"
        shutil.copyfile(inventory, copied_path)
        copied = import_inventory(copied_path, allowed_directory=directory)
        if copied.source_sha256 != snapshot.source_sha256:
            raise SetupError("Planilha mudou durante a cópia; use um diretório novo.")
        database = directory / "workspace.sqlite3"
        result = bootstrap_workspace(
            database, copied_path, allowed_directory=directory, context_mode="REAL"
        )
        repository = SQLiteWorkspaceRepository(database)
        migrate_proposals(repository, directory / "before-proposals.sqlite3")
        migrate_research(repository, directory / "before-research.sqlite3")
        data = {
            "format": "sabor-demo-1",
            "workspace_id": result["workspace_id"],
            "context_mode": "REAL",
            "inventory_sha256": snapshot.source_sha256,
        }
        (directory / "demo.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {
        **data,
        "inventory": snapshot.model_dump(mode="json"),
        "next_step": "Execute configure neste diretório; modelo e credenciais são locais.",
    }


async def check(directory):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    data, _ = manifest(directory)
    env = environment() | {
        "DONA_MARIA_DB_PATH": str(directory / "workspace.sqlite3"),
        "DONA_MARIA_WORKSPACE_ID": data["workspace_id"],
        "DONA_MARIA_MODE": "ATTENDANCE",
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-X", "utf8", "-B", "-m", "dona_maria.launcher"], env=env
    )
    async with asyncio.timeout(30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if {tool.name for tool in (await session.list_tools()).tools} != set(TOOLS):
                    raise SetupError("Catálogo MCP divergente.")
                state = await session.call_tool("get_business_state", {})
                denied = await session.call_tool("accept_recipe", {})
                if state.is_error or not denied.is_error:
                    raise SetupError("Leitura ou recusa MCP falhou.")
    skill = ROOT / "skills/dona-maria-cardapio/SKILL.md"
    if not skill.is_file() or not (ROOT / ".hermes.md").is_file():
        raise SetupError("Skill ou instruções ausentes; restaure o checkout.")
    from dona_maria.approvals import ApprovalService
    from dona_maria.persistence import SQLiteWorkspaceRepository

    proposals = ApprovalService(SQLiteWorkspaceRepository(directory / "workspace.sqlite3")).list(
        data["workspace_id"]
    )
    return {
        "mcp": "PASS",
        "context_mode": data["context_mode"],
        "skill": "PRESENT",
        "human_decisions": sum(p["status"] == "APPROVED" for p in proposals),
        "hermes_host": "NOT_RUN",
        "research": "NOT_RUN" if data["context_mode"] == "REAL" else "DISABLED",
        "state": state.structured_content,
    }


def profile_name(data):
    prefix = "sabor-real-" if data["context_mode"] == "REAL" else "sabor-demo-"
    return prefix + data["workspace_id"].replace("-", "")


def hermes(directory, arguments, *, capture=False, profile=None, cwd=None):
    executable = shutil.which("hermes")
    if not executable:
        raise SetupError("Hermes ausente do PATH; consulte docs/setup.md.")
    data, _ = manifest(directory)
    return subprocess.run(
        [executable, "-p", profile or profile_name(data), *arguments],
        cwd=cwd or directory,
        env=environment(),
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60 if capture else None,
    )


def settings(directory, data):
    result = {
        "plugins.enabled": ["dona-maria-attendance-policy"],
        "platform_toolsets.cli": ["mcp-dona_maria"],
        "tools.tool_search.enabled": "off",
        "memory.memory_enabled": False,
        "memory.user_profile_enabled": False,
        "display.tool_progress": False,
        "display.show_reasoning": False,
        "skills.external_dirs": [(ROOT / "skills").as_posix()],
        "mcp_servers": {
            "dona_maria": {
                "command": sys.executable,
                "args": ["-X", "utf8", "-B", "-m", "dona_maria.launcher"],
                "env": {
                    "DONA_MARIA_DB_PATH": str(directory / "workspace.sqlite3"),
                    "DONA_MARIA_WORKSPACE_ID": data["workspace_id"],
                    "DONA_MARIA_MODE": "ATTENDANCE",
                },
                "tools": {"include": list(TOOLS), "resources": False, "prompts": False},
                "connect_timeout": 15,
            }
        },
    }
    if data["context_mode"] == "REAL":
        from dona_maria.business_state import AttendanceService
        from dona_maria.research import ResearchService

        path = directory / "research.json"
        if path.is_symlink():
            raise SetupError("Configuração de pesquisa redirecionada.")
        terms = json.loads(path.read_text(encoding="utf-8"))
        ResearchService(
            AttendanceService(directory / "workspace.sqlite3", data["workspace_id"], "ATTENDANCE"),
            terms,
            search=None,
        )
        result.update(
            {
                "plugins.enabled": [
                    "dona-maria-attendance-policy",
                    "dona-maria-mediated-research",
                    "web-ddgs",
                ],
                "plugins.entries.dona-maria-mediated-research": {
                    "allow_tool_override": False,
                    "settings": {
                        "application_source": (ROOT / "src").as_posix(),
                        "database": str(directory / "workspace.sqlite3"),
                        "workspace_id": data["workspace_id"],
                        "search_provider": "ddgs",
                        "public_terms": terms,
                    },
                },
                "platform_toolsets.cli": ["mcp-dona_maria", "culinary_research"],
                "web.search_backend": "ddgs",
                "web.keyless_fallback": False,
                "security.allow_private_urls": False,
                "security.fake_ip_ranges": [],
            }
        )
    return result


def approve_search_terms(directory, service):
    from dona_maria.research import ResearchService

    path = directory / "research.json"
    if path.exists():
        return
    print("Pesquisa real com DDGS. Somente os termos liberados serão enviados ao provedor.")
    print("Informe ingredientes ou pratos públicos, sem quantidades, custos ou dados pessoais.")
    entered = input("Termos separados por vírgula (ex.: arroz, feijão): ")
    terms = {f"termo-{i}": term.strip() for i, term in enumerate(entered.split(","), 1)}
    try:
        ResearchService(service, terms, search=None)
    except (ValueError, TypeError) as exc:
        raise SetupError("Use de 1 a 200 termos de até 100 letras, espaços ou hífens.") from exc
    print(json.dumps(terms, ensure_ascii=False, indent=2))
    if input("Para autorizar esses termos, digite LIBERAR PESQUISA: ") != "LIBERAR PESQUISA":
        raise SetupError("Pesquisa não autorizada; nenhum perfil foi criado.")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(terms, stream, ensure_ascii=False, indent=2)


def profile_plugins(data):
    plugins = {"dona-maria-attendance-policy": "hermes_policy"}
    if data["context_mode"] == "REAL":
        plugins["dona-maria-mediated-research"] = "hermes_research"
    return plugins


def conversation_context(data):
    context = (ROOT / ".hermes.md").read_text(encoding="utf-8")
    if data["context_mode"] == "REAL":
        # Desktop não recebe o --skills usado no chat CLI.
        context += "\n\n" + (ROOT / "skills/dona-maria-cardapio/SKILL.md").read_text(
            encoding="utf-8"
        )
    return context


def configure(directory):
    data, service = manifest(directory)
    if (directory / "profile-ready.json").exists():
        return verify_profile(directory)
    if data["context_mode"] == "REAL":
        approve_search_terms(directory, service)
    expected_settings = settings(directory, data)
    root_config = hermes(directory, ["config", "path"], capture=True, profile="default")
    root = Path(root_config.stdout.strip()).parent
    if not root.is_absolute() or not root.is_dir():
        raise SetupError("Raiz do Hermes indisponível.")
    if (root / "profiles" / profile_name(data)).exists():
        raise SetupError("Perfil já existe sem confirmação de preparo; não será sobrescrito.")
    seed = root / "profiles" / ("sabor-seed-" + data["workspace_id"].replace("-", ""))
    seed.mkdir(parents=True, exist_ok=False)
    (seed / ".env").write_text(
        "# Perfil de origem vazio do onboarding; sem credenciais.\n", encoding="utf-8"
    )
    # O Hermes herda model/provider até sem --clone; a origem precisa ser vazia.
    subprocess.run(
        [
            shutil.which("hermes"),
            "profile",
            "create",
            profile_name(data),
            "--no-skills",
            "--no-alias",
        ],
        env=environment(seed),
        cwd=directory,
        check=True,
        capture_output=True,
        timeout=60,
    )
    home = profile_home(directory)
    if home != root / "profiles" / profile_name(data):
        raise SetupError("Perfil criado fora da raiz esperada.")
    conversation = home / "conversation"
    conversation.mkdir(exist_ok=False)
    (conversation / ".hermes.md").write_text(conversation_context(data), encoding="utf-8")
    for plugin_name, source_name in profile_plugins(data).items():
        source = ROOT / "src/dona_maria" / source_name
        plugin = home / "plugins" / plugin_name
        plugin.mkdir(parents=True)
        for name in ("__init__.py", "plugin.yaml"):
            shutil.copyfile(source / name, plugin / name)
    for key, value in expected_settings.items():
        encoded = value if isinstance(value, str) else json.dumps(value)
        hermes(directory, ["config", "set", key, encoded], capture=True)
    (directory / "profile-ready.json").write_text(
        json.dumps({"profile": profile_name(data)}), encoding="utf-8"
    )
    return {
        "configured": True,
        "profile": profile_name(data),
        "model": "REQUIRED: execute model",
        "host_validation": "NOT_RUN",
        "research": "CONFIGURED_NOT_EXERCISED" if data["context_mode"] == "REAL" else "DISABLED",
    }


def profile_home(directory):
    result = hermes(directory, ["config", "path"], capture=True)
    home = Path(result.stdout.strip()).parent
    data, _ = manifest(directory)
    if not home.is_absolute() or home.name != profile_name(data) or home.is_symlink():
        raise SetupError("Caminho do perfil não corresponde à demo.")
    return home


def verify_hermes_runtime(directory, profile):
    from dona_maria.hermes_research import HERMES_COMMIT

    options = {
        "cwd": directory,
        "env": environment(),
        "check": True,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 60,
    }
    try:
        executable = shutil.which("hermes")
        if not executable:
            raise ValueError
        # O launcher vincula Python e bootstrap à instalação; o banner não é identidade.
        resolved = subprocess.run(
            [
                executable,
                "--print-runtime-command",
                "--module",
                "hermes_cli.version_info",
                "--",
                "-p",
                profile,
            ],
            **options,
        )
        command = json.loads(resolved.stdout)
        if (
            not isinstance(command, list)
            or len(command) != 6
            or not all(isinstance(part, str) and part for part in command)
            or command[1:3] != ["-I", "-c"]
            or command[4:] != ["-p", profile]
            or not Path(command[0]).is_absolute()
            or not Path(command[0]).is_file()
        ):
            raise ValueError
        command[3] += (
            "; import json; from hermes_cli.version_info import get_version_info; "
            "identity = get_version_info(); "
            "print(json.dumps(dict(executable=sys.executable, "
            "version=identity.base_version, commit=identity.commit)))"
        )
        result = subprocess.run([command[0], "-B", *command[1:]], **options)
        identity = json.loads(result.stdout)
        if (
            not isinstance(identity, dict)
            or identity.get("version") != "0.23.1"
            or identity.get("commit") != HERMES_COMMIT
            or not isinstance(identity.get("executable"), str)
            or not Path(identity["executable"]).is_absolute()
            or Path(identity["executable"]).resolve() != Path(command[0]).resolve()
        ):
            raise ValueError
    except (OSError, ValueError, subprocess.SubprocessError):
        raise SetupError(
            "Versão/commit do Hermes incompatível ou não identificado. Pesquisa exige "
            "0.23.1 / 3b421578588243f920886e6fe79a6faa87ea026e; confira docs/setup.md."
        ) from None


def verify_profile(directory):
    data, _ = manifest(directory)
    if data["context_mode"] == "REAL":
        verify_hermes_runtime(directory, profile_name(data))
    for key, expected in settings(directory, data).items():
        actual = hermes(directory, ["config", "get", key, "--json"], capture=True)
        if json.loads(actual.stdout) != expected:
            raise SetupError("Configuração divergente: " + key)
    home = profile_home(directory)
    for plugin_name, source_name in profile_plugins(data).items():
        for name in ("__init__.py", "plugin.yaml"):
            if (home / "plugins" / plugin_name / name).read_bytes() != (
                ROOT / "src/dona_maria" / source_name / name
            ).read_bytes():
                raise SetupError("Plugin divergente do checkout: " + plugin_name)
    if (home / "conversation/.hermes.md").read_text(encoding="utf-8") != conversation_context(data):
        raise SetupError("Orientações desatualizadas; prepare outro atendimento.")
    skills = hermes(directory, ["skills", "list", "--enabled-only"], capture=True)
    if "dona-maria-cardapio" not in skills.stdout:
        raise SetupError("Skill de atendimento não descoberta pelo Hermes.")
    hermes(directory, ["mcp", "test", "dona_maria"], capture=True)
    try:
        model = hermes(directory, ["config", "get", "model.default", "--json"], capture=True)
        model_configured = bool(json.loads(model.stdout))
    except subprocess.CalledProcessError:
        model_configured = False
    return {
        "configuration": "PASS",
        "research_version_label": "MATCH" if data["context_mode"] == "REAL" else "NOT_REQUIRED",
        "profile": profile_name(data),
        "policy_files": "PASS",
        "skill_discovery": "PASS",
        "hermes_mcp_connection": "PASS",
        "model_configured": model_configured,
        "next_step": "Configure o modelo com a ação model e homologue a conversa no perfil.",
        "credentials": "NOT_CHECKED",
        "host_dispatch_and_conversation": "NOT_RUN",
        "desktop": "NOT_RUN",
        "research": "CONFIGURED_NOT_EXERCISED" if data["context_mode"] == "REAL" else "DISABLED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "doctor",
            "setup",
            "setup-real",
            "prepare",
            "check",
            "configure",
            "verify-profile",
            "model",
            "chat",
            "desktop",
            "review",
        ),
    )
    parser.add_argument("--directory", type=Path, default=ROOT / "artifacts/private/demo-s20")
    parser.add_argument("--query")
    parser.add_argument("--resume")
    parser.add_argument("--inventory", type=Path)
    args, extra = parser.parse_known_args()
    directory = args.directory.absolute()
    try:
        if directory.resolve() != directory:
            raise ValueError("Diretório redirecionado ou não canônico.")
        if extra and args.action != "review":
            raise ValueError("Argumentos extras não permitidos.")
        if args.inventory is not None and args.action != "setup-real":
            raise SetupError("--inventory pertence somente a setup-real.")
        if args.action == "doctor":
            result = doctor()
        elif args.action == "setup":
            uv = shutil.which("uv")
            if not uv:
                raise ValueError("uv ausente; instale pelo guia docs/setup.md.")
            subprocess.run(
                [uv, "sync", "--locked", "--python", "3.13"],
                cwd=ROOT,
                env=environment(),
                check=True,
            )
            subprocess.run(
                [
                    uv,
                    "run",
                    "--locked",
                    "--no-sync",
                    "python",
                    "-m",
                    "dona_maria.onboarding",
                    "prepare",
                    "--directory",
                    str(directory),
                ],
                cwd=ROOT,
                env=environment(),
                check=True,
            )
            return
        elif args.action == "prepare":
            result = prepare(directory)
        elif args.action == "setup-real":
            result = setup_real(directory, args.inventory)
        elif args.action == "check":
            result = asyncio.run(check(directory))
        elif args.action == "configure":
            result = configure(directory)
        elif args.action == "verify-profile":
            result = verify_profile(directory)
        elif args.action in {"model", "chat", "desktop"}:
            data, _ = manifest(directory)
            if args.action == "model":
                hermes(directory, ["model"])
            else:
                profile_report = verify_profile(directory)
                if not profile_report["model_configured"]:
                    raise SetupError("Modelo ausente no perfil isolado; execute a ação model.")
                if args.action == "desktop":
                    conversation = profile_home(directory) / "conversation"
                    print(json.dumps(profile_report, ensure_ascii=False, indent=2), flush=True)
                    hermes(directory, ["desktop", "--cwd", str(conversation)], cwd=conversation)
                    return
                if not args.query:
                    raise ValueError("chat exige --query; nenhuma fala é fabricada pelo setup.")
                command = [
                    "chat",
                    "--oneshot",
                    "-Q",
                    "--toolsets",
                    ",".join(settings(directory, data)["platform_toolsets.cli"]),
                    "--skills",
                    "dona-maria-cardapio",
                    "-q",
                    args.query,
                ]
                if args.resume:
                    command += ["--resume", args.resume, "--no-restore-cwd"]
                hermes(directory, command, cwd=profile_home(directory) / "conversation")
            return
        else:
            data, _ = manifest(directory)
            review_parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
            review_parser.add_argument(
                "operation", choices=("list", "inspect", "approve", "reject")
            )
            review_parser.add_argument("proposal", nargs="?")
            review_parser.add_argument("--hash")
            try:
                review_args, unknown = review_parser.parse_known_args(extra)
                if unknown or (review_args.operation != "list" and not review_args.proposal):
                    raise ValueError
                if review_args.operation in {"approve", "reject"} and not review_args.hash:
                    raise ValueError
            except (ValueError, argparse.ArgumentError):
                raise SetupError(
                    "Argumentos de revisão inválidos; use list, inspect, approve ou reject."
                ) from None
            subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    "-m",
                    "dona_maria.approval_cli",
                    "--database",
                    str(directory / "workspace.sqlite3"),
                    "--workspace",
                    data["workspace_id"],
                    *extra,
                ],
                check=True,
                env=environment(),
            )
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except SetupError as exc:
        parser.exit(1, str(exc) + "\n")
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, "Preparação interrompida; nenhuma autorização foi inferida.\n")
    except (
        ValueError,
        KeyError,
        OSError,
        sqlite3.Error,
        ImportError,
        subprocess.SubprocessError,
    ) as exc:
        parser.exit(
            1,
            f"Onboarding recusado ({type(exc).__name__}). Confira dependências, manifesto, "
            "binding e perfil em docs/setup.md. "
            "Preserve a pasta incompleta; use outra pasta nova.\n",
        )


if __name__ == "__main__":
    main()
