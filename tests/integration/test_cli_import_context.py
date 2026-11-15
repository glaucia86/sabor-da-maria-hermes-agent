"""Subprocessos de teste usam o mesmo checkout que o processo do pytest."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "case",
    [
        "test_cli_migration_review_attestation_and_rejection",
        "test_lost_cli_response_after_commit_replays_original_result_without_another_effect",
    ],
)
def test_cli_uses_current_checkout_with_a_foreign_pythonpath(tmp_path, case):
    project = Path(__file__).resolve().parents[2]
    foreign = tmp_path / "old-checkout"
    package = foreign / "dona_maria"
    shutil.copytree(
        project / "src/dona_maria",
        package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    inventory = package / "inventory.py"
    content = inventory.read_text(encoding="utf-8")
    old = 'import_policy_version: Literal["1.0", "2.0"] = "1.0"'
    assert content.count(old) == 1
    inventory.write_text(
        content.replace(old, 'import_policy_version: Literal["1.0"] = "1.0"'),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--maxfail=1",
            f"--basetemp={tmp_path / 'nested'}",
            f"tests/integration/test_local_approval_cli.py::{case}",
        ],
        cwd=project,
        env=os.environ | {"PYTHONPATH": str(foreign)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
