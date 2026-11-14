"""Adaptador MCP oficial v2, exclusivamente stdio; regras no serviço Python."""

import asyncio
import json
import logging
import os
import sys
from contextlib import closing
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
    ToolAnnotations,
    jsonrpc_message_adapter,
)

from dona_maria.business_state import (
    ATTENDANCE_TOOLS,
    MAX_CALL_BYTES,
    AttendanceService,
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
    """Seam técnico legado para testes locais; não é o launcher do atendimento."""
    server = create_server(BusinessStateReader(SQLiteWorkspaceRepository(database)))
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def create_attendance_server(service: AttendanceService) -> Server:
    async def list_tools(ctx, params):
        return ListToolsResult(
            tools=[
                Tool(
                    name=name,
                    description=description,
                    input_schema=schema.model_json_schema(),
                    annotations=ToolAnnotations(
                        read_only_hint=True,
                        destructive_hint=False,
                        idempotent_hint=True,
                        open_world_hint=False,
                    ),
                )
                for name, (schema, description) in ATTENDANCE_TOOLS.items()
            ]
        )

    async def call_tool(ctx, params):
        started = perf_counter()
        result = await asyncio.to_thread(service.call, params.name, params.arguments or {})
        logging.getLogger(__name__).info(
            json.dumps(
                {
                    "event": "attendance_read",
                    "correlation_id": str(uuid4()),
                    "tool": params.name if params.name in ATTENDANCE_TOOLS else "disabled",
                    "result": "SUCCESS" if result["ok"] else "REFUSED",
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                }
            )
        )
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
            structured_content=result,
            is_error=not result["ok"],
        )

    return Server(
        "dona_maria",
        version=version("sabor-da-maria"),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve_attendance(service: AttendanceService) -> None:
    server = create_attendance_server(service)
    # O SDK desvia fd 1; o erro do receptor usa uma cópia privada do canal original.
    with closing(os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")) as output:
        async with stdio_server(stdin=_BoundedStdin(output)) as (read, write):
            await server.run(read, write, server.create_initialization_options())


MAX_FRAME_BYTES = 512 * 1024


def _raw_parameter_size(text: str) -> int:
    """Conta o trecho recebido, inclusive espaços e escapes que o SDK normalizaria."""
    decoder = json.JSONDecoder()
    offset = text.index("{") + 1
    size = 0
    while True:
        while text[offset].isspace():
            offset += 1
        if text[offset] == "}":
            return size
        key, offset = decoder.raw_decode(text, offset)
        while text[offset].isspace():
            offset += 1
        offset += 1  # O JSON já foi validado; este caractere é ':'
        start = offset
        while text[offset].isspace():
            offset += 1
        _, offset = decoder.raw_decode(text, offset)
        if key == "params":
            size = max(size, len(text[start:offset].encode("utf-8")))
        while text[offset].isspace():
            offset += 1
        if text[offset] == ",":
            offset += 1


def _collections_fit(parameters) -> bool:
    pending = [parameters]
    while pending:
        value = pending.pop()
        if isinstance(value, (dict, list)):
            if len(value) > 200:
                return False
            pending.extend(value.values() if isinstance(value, dict) else value)
    return True


class _BoundedStdin:
    """O SDK 2.3.0 não limita readline; recusa o frame antes de materializá-lo inteiro."""

    def __init__(self, output):
        self.output = output

    def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            frame = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_FRAME_BYTES + 1)
            if not frame:
                raise StopAsyncIteration
            if len(frame) > MAX_FRAME_BYTES:
                self._refuse("O pedido excede o limite. Envie um pedido menor.")
                # Fecha sem drenar uma entrada excessiva nem truncar silenciosamente.
                raise StopAsyncIteration
            try:
                text = frame.decode("utf-8")
                message = jsonrpc_message_adapter.validate_json(text, by_name=False)
                if getattr(message, "method", None) == "tools/call":
                    if _raw_parameter_size(text) > MAX_CALL_BYTES or not _collections_fit(
                        message.params
                    ):
                        self._refuse("O pedido excede o limite. Envie um pedido menor.", message.id)
                        continue
                return text
            except (UnicodeError, ValueError, RecursionError):
                self._refuse("Não foi possível usar esses dados. Revise o pedido.")
                raise StopAsyncIteration from None

    def _refuse(self, message, identifier=None):
        self.output.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "error": {"code": -32600, "message": message},
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        self.output.flush()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("mcp").setLevel(logging.CRITICAL)
    try:
        service = AttendanceService(
            Path(os.environ["DONA_MARIA_DB_PATH"]),
            os.environ["DONA_MARIA_WORKSPACE_ID"],
            os.environ["DONA_MARIA_MODE"],
        )
    except (KeyError, ValueError):
        raise SystemExit("Atendimento indisponível. Peça auxílio à pessoa operadora.") from None
    logging.getLogger(__name__).info(
        json.dumps(
            {
                "event": "startup",
                "message": "Servidor Dona Maria iniciado em stdio.",
            }
        )
    )
    try:
        asyncio.run(serve_attendance(service))
    except Exception:
        raise SystemExit("Atendimento interrompido. Peça auxílio à pessoa operadora.") from None


if __name__ == "__main__":
    main()
