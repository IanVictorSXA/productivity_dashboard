"""Tests for Task class and task-related commands."""

import pytest
from classes import Task, Message


class TestTaskCreation:
    """Test task creation."""

    def test_create_task(self, test_task_manager):
        """Test creating a task via process_command."""
        msg = Message(
            id=1,
            command="create",
            label="Buy groceries",
            type="task",
            completed=False,
            pos=0
        )

        test_task_manager.process_command(msg)

        assert len(test_task_manager.tasks) == 1
        task = test_task_manager.tasks[0]
        assert task.id == 1
        assert task.label == "Buy groceries"
        assert task.completed is False
        assert task.deleted is False

    def test_create_multiple_tasks(self, test_task_manager):
        """Test creating multiple tasks."""
        for i in range(3):
            msg = Message(
                id=i,
                command="create",
                label=f"Task {i}",
                type="task",
                completed=False,
                pos=i
            )
            test_task_manager.process_command(msg)

        assert len(test_task_manager.tasks) == 3
        assert test_task_manager.tasks[0].label == "Task 0"
        assert test_task_manager.tasks[1].label == "Task 1"
        assert test_task_manager.tasks[2].label == "Task 2"

    def test_create_task_with_completed_state(self, test_task_manager):
        """Test creating a task that starts completed."""
        msg = Message(
            id=1,
            command="create",
            label="Completed task",
            type="task",
            completed=True,
            pos=0
        )

        test_task_manager.process_command(msg)

        assert test_task_manager.tasks[0].completed is True


class TestTaskCommands:
    """Test task command handling."""

    def test_complete_task(self, test_task_manager):
        """Test completing a task."""
        # Create task
        msg_create = Message(
            id=1,
            command="create",
            label="Test task",
            type="task",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        assert test_task_manager.tasks[0].completed is False

        # Complete task
        msg_complete = Message(
            id=1,
            command="complete",
            type="task",
            completed=False  # Message doesn't change, backend toggles
        )
        test_task_manager.process_command(msg_complete)

        assert test_task_manager.tasks[0].completed is True

    def test_complete_task_toggle(self, test_task_manager):
        """Test toggling task completion state."""
        msg_create = Message(
            id=1,
            command="create",
            label="Toggle test",
            type="task",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        # Toggle to completed
        msg_complete = Message(id=1, command="complete", type="task")
        test_task_manager.process_command(msg_complete)
        assert test_task_manager.tasks[0].completed is True

        # Toggle back to incomplete
        test_task_manager.process_command(msg_complete)
        assert test_task_manager.tasks[0].completed is False

    def test_edit_task_label(self, test_task_manager):
        """Test editing a task label."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original label",
            type="task",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Updated label",
            type="task"
        )
        test_task_manager.process_command(msg_edit)

        assert test_task_manager.tasks[0].label == "Updated label"

    def test_delete_task(self, test_task_manager):
        """Test deleting a task."""
        msg_create = Message(
            id=1,
            command="create",
            label="Task to delete",
            type="task",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)
        assert len(test_task_manager.tasks) == 1

        msg_delete = Message(
            id=1,
            command="delete",
            type="task"
        )
        test_task_manager.process_command(msg_delete)

        # Task should be removed from list after delete
        assert len(test_task_manager.tasks) == 0

    def test_delete_removes_from_list(self, test_task_manager):
        """Test that delete removes task from the tasks list."""
        msg_create = Message(
            id=1,
            command="create",
            label="Task to remove",
            type="task",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_delete = Message(id=1, command="delete", type="task")
        test_task_manager.process_command(msg_delete)

        # Task should be removed from list
        assert len(test_task_manager.tasks) == 0


class TestTaskDatabasePersistence:
    """Test that task changes persist to database."""

    def test_task_persists_to_db(self, test_task_manager, test_db):
        """Test that created task is saved to database."""
        msg = Message(
            id=1,
            command="create",
            label="Persist test",
            type="task",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg)

        # Verify in database
        _, data = test_db.retrieveAll()
        task_records = [d for d in data if d.get("type") == "task"]
        assert len(task_records) == 1
        assert task_records[0]["label"] == "Persist test"

    def test_completed_task_persists(self, test_task_manager, test_db):
        """Test that task completion state persists to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Complete test",
            type="task",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_complete = Message(id=1, command="complete", type="task")
        test_task_manager.process_command(msg_complete)

        _, data = test_db.retrieveAll()
        task_records = [d for d in data if d.get("type") == "task"]
        assert task_records[0]["completed"] == 1

    def test_edited_task_persists(self, test_task_manager, test_db):
        """Test that task edits persist to database."""
        msg_create = Message(
            id=1,
            command="create",
            label="Original",
            type="task",
            completed=False,
            pos=0
        )
        test_task_manager.process_command(msg_create)

        msg_edit = Message(
            id=1,
            command="edit",
            label="Modified",
            type="task"
        )
        test_task_manager.process_command(msg_edit)

        _, data = test_db.retrieveAll()
        task_records = [d for d in data if d.get("type") == "task"]
        assert task_records[0]["label"] == "Modified"
