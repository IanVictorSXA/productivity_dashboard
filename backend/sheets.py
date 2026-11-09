"""Authenticated, read-only Google Sheets client for the dashboard's daily sync.

Everything here is deliberately failure-typed: each way the connection can go
wrong raises its own `SheetsError` subclass so the sync path (later groups) can
log a message that names the fix instead of dumping a traceback. Nothing in this
module mutates dashboard state, and the credential is requested with the
read-only scope, so it cannot write to the spreadsheet either.

Run `python sheets.py --check` inside the backend container to prove the
credentials and sharing are set up correctly without booting the whole app.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

import gspread
from google.auth.exceptions import GoogleAuthError
from google.oauth2.service_account import Credentials
from requests.exceptions import RequestException

import sheets_config
# No cycle: `classes` only reaches this module lazily, from inside
# `TaskManager.sync_sheets()`, so it is fully imported before we are.
from classes import Message
from sheets_parse import SheetRead, parse_column

# Read-only for the whole phase: the write path (end-of-day stats) is Phase 7.
READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

# The sheet is one tab, one column; every item lives in column A.
ITEM_COLUMN = 1

# Every Sheets request is bounded, so a black-holed network cannot hang backend
# startup — the sync runs inside `TaskManager.__init__`.
REQUEST_TIMEOUT_SECONDS = 15

logger = logging.getLogger(__name__)


class SheetsError(Exception):
    """Base class for every anticipated Sheets failure."""


class SheetsConfigError(SheetsError):
    """A required environment variable is missing or empty."""


class SheetsAuthError(SheetsError):
    """The key file is missing, unreadable, or not a usable service-account key."""


class SheetsAccessError(SheetsError):
    """The service account may not read the spreadsheet (403 — sheet not shared)."""


class SheetsNotFoundError(SheetsError):
    """The spreadsheet id is wrong (404) or the tab does not exist."""


class SheetsNetworkError(SheetsError):
    """The request never reached Google — DNS failure, no route, or timeout."""


def _key_file_path(key_file: str | None = None) -> str:
    """Return the configured key file path, or raise if none is set."""
    path = key_file or sheets_config.SHEETS_KEY_FILE
    if not path:
        raise SheetsConfigError(
            "SHEETS_KEY_FILE is not set — point it at the service-account key JSON."
        )

    return path


def _load_key_file(path: str) -> dict:
    """Read and parse the service-account key JSON at `path`.

    The compose default mounts /dev/null when no key is configured, so an empty
    or non-JSON file is an expected case, not a bug.
    """
    if not os.path.isfile(path):
        raise SheetsAuthError(f"Service-account key file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            info = json.load(handle)
    except OSError as error:
        raise SheetsAuthError(f"Cannot read service-account key file {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise SheetsAuthError(f"Service-account key file {path} is not valid JSON: {error}") from error

    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise SheetsAuthError(
            f"{path} is not a service-account key (expected a JSON object with "
            '"type": "service_account") — re-download the key from the Google Cloud console.'
        )

    return info


def get_service_account_email(key_file: str | None = None) -> str | None:
    """Return the key's `client_email`, or None if it cannot be read.

    Used to make the 403 message actionable ("share the sheet with this
    address"), so it must never raise on its own.
    """
    try:
        return _load_key_file(_key_file_path(key_file)).get("client_email")
    except SheetsError:
        return None


def get_client(key_file: str | None = None) -> gspread.Client:
    """Build an authorized, read-only `gspread` client from the service-account key."""
    info = _load_key_file(_key_file_path(key_file))

    try:
        credentials = Credentials.from_service_account_info(info, scopes=[READONLY_SCOPE])
    except (ValueError, GoogleAuthError) as error:
        raise SheetsAuthError(f"Service-account key is malformed: {error}") from error

    client = gspread.authorize(credentials)
    client.set_timeout(REQUEST_TIMEOUT_SECONDS)

    return client


def open_worksheet(
    client: gspread.Client,
    spreadsheet_id: str | None = None,
    tab_name: str | None = None,
) -> gspread.Worksheet:
    """Open `tab_name` in `spreadsheet_id`, defaulting both from the environment.

    This is the first call that actually reaches the network: `open_by_key` is
    lazy, so authentication, sharing, and id errors all surface here.
    """
    spreadsheet_id = spreadsheet_id or sheets_config.SHEETS_SPREADSHEET_ID
    if not spreadsheet_id:
        raise SheetsConfigError(
            "SHEETS_SPREADSHEET_ID is not set — copy the id out of the spreadsheet URL."
        )

    tab_name = tab_name or sheets_config.SHEETS_TAB_NAME

    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        return spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound as error:
        raise SheetsNotFoundError(
            f'Spreadsheet {spreadsheet_id} has no tab named "{tab_name}" — '
            "check SHEETS_TAB_NAME against the tab at the bottom of the sheet."
        ) from error
    except gspread.exceptions.SpreadsheetNotFound as error:
        raise SheetsNotFoundError(
            f"No spreadsheet with id {spreadsheet_id} — check SHEETS_SPREADSHEET_ID."
        ) from error
    except PermissionError as error:
        raise SheetsAccessError(_sharing_hint(spreadsheet_id)) from error
    except gspread.exceptions.APIError as error:
        if error.code == 403:
            raise SheetsAccessError(_sharing_hint(spreadsheet_id)) from error
        if error.code == 404:
            raise SheetsNotFoundError(
                f"No spreadsheet with id {spreadsheet_id} — check SHEETS_SPREADSHEET_ID."
            ) from error
        raise SheetsError(f"Google Sheets API error: {error}") from error
    except RequestException as error:
        raise SheetsNetworkError(f"Could not reach Google Sheets: {error}") from error
    except GoogleAuthError as error:
        raise SheetsAuthError(f"Could not authenticate with the service-account key: {error}") from error


def _sharing_hint(spreadsheet_id: str) -> str:
    """403 message that names the address the sheet has to be shared with."""
    email = get_service_account_email()
    who = email or "the service account in SHEETS_KEY_FILE"

    return (
        f"Access denied to spreadsheet {spreadsheet_id} — share it (Viewer is enough) "
        f"with {who}."
    )


def _translate_api_error(error: Exception, spreadsheet_id: str) -> SheetsError:
    """Map a raw gspread/requests failure onto the typed `SheetsError` family.

    `open_worksheet` keeps its own inline handling (it has the extra
    Worksheet/Spreadsheet-not-found cases and is verified against every failure
    path); this covers the reads that happen once a worksheet is already open.
    """
    if isinstance(error, gspread.exceptions.APIError):
        if error.code == 403:
            return SheetsAccessError(_sharing_hint(spreadsheet_id))
        if error.code == 404:
            return SheetsNotFoundError(
                f"No spreadsheet with id {spreadsheet_id} — check SHEETS_SPREADSHEET_ID."
            )
        return SheetsError(f"Google Sheets API error: {error}")

    if isinstance(error, RequestException):
        return SheetsNetworkError(f"Could not reach Google Sheets: {error}")

    if isinstance(error, GoogleAuthError):
        return SheetsAuthError(f"Could not authenticate with the service-account key: {error}")

    return SheetsError(f"Unexpected Sheets failure: {error}")


def read_day(worksheet: gspread.Worksheet | None = None) -> SheetRead:
    """Read column A of the `Day` tab and parse it into items.

    One request for the whole column, so the parsed items are a snapshot of a
    single moment rather than a walk down a sheet that may be edited mid-read.
    Never raises: every failure comes back as a `SheetRead` with `ok = False`,
    which is what tells Group 5's diff to touch nothing at all.
    """
    try:
        if worksheet is None:
            worksheet = open_worksheet(get_client())

        values = worksheet.col_values(ITEM_COLUMN)
    except SheetsError as error:
        logger.warning("Sheets: read failed (%s): %s", type(error).__name__, error)
        return SheetRead(ok=False, error=f"{type(error).__name__}: {error}")
    except Exception as error:  # gspread/requests failures from col_values itself
        translated = _translate_api_error(error, sheets_config.SHEETS_SPREADSHEET_ID)
        logger.warning("Sheets: read failed (%s): %s", type(translated).__name__, translated)
        return SheetRead(ok=False, error=f"{type(translated).__name__}: {translated}")

    read = parse_column(values)
    logger.info(
        "Sheets: read column A — %d item(s), %d skipped, %d row(s) scanned",
        len(read.items), len(read.skipped), len(values),
    )

    return read


def _sheet_cards(task_manager) -> dict[str, list]:
    """Group every loaded card the sheet owns by its cell text.

    Only `source = 'sheet'` cards are collected, which is the whole safety
    property of the diff below: a card the user made by hand on the dashboard
    is invisible to it and can never be deleted by a sync.
    """
    owned: dict[str, list] = {}

    for card in list(task_manager.tasks) + list(task_manager.events):
        if card.source == "sheet" and card.sheet_key:
            owned.setdefault(card.sheet_key, []).append(card)

    return owned


def _has_passed(ring_time: str, now: datetime) -> bool:
    """Has this event's ring time already gone by? Exactly now counts as past.

    Both sides are absolute UTC — the parser resolved the cell's wall-clock text
    against the user's zone — so this does not re-open the timezone question.
    """
    return datetime.fromisoformat(ring_time) <= now


def _apply_diff(task_manager, read: SheetRead) -> tuple[int, int, int]:
    """Bring the sheet-origin cards in line with column A; return (created, deleted, past).

    Called from exactly one place, on the far side of the `read.ok` check, and
    that single call site is the whole safety argument for the deletion half:
    there is no path from a failed read to this function. Everything that can go
    wrong before it — config, key, network, 403, 404, a truncated read — returns
    early in `_reconcile`, so no failure can be mistaken for "column A is empty".
    """
    db = task_manager.db
    owned = _sheet_cards(task_manager)
    now = datetime.now(timezone.utc)

    deleted = 0
    for key, cards in owned.items():
        # Matched against every non-empty cell, parsed or not (`read.cells`), so
        # a cell that has *become* unparseable keeps its card rather than
        # reading as a deleted row.
        if key in read.cells:
            continue

        for card in cards:
            task_manager.process_command(Message(command="delete", id=card.id, type=card.type))
            deleted += 1
            logger.info("Sheets: deleted %s %r — its cell is gone from column A", card.type, key)

    created, past = 0, 0
    for item in read.items:
        # Two identical cells produce one card; the cell text is the only key
        # there is, so a duplicate row is indistinguishable from the original.
        if item.key in owned:
            continue

        if item.type == "event" and _has_passed(item.ring_time, now):
            # Creating it would put a card on the board that rings the instant it
            # appears, for something already done or already missed. Counted apart
            # from unparseable cells because it is a normal outcome, not a failure.
            past += 1
            logger.info("Sheets: A%d skipped, %r has already passed today", item.row, item.key)
            continue

        task_manager.process_command(Message(
            command="create",
            id=db.last_id + 1,
            type=item.type,
            label=item.label,
            ring_time=item.ring_time,
            completed=False,
            source="sheet",
            sheet_key=item.key,
        ))
        created += 1

    return created, deleted, past


def _record(task_manager, date: str, status: str, detail: str) -> None:
    """Write the `sheet_sync` marker for `date`, swallowing a database failure.

    The marker is diagnosis, not state the dashboard needs to run. If the
    database is the thing that broke, failing to record *that* must not be what
    finally takes startup down.
    """
    try:
        task_manager.db.set_sheet_sync(date, status, detail)
    except Exception:
        logger.exception("Sheets: could not record %s status for %s", status, date)


def _reconcile(task_manager, date: str, force: bool) -> dict:
    """The sync proper. May raise; `sync_day` is the guard that makes sure it can't escape."""
    if not force:
        marker = task_manager.db.get_sheet_sync(date)
        if marker is not None and marker["status"] == "ok":
            logger.info("Sheets: %s already synced (%s), skipping", date, marker["detail"])
            # Carries the earlier run's counts through, so a same-day restart
            # still publishes what today's sync actually did (3d) rather than
            # only that it was skipped.
            return {"date": date, "status": "skipped",
                    "detail": f"already synced today — {marker['detail']}"}

    read = read_day()

    if not read.ok:
        # A failed read means column A is *unknown*, not empty. Bailing out here,
        # before a single mutation, is what keeps a network blip or an expired
        # credential from being mistaken for "the user deleted everything today".
        # The marker records the failure without marking the day done, so the
        # next restart (or a tap of the manual button) retries.
        logger.warning("Sheets: sync aborted, nothing created or deleted — %s", read.error)
        _record(task_manager, date, "error", read.error)

        return {"date": date, "status": "error", "detail": read.error}

    created, deleted, past = _apply_diff(task_manager, read)

    detail = f"created {created}, deleted {deleted}, past {past}, unparsed {len(read.skipped)}"
    _record(task_manager, date, "ok", detail)
    logger.info("Sheets: sync complete for %s — %s", date, detail)

    return {"date": date, "status": "ok", "detail": detail}


def sync_day(task_manager, force: bool = False) -> dict:
    """Reconcile the dashboard's sheet-origin cards against today's column A.

    The sheet owns the cards it created: a cell with no card gets one, a
    sheet-origin card whose cell is gone is deleted, and a matched card is left
    completely alone (a completed task stays completed, a dismissed event stays
    dismissed). Local cards, timers, and stopwatches are never touched.

    `force` bypasses the once-per-day marker — that marker exists to stop the
    automatic startup trigger from re-running, not to stop the user (3f).

    **This function never raises.** It runs inside `TaskManager.__init__`, so an
    exception here would be a backend that does not start; the dashboard has to
    work with the sheet unreachable, misconfigured, or absent. Anticipated
    failures already arrive as a typed `SheetsError` message via `read_day`; the
    catch-all below is for the unanticipated ones — a `sqlite3.OperationalError`
    from tables that were never dropped, a gspread internal, a bad key file that
    only fails on use — which are logged with a traceback and swallowed.
    """
    date = None

    try:
        date = task_manager.db.get_date()

        return _reconcile(task_manager, date, force)
    except Exception as error:
        detail = f"{type(error).__name__}: {error}"
        logger.exception("Sheets: sync failed for %s — the dashboard is unaffected", date or "today")

        if date:  # if `get_date()` is what failed there is no key to record under
            _record(task_manager, date, "error", detail)

        return {"date": date, "status": "error", "detail": detail}


def check() -> int:
    """Print the service-account email and the sheet title; return a shell exit code."""
    if not sheets_config.SHEETS_SYNC_ENABLED:
        print("note: SHEETS_SYNC_ENABLED is false — checking the connection anyway.")

    try:
        client = get_client()
        print(f"service account: {get_service_account_email()}")

        worksheet = open_worksheet(client)
        print(f"spreadsheet:     {worksheet.spreadsheet.title}")
        print(f"tab:             {worksheet.title} ({worksheet.row_count} rows)")
    except SheetsError as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1

    print("OK")
    return 0


def dump() -> int:
    """Print what the parser makes of column A, so it can be read against the sheet."""
    read = read_day()

    if not read.ok:
        print(read.error, file=sys.stderr)
        return 1

    for item in read.items:
        when = f" @ {item.ring_time}" if item.ring_time else ""
        print(f"A{item.row:<3} {item.type:<5} {item.label!r}{when}")

    for row, reason in read.skipped:
        print(f"A{row:<3} SKIP  {reason}")

    print(f"{len(read.items)} item(s), {len(read.skipped)} skipped")
    return 0


if __name__ == "__main__":
    # Same reason as `main.py`: without a handler on the root logger the INFO
    # lines these commands rely on ("read column A — N items") never appear.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    arguments = sys.argv[1:]

    if "--dump" in arguments:
        sys.exit(dump())
    if "--check" in arguments or not arguments:
        sys.exit(check())

    print(f"usage: python {os.path.basename(__file__)} [--check | --dump]", file=sys.stderr)
    sys.exit(2)
