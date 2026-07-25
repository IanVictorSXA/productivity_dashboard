"""Sanity checks for the `conftest.py` fixtures themselves (temp DB, task manager)."""

import pytest
from classes import TaskManager, Message


def test_database_initialization(test_db):
    """Test that a test database initializes correctly."""
    assert test_db is not None
    assert test_db.last_id == -1


def test_task_manager_initialization(test_task_manager):
    """Test that a test task manager initializes correctly."""
    assert test_task_manager is not None
    assert test_task_manager.tasks == []
    assert test_task_manager.events == []
    assert test_task_manager.durations == []
    assert test_task_manager.db is not None


def test_create_task(test_task_manager):
    """Test creating a task."""
    msg = Message(
        id=1,
        command="create",
        label="Test Task",
        type="task",
        completed=False,
        pos=0
    )

    test_task_manager.process_command(msg)

    assert len(test_task_manager.tasks) == 1
    assert test_task_manager.tasks[0].label == "Test Task"
    assert test_task_manager.tasks[0].id == 1
