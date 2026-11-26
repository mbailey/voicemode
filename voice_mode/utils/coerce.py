"""Coercion for loosely typed MCP / CLI arguments."""

from typing import Optional, Union

_TRUE = frozenset({"true", "1", "yes", "y", "on"})
_FALSE = frozenset({"false", "0", "no", "n", "off", ""})


def coerce_bool(
    value: Union[bool, str, None], default: Optional[bool] = None
) -> Optional[bool]:
    """Turn a bool-ish MCP/CLI argument into a real bool.

    MCP clients may send ``"false"`` for a ``Union[bool, str]`` parameter, and
    a non-empty string is truthy, so it must never be used as a bool directly.

    - ``True``/``False`` pass through.
    - ``"true"``/``"1"``/``"yes"``/``"y"``/``"on"`` (any case) -> True.
    - ``"false"``/``"0"``/``"no"``/``"n"``/``"off"``/``""`` -> False.
    - ``None`` and anything unrecognised -> ``default``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE:
            return True
        if normalized in _FALSE:
            return False
    return default
