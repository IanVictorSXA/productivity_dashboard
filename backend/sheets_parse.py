"""Grammar for column A of the `Day` tab: one non-empty cell, one card.

Split out from `sheets.py` so the cell grammar can be exercised without a
network, a key file, or any Google import — `parse_column` is a pure function
over a list of strings.

The grammar, as confirmed by the user against the real sheet:

    A1              the wake-up time, never a card (see HEADER_ROWS)
    "1pm sun lunch" an **event**: a leading clock time, then the label
    "check email"   a **task**: everything else non-empty
    ""              skipped

Events are listed first and in order, but nothing here depends on that — the
row order carries no meaning beyond logging. Timers and stopwatches are never
produced from a cell, whatever it contains.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from database import get_timezone

logger = logging.getLogger(__name__)

# A1 holds the time the user intends to wake up, not an item. User-confirmed:
# "A1 is just the time I should wake up. Ignore it for now at least."
HEADER_ROWS = 1

# A cell is an event when it *starts* with a clock time. The am/pm forms are
# what the sheet actually uses ("1pm", "10pm", "645am" = 6:45am); the bare
# 24-hour form is accepted only with a colon, since "1300" alone is as likely
# to be a quantity as a time. Requiring the match at position 0 plus either a
# meridiem or a colon is what keeps a task like "bath, bed, timers 8h" from
# being read as an alarm.
_TIME = re.compile(
    r"""^\s*
    (?:
        (?P<h12>\d{1,2}) (?: : (?P<m12>\d{2}) | (?P<m12_bare>\d{2}) )?
        \s* (?P<meridiem>[ap]\.?m\.?)
      | (?P<h24>\d{1,2}) : (?P<m24>\d{2}) (?![\d:])
    )
    \s* [-–—:,.]? \s*
    (?P<label>.*)$""",
    re.IGNORECASE | re.VERBOSE,
)


class CellError(ValueError):
    """A cell that looks like an item but cannot be turned into one."""


@dataclass
class SheetItem:
    """One parsed cell, ready to become a `Message` in Group 5."""
    row: int          # 1-based sheet row, for logging and diagnostics
    key: str          # match key for the reconciliation diff (stripped cell text)
    type: str         # "event" or "task" — never "duration"
    label: str
    ring_time: str | None = None  # ISO 8601, events only


@dataclass
class SheetRead:
    """The outcome of one read of column A.

    `ok` is the whole point of this object: the reconciliation diff in Group 5
    must be able to tell "the sheet says there is nothing today" (ok, empty
    items) from "the sheet could not be read" (not ok), because only the first
    is allowed to delete cards.
    """
    ok: bool
    items: list[SheetItem] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (row, reason)
    error: str | None = None
    # Every non-empty cell text, parsed or not. The diff deletes against this
    # rather than against `items`, so a cell that stops parsing keeps its card
    # instead of looking like the user deleted the row.
    cells: set[str] = field(default_factory=set)


def _to_iso(hour: int, minute: int, tz) -> str:
    """Pin a wall-clock time to today in `tz`, as a UTC ISO 8601 string.

    Deliberately *not* `classes.parse_time`, which is the obvious thing to
    reuse: it resolves against the process timezone, and the backend container
    runs UTC while the app's configured zone (line 1 of `date_id.txt`) is the
    user's. Cards created in the browser never hit that — the frontend sends an
    already-absolute ISO timestamp — but "1pm" in a spreadsheet is wall-clock
    text, so reusing `parse_time` here would ring the event hours early.
    """
    local = datetime.combine(datetime.now(tz).date(), time(hour, minute), tzinfo=tz)

    return local.astimezone(timezone.utc).isoformat()


def _parse_ring_time(match: re.Match, tz) -> str:
    """Turn a matched time into an ISO 8601 string for `Message.ring_time`."""
    if match.group("meridiem"):
        hour = int(match.group("h12"))
        minute = int(match.group("m12") or match.group("m12_bare") or 0)

        if not 1 <= hour <= 12:
            raise CellError(f"hour {hour} is not a 12-hour clock time")

        meridiem = match.group("meridiem")[0].lower()
        hour = hour % 12 + (12 if meridiem == "p" else 0)
    else:
        hour = int(match.group("h24"))
        minute = int(match.group("m24"))

        if hour > 23:
            raise CellError(f"hour {hour} is not a valid time")

    if minute > 59:
        raise CellError(f"minute {minute} is not a valid time")

    return _to_iso(hour, minute, tz)


def parse_cell(row: int, text: str, tz=None) -> SheetItem:
    """Parse one cell into an event or a task; raise `CellError` if it is neither."""
    key = text.strip()
    if not key:
        raise CellError("cell is empty")

    match = _TIME.match(key)
    if match is None:
        return SheetItem(row=row, key=key, type="task", label=key)

    label = match.group("label").strip()
    if not label:
        raise CellError("event has a time but no label")

    return SheetItem(
        row=row,
        key=key,
        type="event",
        label=label,
        ring_time=_parse_ring_time(match, tz or get_timezone()),
    )


def parse_column(values: list[str], header_rows: int = HEADER_ROWS) -> SheetRead:
    """Parse column A's values (index 0 == row 1) into a successful `SheetRead`.

    A bad cell is collected and skipped, never raised: one unparseable row must
    not cost the user the other twenty. `ok` is True here because the *read*
    succeeded — only the caller in `sheets.py` can report a failed read.
    """
    read = SheetRead(ok=True)
    tz = get_timezone()  # resolved once per read, not once per cell

    for row, text in enumerate(values[header_rows:], start=header_rows + 1):
        key = text.strip()
        if not key:
            continue

        read.cells.add(key)

        try:
            read.items.append(parse_cell(row, text, tz))
        except CellError as error:
            read.skipped.append((row, str(error)))
            logger.warning("Sheets: skipped row A%d (%s): %r", row, error, text)

    return read
