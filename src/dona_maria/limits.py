"""Limites compartilhados pelo receptor e pelas fronteiras de negócio."""

import json

MAX_CALL_BYTES = 256 * 1024


def collections_fit(parameters) -> bool:
    pending = [parameters]
    while pending:
        value = pending.pop()
        if isinstance(value, (dict, list)):
            if len(value) > 200:
                return False
            pending.extend(value.values() if isinstance(value, dict) else value)
    return True


def call_fits(arguments) -> bool:
    return len(
        json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ) <= MAX_CALL_BYTES and collections_fit(arguments)
