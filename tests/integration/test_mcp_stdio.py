import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import anyio
import pytest
from anyio.streams.buffered import BufferedByteReceiveStream
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client
from mcp.shared.exceptions import MCPError
from mcp.types import LATEST_PROTOCOL_VERSION


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_missing_database_config_exits_without_stdout_or_default_database(tmp_path):
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env=get_default_environment(),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "Configure DONA_MARIA_DB_PATH" in result.stderr
    assert "Traceback" not in result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.anyio
async def test_official_client_discovers_and_calls_the_real_stdio_server(tmp_path):
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/s00_missing_workspace.json").read_text("utf-8")
    )
    database = tmp_path / "synthetic.sqlite3"
    sqlite3.connect(database).close()
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )

    with anyio.fail_after(15):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                print(f"SDK negotiated protocol: {initialized.protocol_version}")
                tools = (await session.list_tools()).tools
                assert initialized.server_info.name == "dona_maria"
                assert initialized.protocol_version
                assert [tool.name for tool in tools] == [
                    "get_business_state",
                    "get_inventory_snapshot",
                    "register_recipe_candidate",
                ]
                tool = tools[0]
                assert tool.input_schema["additionalProperties"] is False
                assert tool.annotations.read_only_hint is True
                assert tool.annotations.destructive_hint is False
                result = await session.call_tool(
                    "get_business_state", {"workspace_id": fixture["workspace_id"]}
                )

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "NOT_FOUND"
    assert result.structured_content["data"] is None
    assert result.structured_content["revision"] is None
    assert json.loads(result.content[0].text) == result.structured_content


@pytest.mark.anyio
async def test_invalid_calls_are_structured_and_the_server_remains_usable(tmp_path):
    database = tmp_path / "synthetic.sqlite3"
    sqlite3.connect(database).close()
    server = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env={"DONA_MARIA_DB_PATH": str(database)},
        cwd=tmp_path,
    )
    with anyio.fail_after(15):
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for arguments in [
                    {},
                    {"workspace_id": "invalid"},
                    {"workspace_id": 42},
                    {"workspace_id": "00000000-0000-4000-8000-000000000001", "confirm": True},
                ]:
                    result = await session.call_tool("get_business_state", arguments)
                    assert result.is_error is True
                    assert result.structured_content["error"]["code"] == "VALIDATION_ERROR"
                    assert result.structured_content["data"] is None
                with pytest.raises(MCPError, match="Ferramenta desconhecida"):
                    await session.call_tool("execute_sql", {"sql": "DROP TABLE workspaces"})
                recovered = await session.call_tool(
                    "get_business_state",
                    {"workspace_id": "00000000-0000-4000-8000-000000000001"},
                )
                assert recovered.structured_content["error"]["code"] == "NOT_FOUND"


@pytest.mark.anyio
async def test_storage_lock_does_not_block_mcp_ping_and_read_recovers(tmp_path):
    database = tmp_path / "locked.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY)")
        connection.commit()
        before = database.read_bytes()
        server = StdioServerParameters(
            command=sys.executable,
            args=["-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
            env={"DONA_MARIA_DB_PATH": str(database)},
            cwd=tmp_path,
        )
        with anyio.fail_after(15):
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    connection.execute("BEGIN EXCLUSIVE")
                    responses = []

                    async def read_state(*, task_status):
                        task_status.started()
                        responses.append(
                            await session.call_tool(
                                "get_business_state",
                                {"workspace_id": "00000000-0000-4000-8000-000000000001"},
                            )
                        )

                    try:
                        async with anyio.create_task_group() as tasks:
                            await tasks.start(read_state)
                            with anyio.fail_after(2):
                                await session.send_ping()
                            assert responses == []
                            connection.rollback()
                    finally:
                        connection.rollback()

    assert len(responses) == 1
    assert responses[0].structured_content["error"]["code"] == "NOT_FOUND"
    assert database.read_bytes() == before


@pytest.mark.anyio
async def test_stdout_is_only_protocol_stderr_accepts_logs_and_eof_exits_cleanly(tmp_path):
    database = tmp_path / "synthetic with spaces.sqlite3"
    sqlite3.connect(database).close()
    before = database.read_bytes()
    environment = get_default_environment() | {"DONA_MARIA_DB_PATH": str(database)}
    with anyio.fail_after(15):
        async with await anyio.open_process(
            [sys.executable, "-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
            cwd=tmp_path,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            stdout = BufferedByteReceiveStream(process.stdout)
            messages = []

            async def exchange(message):
                await process.stdin.send((json.dumps(message) + "\n").encode("utf-8"))
                while True:
                    # Qualquer log/plaintext em stdout torna este decode uma falha.
                    response = json.loads(await stdout.receive_until(b"\n", 1_000_000))
                    messages.append(response)
                    assert response["jsonrpc"] == "2.0"
                    if response.get("id") == message["id"]:
                        return response

            initialized = await exchange(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": LATEST_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "synthetic-s00-wire-test", "version": "1"},
                    },
                }
            )
            assert initialized["result"]["serverInfo"]["name"] == "dona_maria"
            await process.stdin.send(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            called = await exchange(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "get_business_state",
                        "arguments": {"workspace_id": "00000000-0000-4000-8000-000000000001"},
                    },
                }
            )
            assert called["result"]["isError"] is True
            assert called["result"]["structuredContent"]["error"]["code"] == "NOT_FOUND"
            await process.stdin.aclose()
            assert await process.wait() == 0
            # Conferir também qualquer conteúdo restante após o último resultado.
            remaining = stdout.buffer
            async for chunk in process.stdout:
                remaining += chunk
            for line in remaining.splitlines():
                assert json.loads(line)["jsonrpc"] == "2.0"
            stderr = b""
            async for chunk in process.stderr:
                stderr += chunk
            assert b"Servidor Dona Maria iniciado" in stderr
            assert b"Traceback" not in stderr

    assert len(messages) >= 2
    assert database.read_bytes() == before
