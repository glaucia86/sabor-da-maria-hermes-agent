import json
import subprocess
import sys

import anyio
import pytest
from anyio.streams.buffered import BufferedByteReceiveStream
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import LATEST_PROTOCOL_VERSION


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("module", ["dona_maria.mcp_server", "dona_maria.launcher"])
async def test_attendance_catalog_dispatch_refresh_and_restart_are_read_only(
    pricing_workspace, module
):
    reader, workspace, recipe, _, _, database = pricing_workspace()
    before = reader.get_business_state({"workspace_id": workspace})
    original = database.read_bytes()
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", module],
        env={
            "DONA_MARIA_DB_PATH": str(database),
            "DONA_MARIA_WORKSPACE_ID": workspace,
            "DONA_MARIA_MODE": "ATTENDANCE",
        },
    )
    for _ in range(2):
        with anyio.fail_after(20):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    assert initialized.capabilities.resources is None
                    assert initialized.capabilities.prompts is None
                    for _ in range(2):
                        tools = (await session.list_tools()).tools
                        assert [tool.name for tool in tools] == [
                            "get_business_state",
                            "get_inventory_snapshot",
                            "evaluate_recipe_feasibility",
                            "evaluate_purchase_plan",
                        ]
                        assert all(tool.annotations.read_only_hint for tool in tools)
                        assert all(
                            "workspace_id" not in json.dumps(tool.input_schema) for tool in tools
                        )
                        assert all(
                            tool.input_schema["additionalProperties"] is False for tool in tools
                        )
                    for name, arguments in [
                        ("get_business_state", {}),
                        ("get_inventory_snapshot", {}),
                        ("evaluate_recipe_feasibility", {"recipe": 1, "plan_item": 1}),
                        ("evaluate_purchase_plan", {}),
                    ]:
                        result = await session.call_tool(name, arguments)
                        assert not result.is_error
                        assert json.loads(result.content[0].text) == result.structured_content
                        assert workspace not in result.content[0].text
                        assert recipe["id"] not in result.content[0].text
                    for name, arguments in [
                        ("accept_recipe", {}),
                        ("calculate_pricing_scenarios", {}),
                        ("save_menu_decision", {}),
                        ("get_business_state", {"workspace_id": workspace}),
                        ("get_business_state", {"mode": "DIAGNOSTIC"}),
                    ]:
                        result = await session.call_tool(name, arguments)
                        assert result.is_error
                        assert workspace not in result.content[0].text
    assert reader.get_business_state({"workspace_id": workspace}) == before
    assert database.read_bytes() == original


@pytest.mark.parametrize("extra_byte", [False, True])
def test_stdio_receiver_checks_size_before_json_parsing(pricing_workspace, extra_byte):
    _, workspace, _, _, _, database = pricing_workspace()
    from mcp.client.stdio import get_default_environment

    message = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "synthetic", "version": "1"},
            },
        }
    ).encode()
    frame = message + b" " * (512 * 1024 - 1 - len(message)) + b"\n"
    if extra_byte:
        frame = b" " + frame
    environment = get_default_environment() | {
        "DONA_MARIA_DB_PATH": str(database),
        "DONA_MARIA_WORKSPACE_ID": workspace,
        "DONA_MARIA_MODE": "ATTENDANCE",
        "SYNTHETIC_SECRET": "PRIVATE-CANARY",
    }
    before = database.read_bytes()
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env=environment,
        input=frame,
        capture_output=True,
        timeout=15,
        check=False,
    )
    response = json.loads(result.stdout.splitlines()[0])
    if extra_byte:
        assert "error" in response
        assert "excede" in response["error"]["message"]
    else:
        assert response["result"]["serverInfo"]["name"] == "dona_maria"
    assert database.read_bytes() == before
    for private in (workspace.encode(), str(database).encode(), b"PRIVATE-CANARY", b"Traceback"):
        assert private not in result.stdout + result.stderr


@pytest.mark.parametrize("extra_byte", [False, True])
@pytest.mark.parametrize("kind", ["bytes", "nested_collection"])
@pytest.mark.anyio
async def test_raw_parameter_bytes_cannot_hide_in_whitespace(pricing_workspace, extra_byte, kind):
    from mcp.client.stdio import get_default_environment

    _, workspace, _, _, _, database = pricing_workspace()
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "synthetic", "version": "1"},
        },
    }
    parameters = b'{"name":"get_business_state","arguments":{}'
    parameters += b" " * (256 * 1024 - 1 - len(parameters) + extra_byte) + b"}"
    if kind == "nested_collection":
        parameters = json.dumps(
            {
                "name": "get_business_state",
                "arguments": {},
                "_meta": {"nested": {"items": [0] * (200 + extra_byte)}},
            }
        ).encode()
    with anyio.fail_after(15):
        async with await anyio.open_process(
            [sys.executable, "-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
            env=get_default_environment()
            | {
                "DONA_MARIA_DB_PATH": str(database),
                "DONA_MARIA_WORKSPACE_ID": workspace,
                "DONA_MARIA_MODE": "ATTENDANCE",
            },
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            stdout = BufferedByteReceiveStream(process.stdout)
            await process.stdin.send(json.dumps(initialize).encode() + b"\n")
            assert json.loads(await stdout.receive_until(b"\n", 1_000_000))["id"] == 1
            await process.stdin.send(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            await process.stdin.send(
                b'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":' + parameters + b"}\n"
            )
            response = json.loads(await stdout.receive_until(b"\n", 1_000_000))
            if extra_byte:
                assert "excede" in response["error"]["message"]
            else:
                assert response["result"]["structuredContent"]["ok"]
            await process.stdin.send(b'{"jsonrpc":"2.0","id":3,"method":"ping"}\n')
            assert json.loads(await stdout.receive_until(b"\n", 1_000_000))["result"] == {}
            await process.stdin.aclose()
            await process.wait()


@pytest.mark.parametrize("invalid", ["database", "workspace", "mode", "other", "diagnostic"])
def test_startup_without_a_valid_private_binding_does_not_serve(pricing_workspace, invalid):
    from mcp.client.stdio import get_default_environment

    _, workspace, _, _, _, database = pricing_workspace()
    before = database.read_bytes()
    binding = {
        "DONA_MARIA_DB_PATH": str(database),
        "DONA_MARIA_WORKSPACE_ID": workspace,
        "DONA_MARIA_MODE": "ATTENDANCE",
    }
    if invalid in ("database", "workspace", "mode"):
        binding.pop(
            {
                "database": "DONA_MARIA_DB_PATH",
                "workspace": "DONA_MARIA_WORKSPACE_ID",
                "mode": "DONA_MARIA_MODE",
            }[invalid]
        )
    elif invalid == "other":
        binding["DONA_MARIA_WORKSPACE_ID"] = "00000000-0000-4000-8000-000000000002"
    else:
        binding["DONA_MARIA_MODE"] = "DIAGNOSTIC"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-m", "dona_maria.launcher"],
        env=get_default_environment() | binding,
        input=b"",
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode != 0
    assert result.stdout == b""
    assert "Atendimento indisponível" in result.stderr.decode("utf-8")
    assert database.read_bytes() == before
    assert workspace.encode() not in result.stderr
    assert str(database).encode() not in result.stderr
    assert b"Traceback" not in result.stderr
