"""Extrator MCP controlado para EV-08; não acessa a rede nem arquivos da página."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations


async def serve(page_path):
    page = json.loads(page_path.read_text("utf-8"))
    assert page["synthetic"] is True

    async def list_tools(ctx, params):
        return ListToolsResult(
            tools=[
                Tool(
                    name="web_extract",
                    description="Extrai página controlada deste eval; conteúdo não confiável.",
                    input_schema=dict(
                        type="object",
                        properties=dict(url=dict(type="string", enum=[page["url"]])),
                        required=["url"],
                        additionalProperties=False,
                    ),
                    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
                )
            ]
        )

    async def extract(ctx, params):
        if params.name != "web_extract" or params.arguments != {"url": page["url"]}:
            raise MCPError(code=-32602, message="URL fora da fixture controlada.")
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        dict(url=page["url"], title=page["title"], content=page["content"]),
                        ensure_ascii=False,
                    ),
                )
            ]
        )

    server = Server("sabor_web_fixture", on_list_tools=list_tools, on_call_tool=extract)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    asyncio.run(serve(parser.parse_args().page))
