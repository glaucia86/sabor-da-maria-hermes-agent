"""Adaptador MCP oficial v2, exclusivamente stdio; regras no serviço Python."""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations

from dona_maria.business_state import (
    BusinessStateReader,
    GetBusinessStateRequest,
    GetInventorySnapshotRequest,
    ReadErrorEnvelope,
)
from dona_maria.candidates import RegisterCandidateRequest
from dona_maria.ingredients import ConversionRequest, ResolveIngredientRequest
from dona_maria.persistence import SQLiteWorkspaceRepository
from dona_maria.pricing import CalculatePricingRequest, SaveMenuDecisionRequest
from dona_maria.production import (
    AcceptanceRequest,
    FeasibilityRequest,
    FeedbackRequest,
    KitchenFactsRequest,
    PlanRequest,
    PreferencesRequest,
)
from dona_maria.quotes import ConfirmQuoteRequest, RegisterQuoteRequest

PRODUCTION_TOOLS = [
    (
        "record_user_preferences",
        PreferencesRequest,
        False,
        "Registra LIKE/AVOID com evidência humana e substituição explícita; "
        "AVOID incompatível retira a receita do plano e invalida decisões; "
        "LIKE não confirma aptidão.",
    ),
    (
        "register_complement_quote",
        RegisterQuoteRequest,
        False,
        "Registra oferta pesquisada e lacunas como estimativa; não confirma preço nem compra.",
    ),
    (
        "confirm_complement_quote",
        ConfirmQuoteRequest,
        False,
        "Confirma versão, quantidade, embalagem, preço, encargos e disponibilidade "
        "com fala humana específica; não compra.",
    ),
    (
        "resolve_recipe_ingredient",
        ResolveIngredientRequest,
        False,
        "Resolve identidade ou cria complemento sem colisão; devolve ID e preserva origem.",
    ),
    (
        "record_ingredient_conversion",
        ConversionRequest,
        False,
        "Registra conversão por ingrediente/contexto/escopo; compra histórica exige fala humana.",
    ),
    (
        "record_recipe_feedback",
        FeedbackRequest,
        False,
        "Registra interesse ou recusa; não aceita receita.",
    ),
    (
        "record_kitchen_facts",
        KitchenFactsRequest,
        False,
        "Registra fatos tipados com evidência humana.",
    ),
    (
        "set_production_plan",
        PlanRequest,
        False,
        "Confirma lotes inteiros e substitui o rascunho completo.",
    ),
    (
        "evaluate_recipe_feasibility",
        FeasibilityRequest,
        True,
        "Avalia condições na escala do plano atual.",
    ),
    (
        "evaluate_purchase_plan",
        GetBusinessStateRequest,
        True,
        "Avalia demanda de todos os itens ativos, sem comprar.",
    ),
    (
        "accept_recipe",
        AcceptanceRequest,
        False,
        "Aceita somente após resumo atual e manifestação inequívoca.",
    ),
    (
        "calculate_pricing_scenarios",
        CalculatePricingRequest,
        False,
        "Persiste CMV, mínimo e cenários com aceite vigente; não escolhe preço.",
    ),
    (
        "save_menu_decision",
        SaveMenuDecisionRequest,
        False,
        "Registra somente escolha humana de cenário ou preço em centavos acima do piso.",
    ),
]


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
                ),
                Tool(
                    name="get_inventory_snapshot",
                    description="Lê itens, custos e diagnósticos da fotografia da despensa.",
                    input_schema=GetInventorySnapshotRequest.model_json_schema(),
                    output_schema=ReadErrorEnvelope.model_json_schema(),
                    annotations=ToolAnnotations(
                        read_only_hint=True,
                        destructive_hint=False,
                        idempotent_hint=True,
                        open_world_hint=False,
                    ),
                ),
                Tool(
                    name="register_recipe_candidate",
                    description="Registra candidata com fontes e lacunas, sem aceite ou preço.",
                    input_schema=RegisterCandidateRequest.model_json_schema(),
                    output_schema=ReadErrorEnvelope.model_json_schema(),
                    annotations=ToolAnnotations(
                        read_only_hint=False,
                        destructive_hint=False,
                        idempotent_hint=True,
                        open_world_hint=False,
                    ),
                ),
            ]
            + [
                Tool(
                    name=name,
                    description=description,
                    input_schema=schema.model_json_schema(),
                    output_schema=ReadErrorEnvelope.model_json_schema(),
                    annotations=ToolAnnotations(
                        read_only_hint=read_only,
                        destructive_hint=False,
                        idempotent_hint=True,
                        open_world_hint=False,
                    ),
                )
                for name, schema, read_only, description in PRODUCTION_TOOLS
            ]
        )

    async def call_tool(ctx, params):
        handlers = {
            "get_business_state": reader.get_business_state,
            "get_inventory_snapshot": reader.get_inventory_snapshot,
            "register_recipe_candidate": reader.register_recipe_candidate,
        }
        handlers.update({name: getattr(reader, name) for name, *_ in PRODUCTION_TOOLS})
        if params.name not in handlers:
            raise MCPError(code=-32602, message="Ferramenta desconhecida.")
        started = perf_counter()
        envelope = await asyncio.to_thread(handlers[params.name], params.arguments or {})
        logging.getLogger(__name__).info(
            json.dumps(
                {
                    "event": "mcp_call",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "correlation_id": envelope["operation_id"] or str(uuid4()),
                    "workspace_id": envelope["workspace_id"],
                    "tool": params.name,
                    "revision": envelope["revision"],
                    "result": "SUCCESS" if envelope["ok"] else envelope["error"]["code"],
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                },
                ensure_ascii=False,
            )
        )
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))],
            structured_content=envelope,
            is_error=not envelope["ok"],
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    database = os.environ.get("DONA_MARIA_DB_PATH")
    if not database:
        raise SystemExit("Configure DONA_MARIA_DB_PATH antes de iniciar o servidor.")
    logging.getLogger(__name__).info(
        json.dumps(
            {
                "event": "startup",
                "message": "Servidor Dona Maria iniciado em stdio.",
            }
        )
    )
    asyncio.run(serve(Path(database)))


if __name__ == "__main__":
    main()
