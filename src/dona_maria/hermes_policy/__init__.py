"""Política de atendimento pelos hooks públicos do Hermes; não registra ferramentas."""

from collections import OrderedDict
from threading import Lock

ALLOWED = frozenset(
    "mcp__dona_maria__" + name
    for name in (
        "get_business_state",
        "get_inventory_snapshot",
        "evaluate_recipe_feasibility",
        "evaluate_purchase_plan",
        "propose_user_change",
        "calculate_pricing_scenarios",
    )
) | frozenset({"search_culinary_sources", "extract_culinary_source"})
REFUSAL = {"action": "block", "message": "Esta ação não está disponível neste atendimento."}


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def register(ctx):
    observed = OrderedDict()
    lock = Lock()

    def observe(
        *,
        session_id=None,
        api_request_id=None,
        assistant_message=None,
        **kwargs,
    ):
        if not all(isinstance(value, str) and value for value in (session_id, api_request_id)):
            return
        record = {}
        with lock:
            observed[(session_id, api_request_id)] = record
            # Evicção limita memória; uma observação ausente sempre resulta em recusa.
            while len(observed) > 128:
                observed.popitem(last=False)
        calls = _field(assistant_message, "tool_calls") or []
        if not isinstance(calls, (list, tuple)):
            return
        names = {}
        for call in calls:
            identifier = _field(call, "id")
            name = _field(_field(call, "function"), "name")
            if (
                type(call).__module__ == "hermes_cli.plugin_host_wire"
                and type(call).__name__ == "Record"
                and "function" not in call
            ):
                # O transporte serializa campos de ToolCall, mas não sua propriedade function.
                name = call.get("name")
            if isinstance(identifier, str) and identifier:
                names[identifier] = (
                    name
                    if isinstance(name, str) and name in ALLOWED and identifier not in names
                    else None
                )
        with lock:
            if observed.get((session_id, api_request_id)) is record:
                record.update(names)

    def guard(*, session_id=None, api_request_id=None, tool_call_id=None, tool_name=None, **kwargs):
        if not all(
            isinstance(value, str) and value
            for value in (
                session_id,
                api_request_id,
                tool_call_id,
                tool_name,
            )
        ):
            return dict(REFUSAL)
        with lock:
            original = observed.get((session_id, api_request_id), {}).get(tool_call_id)
        if tool_name not in ALLOWED or original != tool_name:
            return dict(REFUSAL)
        return None

    ctx.register_hook("post_api_request", observe)
    ctx.register_hook("pre_tool_call", guard)
