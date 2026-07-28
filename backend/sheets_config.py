"""Google Sheets sync configuration, read from the environment once at import time.

`SHEETS_SYNC_ENABLED` gates the whole sync path added in later groups; every
other variable here only matters once sync is enabled, so a dev machine with
none of them set behaves exactly as it did before Phase 3.
"""

import os


def _read_bool(name: str, default: bool) -> bool:
    """Parse an env var as a boolean, accepting common truthy strings case-insensitively."""
    value = os.environ.get(name)
    if value is None:
        return default

    return value.strip().lower() in ("1", "true", "yes", "on")


SHEETS_SYNC_ENABLED: bool = _read_bool("SHEETS_SYNC_ENABLED", False)
SHEETS_KEY_FILE: str | None = os.environ.get("SHEETS_KEY_FILE")
SHEETS_SPREADSHEET_ID: str | None = os.environ.get("SHEETS_SPREADSHEET_ID")
SHEETS_TAB_NAME: str = os.environ.get("SHEETS_TAB_NAME", "Day")
