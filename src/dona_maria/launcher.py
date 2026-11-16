"""Launcher stdio: o processo de negócio recebe somente ambiente operacional e binding."""

import os
import subprocess
import sys


def main():
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "DONA_MARIA_DB_PATH",
        "DONA_MARIA_WORKSPACE_ID",
        "DONA_MARIA_MODE",
    }
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-m", "dona_maria.mcp_server"],
        env=environment,
        check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
