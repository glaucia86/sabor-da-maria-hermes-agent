"""Contrato público de registro/callbacks do adaptador Hermes; sem importar o host."""

from threading import Event, Thread
from types import SimpleNamespace

import pytest

from dona_maria.hermes_policy import register


def callbacks():
    hooks = {}
    register(SimpleNamespace(register_hook=lambda event, handler: hooks.update({event: handler})))
    return hooks


def provider_message(name):
    return SimpleNamespace(
        tool_calls=[
            SimpleNamespace(
                id="synthetic-call", function=SimpleNamespace(name=name, arguments="{}")
            )
        ]
    )


def test_original_forbidden_name_cannot_become_an_authorized_read_after_host_repair():
    hooks = callbacks()
    context = {"session_id": "synthetic-session", "api_request_id": "synthetic-request"}
    hooks["post_api_request"](
        **context, assistant_message=provider_message("mcp__dona_maria__accept_recipe")
    )
    result = hooks["pre_tool_call"](
        **context,
        tool_call_id="synthetic-call",
        tool_name="mcp__dona_maria__evaluate_recipe_feasibility",
        args={},
    )
    assert result == {
        "action": "block",
        "message": "Esta ação não está disponível neste atendimento.",
    }


@pytest.mark.parametrize(
    "name",
    [
        "get_business_state",
        "get_inventory_snapshot",
        "evaluate_recipe_feasibility",
        "evaluate_purchase_plan",
        "propose_user_change",
        "calculate_pricing_scenarios",
    ],
)
def test_exact_read_observed_in_the_same_request_can_execute(name):
    hooks = callbacks()
    context = {"session_id": "synthetic-session", "api_request_id": "synthetic-request"}
    name = "mcp__dona_maria__" + name
    hooks["post_api_request"](**context, assistant_message=provider_message(name))
    assert (
        hooks["pre_tool_call"](**context, tool_call_id="synthetic-call", tool_name=name, args={})
        is None
    )


def test_missing_observation_or_another_request_is_refused():
    hooks = callbacks()
    context = {"session_id": "synthetic-session", "api_request_id": "synthetic-request"}
    name = "mcp__dona_maria__get_business_state"
    assert (
        hooks["pre_tool_call"](**context, tool_call_id="synthetic-call", tool_name=name)["action"]
        == "block"
    )
    hooks["post_api_request"](**context, assistant_message=provider_message(name))
    context["api_request_id"] = "another-request"
    assert (
        hooks["pre_tool_call"](**context, tool_call_id="synthetic-call", tool_name=name)["action"]
        == "block"
    )


@pytest.mark.parametrize("isolated", [False, True])
@pytest.mark.parametrize("original", ["mcp__dona_maria__get_business_state", "forbidden_tool"])
def test_host_record_uses_original_normalized_name_without_authorizing_plain_dicts(
    isolated, original
):
    hooks = callbacks()
    context = {"session_id": "isolated-session", "api_request_id": "isolated-request"}
    record = type("Record", (dict,), {"__module__": "hermes_cli.plugin_host_wire"})
    call = {"id": "call", "name": original, "arguments": "{}", "provider_data": None}
    hooks["post_api_request"](
        **context, assistant_message={"tool_calls": [record(call) if isolated else call]}
    )
    result = hooks["pre_tool_call"](
        **context, tool_call_id="call", tool_name="mcp__dona_maria__get_business_state"
    )
    if isolated and original == "mcp__dona_maria__get_business_state":
        assert result is None
    else:
        assert result["action"] == "block"


@pytest.mark.parametrize("function", [None, {}, {"name": "forbidden_tool"}])
def test_flat_name_does_not_override_present_function_in_host_record(function):
    hooks = callbacks()
    context = {"session_id": "isolated-session", "api_request_id": "isolated-request"}
    record = type("Record", (dict,), {"__module__": "hermes_cli.plugin_host_wire"})
    name = "mcp__dona_maria__get_business_state"
    hooks["post_api_request"](
        **context,
        assistant_message={"tool_calls": [record(id="call", name=name, function=function)]},
    )
    assert (
        hooks["pre_tool_call"](**context, tool_call_id="call", tool_name=name)["action"] == "block"
    )


@pytest.mark.parametrize("name", ["search_culinary_sources", "extract_culinary_source"])
def test_mediated_research_requires_the_exact_original_tool_name(name):
    hooks = callbacks()
    context = {"session_id": "research-session", "api_request_id": "research-request"}
    hooks["post_api_request"](**context, assistant_message=provider_message(name))
    assert hooks["pre_tool_call"](**context, tool_call_id="synthetic-call", tool_name=name) is None
    hooks["post_api_request"](**context, assistant_message=provider_message(name))
    context["api_request_id"] = "another-request"
    assert (
        hooks["pre_tool_call"](**context, tool_call_id="synthetic-call", tool_name=name)["action"]
        == "block"
    )


def test_ambiguous_ids_or_malformed_observation_cannot_reuse_an_authorized_call():
    hooks = callbacks()
    context = {"session_id": "synthetic-session", "api_request_id": "synthetic-request"}
    name = "mcp__dona_maria__get_business_state"
    message = provider_message(name)
    message.tool_calls.append(provider_message("mcp__dona_maria__accept_recipe").tool_calls[0])
    hooks["post_api_request"](**context, assistant_message=message)
    assert (
        hooks["pre_tool_call"](**context, tool_call_id="synthetic-call", tool_name=name)["action"]
        == "block"
    )
    hooks["post_api_request"](**context, assistant_message=provider_message(name))
    hooks["post_api_request"](**context, assistant_message=SimpleNamespace(tool_calls=42))
    assert (
        hooks["pre_tool_call"](**context, tool_call_id="synthetic-call", tool_name=name)["action"]
        == "block"
    )


def test_slow_observation_cannot_reappear_after_eviction():
    hooks = callbacks()
    started, release = Event(), Event()
    name = "mcp__dona_maria__get_business_state"

    class DelayedMessage:
        @property
        def tool_calls(self):
            started.set()
            assert release.wait(5)
            return provider_message(name).tool_calls

    worker = Thread(
        target=hooks["post_api_request"],
        kwargs={
            "session_id": "synthetic-session",
            "api_request_id": "slow",
            "assistant_message": DelayedMessage(),
        },
    )
    worker.start()
    try:
        assert started.wait(5)
        for index in range(129):
            hooks["post_api_request"](
                session_id="synthetic-session",
                api_request_id=str(index),
                assistant_message=provider_message(name),
            )
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert (
        hooks["pre_tool_call"](
            session_id="synthetic-session",
            api_request_id="slow",
            tool_call_id="synthetic-call",
            tool_name=name,
        )["action"]
        == "block"
    )


def test_old_observation_eviction_fails_closed_without_exposing_names_or_ids():
    hooks = callbacks()
    name = "mcp__dona_maria__get_business_state"
    for index in range(129):
        hooks["post_api_request"](
            session_id="synthetic-session",
            api_request_id=str(index),
            assistant_message=provider_message(name),
        )
    assert (
        hooks["pre_tool_call"](
            session_id="synthetic-session",
            api_request_id="0",
            tool_call_id="synthetic-call",
            tool_name=name,
        )["action"]
        == "block"
    )
    assert (
        hooks["pre_tool_call"](
            session_id="synthetic-session",
            api_request_id="128",
            tool_call_id="synthetic-call",
            tool_name=name,
        )
        is None
    )
