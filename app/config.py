"""Central configuration for CleanSheet.

Every limit lives here so it can be changed in one place. Each value can also be
overridden with an environment variable (useful for deployment and for tests).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


# --------------------------------------------------------------------------- #
# Upload limits
# --------------------------------------------------------------------------- #
# The single configurable upload limit (in megabytes). Everything else derives from it.
MAX_UPLOAD_MB: int = _int_env("CLEANSHEET_MAX_UPLOAD_MB", 50)
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

MAX_ROWS: int = _int_env("CLEANSHEET_MAX_ROWS", 500_000)      # data rows, header excluded
MAX_COLS: int = _int_env("CLEANSHEET_MAX_COLS", 200)
MAX_CELLS: int = _int_env("CLEANSHEET_MAX_CELLS", 10_000_000)  # rows x columns (memory guard)

ALLOWED_EXTENSIONS = frozenset({".csv", ".xlsx"})

# A .xlsx is a zip file. Refuse archives that would expand to more than this (zip bombs).
MAX_XLSX_UNCOMPRESSED_BYTES: int = _int_env("CLEANSHEET_MAX_XLSX_UNCOMPRESSED_MB", 600) * 1024 * 1024

# --------------------------------------------------------------------------- #
# Temporary files and sessions
# --------------------------------------------------------------------------- #
TEMP_DIR = Path(
    os.environ.get("CLEANSHEET_TEMP_DIR") or (Path(tempfile.gettempdir()) / "cleansheet_tmp")
)
STALE_TEMP_SECONDS = 60 * 60            # leftover temp files older than this are purged at startup

SESSION_TTL_SECONDS: int = _int_env("CLEANSHEET_SESSION_TTL_MINUTES", 120) * 60
MAX_SESSIONS: int = _int_env("CLEANSHEET_MAX_SESSIONS", 10)

# --------------------------------------------------------------------------- #
# UI / processing behaviour
# --------------------------------------------------------------------------- #
PREVIEW_ROWS = 10
MAX_PREVIEW_COLS = 60                    # preview tables show at most this many columns
MAX_INVALID_EXAMPLES = 5                 # sample invalid values quoted in warnings

# Values that mean "no data" (compared case-insensitively after trimming).
# Deliberately conservative: words like "unknown" are real categories in many datasets.
MISSING_TOKENS = (
    "na", "n/a", "#n/a", "n.a.", "nan", "null", "#null!", "none", "nil",
    "missing", "-", "--", "?", "#value!", "#div/0!",
)

# Largest JSON request body accepted by the API (plans and options are small; uploads are separate).
MAX_JSON_BYTES = 1024 * 1024
SESSION_COOKIE = "cleansheet_sid"
MAX_DECIMAL_PLACES = 10                  # "Decimal" conversion: most places a user may ask for

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
