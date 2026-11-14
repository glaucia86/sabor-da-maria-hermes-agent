"""Proxy de teste: servidor real; falha somente na fronteira de transporte.

Use exclusivamente banco sintético. Não é um launcher de produção.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from threading import Thread

from mcp.client.stdio import get_default_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument(
        "--fault", choices=["lost-success", "disconnect-calculation"], default="lost-success"
    )
    args = parser.parse_args()
    if not args.database.is_file() or not args.marker.parent.is_dir():
        parser.error("Prepare o banco sintético e o diretório de evidências primeiro.")
    pending = {}
    child = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=get_default_environment() | {"DONA_MARIA_DB_PATH": str(args.database.resolve())},
    )

    def emit(message):
        sys.stdout.buffer.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()

    def uncertain(identifier, operation_id):
        return dict(
            jsonrpc="2.0",
            id=identifier,
            error=dict(
                code=-32000,
                message="Resultado incerto: falha de transporte controlada.",
                data=dict(
                    operation_id=operation_id, next_action="READ_STATE_THEN_REPLAY_SAME_OPERATION"
                ),
            ),
        )

    def forward_output():
        for line in child.stdout:
            message = json.loads(line)
            operation_id = pending.pop(message.get("id"), None)
            result = message.get("result", {}).get("structuredContent", {})
            if args.fault == "lost-success" and operation_id and result.get("ok"):
                try:
                    with args.marker.open("x", encoding="utf-8") as marker:
                        json.dump(
                            dict(
                                tool="save_menu_decision",
                                operation_id=operation_id,
                                committed_revision=result["revision"],
                            ),
                            marker,
                        )
                except FileExistsError:
                    pass
                else:
                    emit(uncertain(message["id"], operation_id))
                    continue
            emit(message)

    forwarding = Thread(target=forward_output)
    forwarding.start()
    try:
        for line in sys.stdin.buffer:
            message = json.loads(line)
            if (
                args.fault == "disconnect-calculation"
                and message.get("method") == "tools/call"
                and message["params"]["name"] == "calculate_pricing_scenarios"
            ):
                args.marker.write_text(
                    json.dumps(
                        dict(
                            tool="calculate_pricing_scenarios",
                            committed=False,
                            operation_id=message["params"].get("arguments", {}).get("operation_id"),
                        )
                    ),
                    encoding="utf-8",
                )
                break
            if (
                message.get("method") == "tools/call"
                and message["params"]["name"] == "save_menu_decision"
            ):
                operation_id = message["params"].get("arguments", {}).get("operation_id")
                pending[message["id"]] = operation_id
            child.stdin.write(line)
            child.stdin.flush()
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
        forwarding.join(timeout=5)
        child.stdout.close()
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())
