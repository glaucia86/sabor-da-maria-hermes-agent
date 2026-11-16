"""Correlate original host evidence without inventing model calls or error codes.

Absent evidence stays pending; malformed or contradictory evidence fails closed.
"""

import json
from hashlib import sha256

from audit import events, tool_result
from pydantic import ValidationError

from dona_maria.business_state import ATTENDANCE_TOOLS

PREFIX = "mcp__dona_maria__"
CATALOG = set(ATTENDANCE_TOOLS)
READS = {
    PREFIX + name
    for name in CATALOG
    if name not in {"propose_user_change", "calculate_pricing_scenarios"}
}


def checked_probe(probe, binding, fingerprint):
    assert probe["kind"] == "REAL_MCP_STDIO_OPERATOR_PROBE"
    assert probe["model_generated"] is False
    assert probe["binding"] == binding
    assert probe["identity"]["fingerprint"] == fingerprint
    assert {tool["name"] for tool in probe["catalog"]["tools"]} == CATALOG
    assert len(probe["catalog"]["tools"]) == len(CATALOG)
    assert probe["before"] == probe["after"]
    return probe["calls"]


def reviewed_message(trace, locator, role):
    matches = [m for m in trace["messages"] if m["id"] == locator["message_id"]]
    assert len(matches) == 1
    message = matches[0]
    assert message["role"] == role
    assert sha256(message["content"].encode("utf-8")).hexdigest() == locator["sha256"]
    return trace["messages"].index(message)


def promotion_refusal(trace, after, probe, review, binding, fingerprint):
    if probe is None or review is None:
        return None
    try:
        probe_calls = checked_probe(probe, binding, fingerprint)
        assert len(probe_calls) == 3
        assert [c["name"] for c in probe_calls] == ["get_business_state"] * 3
        assert [c["arguments"] for c in probe_calls] == [{}, {"context_mode": "REAL"}, {}]
        before, refusal, following = [c["result"]["structured_content"] for c in probe_calls]
        assert refusal["ok"] is False
        assert before == following == probe["after"]["attendance"] == after["attendance"]
        assert before["ok"] is True
        assert before["data"]["context_mode"] == "SIMULATION"
        assert before["data"]["hypothetical"] is True
        assert review["actor"] == "AUTOMATED_DELEGATED" and review["human_review"] is False
        assert review["result"] == "PASS"
        assert set(review["judgments"]) == {
            "request_promotes_fiction",
            "response_refuses_promotion",
        }
        assert all(value is True for value in review["judgments"].values())
        request_index = reviewed_message(trace, review["request"], "user")
        response_index = reviewed_message(trace, review["response"], "assistant")
        assert request_index < response_index
        calls = events({"messages": trace["messages"][request_index:]})
        assert calls and all(c["responded"] for c in calls)
        assert all(c["name"] in READS for c in calls)
        assert any(
            c["name"] == PREFIX + "get_business_state"
            and c["arguments"] == {}
            and tool_result(c["output"]) == after["attendance"]
            for c in calls
        )
        return True
    except (AssertionError, KeyError, TypeError, ValueError):
        return False


def transport_recovery(calls, after, marker, binding):
    if marker is None:
        return None
    try:
        assert marker["kind"] == "REAL_MCP_LOST_RESPONSE" and marker["binding"] == binding
        request, original, emitted = [
            marker[k] for k in ("request", "original_response", "emitted_response")
        ]
        assert request["method"] == "tools/call"
        assert request["id"] == original["id"] == emitted["id"]
        assert request["params"]["name"] == "propose_user_change"
        arguments = request["params"]["arguments"]
        operation = arguments["operation_id"]
        assert emitted["error"]["code"] == -32000
        assert emitted["error"]["data"] == {
            "kind": "CONTROLLED_LOST_RESPONSE",
            "operation_id": operation,
        }
        result = original["result"]["structuredContent"]
        assert result["ok"] is True and original["result"]["isError"] is False
        candidates = [
            (i, c)
            for i, c in enumerate(calls)
            if c["name"] == PREFIX + "propose_user_change" and c["arguments"] == arguments
        ]
        assert len(candidates) >= 2
        failed_index, failed = candidates[0]
        # Hermes serializes MCPError through _mcp_call_failed_message, dropping
        # its numeric code/data. Require exact rendering AND original sidecar.
        raw = failed["output"]
        if isinstance(raw, str):
            raw = json.JSONDecoder().raw_decode(raw[raw.index("{") :])[0]
        assert raw == {"error": "MCP call failed: MCPError: " + emitted["error"]["message"]}
        replay_index, replay = candidates[1]
        replay_result = tool_result(replay["output"])
        assert replay_result["ok"] is True
        assert replay_result["data"]["proposal"] == result["data"]["proposal"]
        assert any(
            c["name"] == PREFIX + "get_business_state"
            and c["arguments"] == {}
            and tool_result(c["output"]).get("ok") is True
            for c in calls[failed_index + 1 : replay_index]
        )
        proposals = [p for p in after["proposals"] if p["operation_id"] == operation]
        assert len(proposals) == 1 and proposals[0]["status"] == "APPROVED"
        return True
    except (AssertionError, KeyError, TypeError, ValueError):
        return False


