from __future__ import annotations

import getpass


def prompt_value(
    label: str,
    default: str | None = None,
    secret: bool = False,
) -> str:
    """Prompt until a value is entered, accepting an optional default."""
    hint = f" [{default}]" if default not in (None, "") else ""
    prompt = f"  {label}{hint}: "

    while True:
        value = getpass.getpass(prompt) if secret else input(prompt)
        if value:
            return value
        if default is not None:
            return default
