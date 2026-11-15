"""Shared pytest fixtures for the backend test suite.

Provides an isolated filesystem sandbox (`temp_db_env`) so every test gets
its own `date_id.txt` and SQLite file instead of touching the real
`productivity.db` / `date_id.txt` used by the running app, plus `test_db` and
`test_task_manager` built on top of that sandbox.
"""

import pytest
import tempfile
import os
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from classes import TaskManager
from database import Database


@pytest.fixture
def temp_db_env(monkeypatch):
    """Create a temporary directory and change to it for the duration of the test."""
    with tempfile.TemporaryDirectory() as temp_dir:
        orig_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            tz = "UTC"
            today = datetime.now(tz=ZoneInfo(tz)).date().strftime("%Y-%m-%d")

            date_id_path = os.path.join(temp_dir, "date_id.txt")
            with open(date_id_path, "w") as f:
                f.write(f"{tz}\n{today}\n-1\n")

            yield temp_dir
        finally:
            os.chdir(orig_cwd)


@pytest.fixture
def test_db(temp_db_env):
    """Create a test Database instance using temporary files."""
    db_instance = Database()
    yield db_instance


@pytest.fixture
def test_task_manager(test_db):
    """Create a test TaskManager instance that uses the test database."""
    tm = TaskManager.__new__(TaskManager)
    tm.tasks = []
    tm.events = []
    tm.durations = []
    tm.db = test_db

    yield tm


@pytest.fixture
def frozen_clock(monkeypatch):
    """Pin "now" to 2026-11-15 12:00 UTC inside the Sheets modules.

    Sheet times like "1pm" are resolved against today's date, and the sync
    drops events whose time has already passed, so without a fixed clock those
    tests would give different answers depending on when they run.
    """
    import sheets
    import sheets_parse
    from datetime import datetime as real_datetime, timezone

    fixed = real_datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    class FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(sheets_parse, "datetime", FrozenDatetime)
    monkeypatch.setattr(sheets, "datetime", FrozenDatetime)

    return fixed
