"""Tests for the column-A cell grammar in `sheets_parse.py` (Phase 3, Group 4).

Pure functions only: no network, no key file, no database.
"""

from datetime import timezone
from zoneinfo import ZoneInfo

import pytest

from sheets_parse import CellError, parse_cell, parse_column

UTC = timezone.utc


class TestEventsVersusTasks:
    @pytest.mark.parametrize("text", [
        "check email",
        "bath, bed, timers 8h",   # digits inside the cell must not make it an alarm
        "1300 pay rent",           # bare 4-digit number, no colon or am/pm: a task
        "7 eggs",                  # a bare hour is a quantity, not a time
        "pick up 3pm parcel",      # the time must be at the START of the cell
    ])
    def test_plain_text_is_a_task(self, text):
        item = parse_cell(2, text, UTC)

        assert item.type == "task"
        assert item.label == text
        assert item.ring_time is None

    def test_leading_time_makes_an_event_with_the_rest_as_label(self, frozen_clock):
        item = parse_cell(2, "1pm sun lunch", UTC)

        assert item.type == "event"
        assert item.label == "sun lunch"
        assert item.key == "1pm sun lunch"
        assert item.ring_time == "2026-11-15T13:00:00+00:00"

    @pytest.mark.parametrize("text, expected_utc", [
        ("12am midnight snack", "2026-11-15T00:00:00+00:00"),
        ("12pm noon call",      "2026-11-15T12:00:00+00:00"),
        ("645am wake",          "2026-11-15T06:45:00+00:00"),
        ("6:45am wake",         "2026-11-15T06:45:00+00:00"),
        ("6:45 a.m. wake",      "2026-11-15T06:45:00+00:00"),
        ("10PM bed",            "2026-11-15T22:00:00+00:00"),
        ("13:30 standup",       "2026-11-15T13:30:00+00:00"),
        ("1pm - lunch",         "2026-11-15T13:00:00+00:00"),
    ])
    def test_time_forms(self, frozen_clock, text, expected_utc):
        assert parse_cell(2, text, UTC).ring_time == expected_utc

    def test_wall_clock_time_is_resolved_in_the_users_zone_not_the_servers(self, frozen_clock):
        # The backend container runs UTC; "1pm" in the sheet means 1pm in Chicago
        # (CST, UTC-6 in November) = 19:00 UTC. Reading it as UTC would ring 6h early.
        item = parse_cell(2, "1pm lunch", ZoneInfo("America/Chicago"))

        assert item.ring_time == "2026-11-15T19:00:00+00:00"

    def test_key_is_the_stripped_cell_text(self):
        assert parse_cell(2, "   check email  ", UTC).key == "check email"


class TestBadCells:
    @pytest.mark.parametrize("text, fragment", [
        ("1pm", "no label"),
        ("13pm lunch", "12-hour"),
        ("0am lunch", "12-hour"),
        ("25:00 lunch", "not a valid time"),
        ("9:75am lunch", "minute"),
        ("   ", "empty"),
    ])
    def test_cell_that_looks_like_an_item_but_is_not_raises(self, text, fragment):
        with pytest.raises(CellError, match=fragment):
            parse_cell(2, text, UTC)


class TestParseColumn:
    def test_first_row_is_never_a_card(self):
        read = parse_column(["7am", "check email"])

        assert [i.label for i in read.items] == ["check email"]
        assert read.items[0].row == 2

    def test_blank_cells_are_skipped_silently_and_rows_keep_their_numbers(self):
        read = parse_column(["7am", "", "  ", "a task"])

        assert [(i.row, i.label) for i in read.items] == [(4, "a task")]
        assert read.skipped == []

    def test_bad_cell_is_skipped_but_does_not_cost_the_other_rows(self, frozen_clock):
        read = parse_column(["7am", "1pm", "good task", "2pm good event"])

        assert read.ok is True
        assert [i.label for i in read.items] == ["good task", "good event"]
        assert read.skipped == [(2, "event has a time but no label")]

    def test_cells_holds_every_nonempty_text_even_unparsed_ones(self, frozen_clock):
        # The diff deletes against `cells`, so a cell that stops parsing keeps its card.
        read = parse_column(["7am", "1pm", "a task", ""])

        assert read.cells == {"1pm", "a task"}

    def test_empty_column_is_a_successful_empty_read(self):
        read = parse_column([])

        assert read.ok is True
        assert read.items == []
        assert read.cells == set()

    def test_never_produces_timers_or_stopwatches(self, frozen_clock):
        read = parse_column(["7am", "timer 25m", "stopwatch work", "1pm timer 10m"])

        assert {i.type for i in read.items} <= {"event", "task"}
