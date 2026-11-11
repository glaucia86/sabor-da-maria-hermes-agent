"""Adaptador MCP oficial v2, exclusivamente stdio e somente leitura em S00."""

import asyncio
import json
import logging
import os
from importlib.metadata import version
from pathlib import Path

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations

from dona_maria.business_state import (
    BusinessStateReader,
    GetBusinessStateRequest,
    ReadErrorEnvelope,
    SQLiteWorkspaceRepository,
)


def create_server(reader: BusinessStateReader) -> Server:
    async def list_tools(ctx, params):
        return ListToolsResult(
            tools=[
                Tool(
                    name="get_business_state",
                    description="Consulta o workspace configurado; nunca cria estado ou decisões.",
                    input_schema=GetBusinessStateRequest.model_json_schema(),
                    output_schema=ReadErrorEnvelope.model_json_schema(),
                    annotations=ToolAnnotations(
                        read_only_hint=True,
                        destructive_hint=False,
                        idempotent_hint=True,
                        open_world_hint=False,
                    ),
                )
            ]
        )

    async def call_tool(ctx, params):
        if params.name != "get_business_state":
            raise MCPError(code=-32602, message="Ferramenta desconhecida.")
        envelope = await asyncio.to_thread(reader.get_business_state, params.arguments or {})
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))],
            structured_content=envelope,
            is_error=True,
        )

    return Server(
        "dona_maria",
        version=version("sabor-da-maria"),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve(database: Path) -> None:
    server = create_server(BusinessStateReader(SQLiteWorkspaceRepository(database)))
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    database = os.environ.get("DONA_MARIA_DB_PATH")
    if not database:
        raise SystemExit("Configure DONA_MARIA_DB_PATH antes de iniciar o servidor.")
    logging.getLogger(__name__).info("Servidor Dona Maria iniciado em stdio, somente leitura S00.")
    asyncio.run(serve(Path(database)))


if __name__ == "__main__":
    main()
