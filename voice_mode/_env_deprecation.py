"""Helper for one-shot deprecation warnings on renamed env vars / CLIs.

Used during the 8.7.x release window where some env vars were renamed
(VM-1174). The old names are still honoured but emit a one-time warning
to nudge users toward the new ones. Removal scheduled for 8.8.0.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("voicemode")

# Track which deprecation warnings have already fired in this process so
# we only emit each one once -- per-VAR (or per-key for ad-hoc warnings),
# regardless of how many call sites read it.
_warned_keys: set = set()


def get_env_with_deprecation(new_name: str, old_name: str, default: str) -> str:
    """Read ``new_name`` from env, falling back to ``old_name``.

    If only the old name is set, return its value and emit a one-shot
    ``logger.warning`` per process recommending the new name.

    Precedence:
    1. ``new_name`` set -> return it (no warning).
    2. ``old_name`` set -> return it, warn once per process.
    3. neither set -> return ``default``.
    """
    new_val = os.environ.get(new_name)
    if new_val is not None:
        return new_val

    old_val = os.environ.get(old_name)
    if old_val is not None:
        warn_once(
            old_name,
            f"{old_name} is deprecated, use {new_name} instead "
            f"(will be removed in 8.8.0)",
        )
        return old_val

    return default


def warn_once(key: str, message: str) -> None:
    """Emit ``logger.warning(message)`` exactly once per process for ``key``.

    The ``key`` is the dedupe slot -- typically the deprecated env-var name
    or a stable identifier for the deprecation site.
    """
    if key in _warned_keys:
        return
    _warned_keys.add(key)
    logger.warning(message)
