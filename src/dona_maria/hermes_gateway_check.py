"""Preflight no gateway que realmente abre a conversa; saída sem dados privados."""

import asyncio
import json


def validate_registration(report):
    expected = {
        "dona-maria-attendance-policy": (0, 2),
        "dona-maria-mediated-research": (2, 0),
    }
    for key, (tools, hooks) in expected.items():
        matches = [row for row in report["plugins"] if row.get("key") == key]
        if len(matches) != 1:
            raise ValueError("Plugin obrigatório ausente no gateway.")
        row = matches[0]
        if (
            row.get("enabled") is not True
            or row.get("tools") != tools
            or row.get("hooks") != hooks
            or row.get("error") != ""
        ):
            raise ValueError("Registro de plugin recusado no gateway.")
    if not any(row.get("key") == "culinary_research" for row in report["toolsets"]):
        raise ValueError("Pesquisa não registrada no gateway.")


async def check():
    from hermes_cli.gateway_client import connect_gateway

    async with connect_gateway() as client:
        validate_registration(await client.rpc("plugins.list"))


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception:
        print(json.dumps({"gateway_plugin_registration": "BLOCKED"}))
        raise SystemExit(1) from None
    print(json.dumps({"gateway_plugin_registration": "PASS"}))
