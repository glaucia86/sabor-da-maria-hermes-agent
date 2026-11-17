"""Opt-in: perfil descartável configurado, Hermes instalado sem atualizações."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dona_maria.onboarding import environment


def test_installed_host_registration_and_desktop_dispatch():
    profile = os.environ.get("DONA_MARIA_HERMES_TEST_PROFILE")
    if not profile:
        pytest.skip("Defina DONA_MARIA_HERMES_TEST_PROFILE com um perfil sintético isolado.")
    assert profile.startswith("sabor-research-regression-")
    assert Path(profile).name == profile
    executable = shutil.which("hermes")
    assert executable
    env = environment() | {"HERMES_DISABLE_LAZY_INSTALLS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    resolved = subprocess.run(
        [executable, "--print-runtime-command", "--module", "hermes_cli.version_info"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=True,
        timeout=30,
    )
    command = json.loads(resolved.stdout)
    probe = Path(__file__).with_name("hermes_runtime_probe.py")
    command[3] += (
        "; from hermes_constants import get_default_hermes_root, set_hermes_home_override; "
        f"home = get_default_hermes_root() / 'profiles' / {profile!r}; "
        "os.environ['HERMES_HOME'] = str(home); set_hermes_home_override(home); "
        f"runpy.run_path({str(probe)!r}, run_name='__main__')"
    )
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, "Runtime recusou registro ou cobertura de hooks."
    assert result.stdout.strip() == "HERMES_RUNTIME_PASS"
