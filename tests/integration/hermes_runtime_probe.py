"""Executado pelo Hermes instalado; sem LLM, rede externa ou escrita no negócio."""

import json
import time
from types import ModuleType, SimpleNamespace


def main():
    import sys

    from agent.agent_runtime_helpers import invoke_tool
    from agent.tool_executor import (
        _resolve_sequential_dispatch,
        _run_agent_tool_execution_middleware,
        _ToolCallRef,
    )
    from agent.transports.types import NormalizedResponse, ToolCall
    from agent.turn_response_intake import _fire_post_api_request_hook
    from hermes_cli.config import load_config_readonly
    from hermes_cli.plugins import (
        _dispatch_pre_tool_call_hooks,
        discover_plugins,
        get_plugin_manager,
    )
    from toolsets import validate_toolset

    assert load_config_readonly()["plugins"]["isolation"] == "host"
    # Reproduz o conflito no processo pai; o host precisa ter seu próprio pacote.
    foreign = ModuleType("dona_maria")
    foreign.__file__ = "synthetic-foreign-checkout/__init__.py"
    sys.modules["dona_maria"] = foreign
    discover_plugins()
    loaded = get_plugin_manager()._plugins["dona-maria-mediated-research"]
    assert loaded.enabled and not loaded.error
    assert set(loaded.tools_registered) == {"search_culinary_sources", "extract_culinary_source"}
    assert validate_toolset("culinary_research")
    assert sys.modules["dona_maria"] is foreign
    from model_tools import get_tool_definitions

    catalog = get_tool_definitions(
        enabled_toolsets=["culinary_research", "desktop_ui"],
        disabled_toolsets=["desktop_ui"],
        quiet_mode=True,
    )
    names = {tool["function"]["name"] for tool in catalog}
    assert {"search_culinary_sources", "extract_culinary_source"} <= names
    assert not {"desktop_preview", "drive_preview"} & names

    calls = []
    agent = SimpleNamespace(
        session_id="synthetic-session",
        platform="desktop",
        model="synthetic",
        provider="synthetic",
        base_url="",
        api_mode="chat_completions",
        _current_api_request_id="synthetic-request",
        _current_turn_id="synthetic-turn",
        _api_response_payload_for_hook=lambda *a, **kw: {},
        _usage_summary_for_api_request_hook=lambda *a: {},
        read_preview_callback=lambda *a, **kw: calls.append("desktop_preview"),
        drive_preview_callback=lambda *a, **kw: calls.append("drive_preview"),
    )
    for name in ("desktop_preview", "drive_preview", "web_search", "search_culinary_sources"):
        args = {"action": "read"}
        message = NormalizedResponse(
            content="",
            finish_reason="tool_calls",
            tool_calls=[ToolCall(id="call", name=name, arguments=json.dumps(args))],
        )
        _fire_post_api_request_hook(
            agent,
            None,
            message,
            "tool_calls",
            api_messages=[],
            api_call_count=1,
            api_duration=0,
            api_start_time=time.time(),
            api_request_id="synthetic-request",
            effective_task_id="task",
            turn_id="synthetic-turn",
        )
        verdict, _ = _dispatch_pre_tool_call_hooks(
            name,
            args,
            session_id=agent.session_id,
            api_request_id=agent._current_api_request_id,
            tool_call_id="call",
        )
        if name == "search_culinary_sources":
            assert verdict is None  # Controle positivo: o observer precisa ter funcionado.
            continue
        assert verdict is not None
        assert json.loads(invoke_tool(agent, name, args, "task", tool_call_id="call"))["error"]
        if name in {"desktop_preview", "drive_preview"}:
            dispatch = _resolve_sequential_dispatch(
                agent, _ToolCallRef(name, args, "task", "call", []), []
            )
            result = _run_agent_tool_execution_middleware(
                agent,
                function_name=name,
                function_args=args,
                effective_task_id="task",
                tool_call_id="call",
                execute=dispatch.execute,
            )
            assert result.blocked and json.loads(result.result)["error"]
    assert calls == []
    print("HERMES_RUNTIME_PASS")


if __name__ == "__main__":
    main()