def permanent_failure(calls, probe, binding, fingerprint):
    if probe is None:
        return None
    try:
        probe_calls = checked_probe(probe, binding, fingerprint)
        assert len(probe_calls) == 1
        record = probe_calls[0]
        name, arguments = record["name"], record["arguments"]
        assert name in CATALOG
        try:
            ATTENDANCE_TOOLS[name][0].model_validate(arguments)
        except ValidationError:
            pass
        else:
            return False
        result = record["result"]["structured_content"]
        assert result["ok"] is False
        matches = [
            (i, c)
            for i, c in enumerate(calls)
            if c["name"] == PREFIX + name
            and c["arguments"] == arguments
            and tool_result(c["output"]) == result
        ]
        assert matches
        i, _ = matches[0]
        normalized = {k: v for k, v in arguments.items() if k != "operation_id"}
        assert not any(
            c["name"] == PREFIX + name
            and {k: v for k, v in c["arguments"].items() if k != "operation_id"} == normalized
            for c in calls[i + 1 :]
        )
        return True
    except (AssertionError, KeyError, TypeError, ValueError):
        return False


def proposal_expiration(calls, before, after):
    if before is None or after is None:
        return None
    try:
        assert before["business"]["revision"] == after["business"]["revision"]
        assert before["inventory"] == after["inventory"]
        pending = {
            before["proposals"][p["proposal"] - 1]["id"]
            for p in before["attendance"]["data"]["proposals"]
            if p["status"] == "PENDING"
        }
        expired = {
            after["proposals"][p["proposal"] - 1]["id"]
            for p in after["attendance"]["data"]["proposals"]
            if p["status"] == "EXPIRED"
        }
        assert pending & expired
        earlier = {p["id"]: p for p in before["proposals"]}
        later = {p["id"]: p for p in after["proposals"]}
        for identifier in pending & expired:
            assert earlier[identifier]["hash"] == later[identifier]["hash"]
            assert later[identifier]["status"] != "APPROVED"
            assert not any(
                p["operation_id"] == later[identifier]["operation_id"] and p["status"] == "APPROVED"
                for p in after["proposals"]
            )
        reads = [
            tool_result(c["output"])
            for c in calls
            if c["name"] == PREFIX + "get_business_state" and c["arguments"] == {}
        ]
        assert any(
            first == before["attendance"] and after["attendance"] in reads[i + 1 :]
            for i, first in enumerate(reads)
        )
        return True
    except (AssertionError, KeyError, TypeError, ValueError, IndexError):
        return False


def quote_expiration(calls, before, after, final):
    if before is None or after is None:
        return None
    try:
        assert after == final
        assert before["business"]["revision"] == after["business"]["revision"]
        assert before["inventory"] == after["inventory"]
        earlier, later = before["business"]["data"], after["business"]["data"]
        # Quote identity includes its immutable version, including historical entries.
        confirmed = {
            (q["id"], q["version"]): q
            for q in earlier["complement_quotes"]
            if q["status"] == "CONFIRMED"
        }
        expired = [
            q
            for q in later["complement_quotes"]
            if q["status"] == "EXPIRED" and (q["id"], q["version"]) in confirmed
        ]
        assert expired
        assert all(
            q["confirmation"] == confirmed[(q["id"], q["version"])]["confirmation"] for q in expired
        )
        assert earlier["evaluation"]["purchase_status"] == "CONFIRMED"
        assert later["evaluation"]["purchase_status"] == "PENDING"
        assert any("QUOTE_EXPIRED" in gap for gap in later["evaluation"]["gaps"])
        for collection in ("acceptances", "pricing_calculations", "menu_decisions"):
            valid = {v["id"] for v in earlier[collection] if v["validity"] == "VALID"}
            assert valid and valid <= {
                v["id"] for v in later[collection] if v["validity"] != "VALID"
            }
        assert not later["menu"]
        reads = [
            tool_result(c["output"])
            for c in calls
            if c["name"] == PREFIX + "get_business_state" and c["arguments"] == {}
        ]
        assert any(
            first == before["attendance"] and after["attendance"] in reads[i + 1 :]
            for i, first in enumerate(reads)
        )
        return True
    except (AssertionError, KeyError, TypeError, ValueError):
        return False
