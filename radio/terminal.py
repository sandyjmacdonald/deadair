# radio/terminal.py
"""ANSI terminal colour helpers.

All constants are empty strings when stdout is not a TTY, so output
stays clean when piped or redirected.
"""
from __future__ import annotations

import sys

_IS_TTY: bool = getattr(sys.stdout, "isatty", lambda: False)()


def _c(code: str) -> str:
    """Return the ANSI escape code if stdout is a TTY, otherwise an empty string."""
    return code if _IS_TTY else ""


RESET          = _c("\033[0m")
BOLD           = _c("\033[1m")
DIM            = _c("\033[2m")

RED            = _c("\033[31m")
GREEN          = _c("\033[32m")
YELLOW         = _c("\033[33m")
BLUE           = _c("\033[34m")
MAGENTA        = _c("\033[35m")
CYAN           = _c("\033[36m")

BRIGHT_RED     = _c("\033[91m")
BRIGHT_GREEN   = _c("\033[92m")
BRIGHT_YELLOW  = _c("\033[93m")
BRIGHT_BLUE    = _c("\033[94m")
BRIGHT_MAGENTA = _c("\033[95m")
BRIGHT_CYAN    = _c("\033[96m")
BRIGHT_WHITE   = _c("\033[97m")
