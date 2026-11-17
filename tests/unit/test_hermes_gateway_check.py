"""O preflight deve observar o gateway, não somente os arquivos do perfil."""

import pytest

from dona_maria.hermes_gateway_check import validate_registration


def report():
    return {
        "plugins": [
            {
                "key": "dona-maria-attendance-policy",
                "enabled": True,
                "tools": 0,
                "hooks": 2,
                "error": "",
            },
            {
                "key": "dona-maria-mediated-research",
                "enabled": True,
                "tools": 2,
                "hooks": 0,
                "error": "",
            },
        ],
        "toolsets": [{"key": "culinary_research"}],
    }


def test_gateway_registration_requires_both_plugins_and_research_toolset():
    validate_registration(report())


@pytest.mark.parametrize("fault", ["missing", "disabled", "tools", "hooks", "error", "toolset"])
def test_gateway_registration_refuses_incomplete_or_failed_plugins(fault):
    value = report()
    if fault == "missing":
        value["plugins"].pop()
    elif fault == "toolset":
        value["toolsets"] = []
    elif fault == "hooks":
        value["plugins"][0]["hooks"] = 0
    else:
        key, replacement = {
            "disabled": ("enabled", False),
            "tools": ("tools", 0),
            "error": ("error", "PRIVATE-CANARY"),
        }[fault]
        value["plugins"][1][key] = replacement
    with pytest.raises(ValueError) as error:
        validate_registration(value)
    assert "PRIVATE-CANARY" not in str(error.value)
