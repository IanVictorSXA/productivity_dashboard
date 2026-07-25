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
