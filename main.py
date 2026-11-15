"""
Morticia Sail Plan Tracker - HTMX Version

FastAPI backend with HTMX-powered frontend for logging sail configurations.
"""

from __future__ import annotations

__version__ = "0.11.0"

import logging
import os
import random
import time
import tomllib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response
from timezonefinder import TimezoneFinder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
QUESTDB_URL = os.getenv("QUESTDB_URL", "http://localhost:9000")
VESSEL = "morticia"
TABLE = os.getenv("SAIL_TABLE", "sail_config")  # override only for testing
SIGNALK_URL = os.getenv("SIGNALK_URL", "http://localhost:3000")

# Timezone finder (reused)
_tz_finder = TimezoneFinder()

# Load boat config
def load_boat_config() -> dict[str, Any]:
    """Load boat configuration from TOML file."""
    app_dir = Path(__file__).parent
    config_path = app_dir / "boat_config.toml"
    example_path = app_dir / "boat_config.toml.example"

    if config_path.exists():
        logger.info("Loading boat config from %s", config_path)
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    elif example_path.exists():
        logger.warning("boat_config.toml not found, using example config")
        with open(example_path, "rb") as f:
            return tomllib.load(f)
    else:
        logger.error("No boat configuration file found")
        raise FileNotFoundError("boat_config.toml not found")

_boat_config = load_boat_config()
BOAT_NAME = _boat_config.get("boat", {}).get("name", "Boat")
MAIN_STATES = _boat_config.get("sails", {}).get("main", {}).get("options", [])
HEADSAILS = _boat_config.get("sails", {}).get("headsail", {}).get("options", [])
DOWNWIND_SAILS = _boat_config.get("sails", {}).get("downwind", {}).get("options", [])
CENTRAL_BOARDS = _boat_config.get("boards", {}).get("central", {}).get("options", ["UP", "HALF", "FULL"])
CFOIL_BOARDS = _boat_config.get("boards", {}).get("cfoil", {}).get("options", ["UP", "HALF", "FULL"])
CFOIL_RAKE_OPTIONS = _boat_config.get("boards", {}).get("cfoil_rake", {}).get("options", ["-1", "0", "1", "2", "3", "4"])
SAIL_DISPLAY = _boat_config.get("display", {})

# FastAPI app
app = FastAPI(title=f"{BOAT_NAME} Sail Plan")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Add custom template globals
templates.env.globals["BOAT_NAME"] = BOAT_NAME
templates.env.globals["MAIN_STATES"] = MAIN_STATES
templates.env.globals["HEADSAILS"] = HEADSAILS
templates.env.globals["DOWNWIND_SAILS"] = DOWNWIND_SAILS
templates.env.globals["CENTRAL_BOARDS"] = CENTRAL_BOARDS
templates.env.globals["CFOIL_BOARDS"] = CFOIL_BOARDS
templates.env.globals["CFOIL_RAKE_OPTIONS"] = CFOIL_RAKE_OPTIONS
templates.env.globals["SAIL_DISPLAY"] = SAIL_DISPLAY
templates.env.globals["VERSION"] = __version__


# ============ Signal K / Timezone ============

def get_boat_position() -> tuple[float, float] | None:
    """Fetch GPS position from Signal K."""
    try:
        response = requests.get(
            f"{SIGNALK_URL}/signalk/v1/api/vessels/self/navigation/position",
            timeout=2,
        )
        if response.status_code == 200:
            data = response.json()
            lat = data.get("value", {}).get("latitude")
            lon = data.get("value", {}).get("longitude")
            if lat is not None and lon is not None:
                return (lat, lon)
        else:
            logger.debug("Signal K returned status %d", response.status_code)
    except requests.RequestException as e:
        logger.debug("Failed to fetch GPS position from Signal K: %s", e)
    return None


def get_boat_timezone() -> ZoneInfo:
    """Get timezone from GPS position, fallback to local."""
    position = get_boat_position()
    if position:
        tz_name = _tz_finder.timezone_at(lat=position[0], lng=position[1])
        if tz_name:
            logger.debug("Using GPS-based timezone: %s", tz_name)
            return ZoneInfo(tz_name)
    # Fallback to system timezone
    logger.debug("Using system timezone (no GPS position available)")
    return datetime.now().astimezone().tzinfo


# ============ QuestDB ============
#
# Sail log entries live in the QuestDB table `sail_config`, one row per entry
# (see SAIL_CONFIG_DDL). QuestDB has no row DELETE, so deleting an entry sets
# `deleted = true` (UPDATE) and every read filters those rows out.

SAIL_CONFIG_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    ts TIMESTAMP,
    vessel SYMBOL,
    main VARCHAR,
    headsail VARCHAR,
    downwind VARCHAR,
    staysail_mode BOOLEAN,
    comment VARCHAR,
    central_board VARCHAR,
    cfoil_board VARCHAR,
    cfoil_rake VARCHAR,
    deleted BOOLEAN
) TIMESTAMP(ts) PARTITION BY YEAR WAL
DEDUP UPSERT KEYS(ts, vessel)
"""

DEFAULT_CONFIG: dict[str, Any] = {
    "main": "DOWN", "headsail": "", "downwind": "", "staysail_mode": False, "comment": "",
    "central_board": "UP", "cfoil_board": "UP", "cfoil_rake": "0",
}


def _sql_str(value: str) -> str:
    """Quote a value as a QuestDB SQL string literal (single quotes doubled).

    This is the only way user-supplied text (e.g. the comment) enters SQL.
    """
    return "'" + str(value).replace("'", "''") + "'"


def _ts_literal(dt: datetime) -> str:
    """UTC timestamp literal with microsecond precision, e.g. '2026-09-21T14:13:20.123456Z'."""
    return "'" + dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ") + "'"


def _qdb_exec(sql: str) -> dict[str, Any]:
    """Run one SQL statement against QuestDB's HTTP API; raise on error."""
    resp = requests.get(f"{QUESTDB_URL}/exec", params={"query": sql}, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload


def _wait_applied(table: str = TABLE, timeout: float = 3.0) -> None:
    """Block until QuestDB has applied our last WAL write to `table`.

    WAL tables acknowledge a write once it is durable in the WAL, but a SELECT
    only sees it after it is applied (milliseconds later). The UI re-reads
    immediately after a save/delete, so wait for apply to catch up.
    """
    deadline = datetime.now().timestamp() + timeout
    while datetime.now().timestamp() < deadline:
        rows = _qdb_exec(
            f"SELECT writerTxn, sequencerTxn FROM wal_tables() WHERE name = {_sql_str(table)}"
        )["dataset"]
        if not rows or rows[0][0] == rows[0][1]:
            return
        time.sleep(0.025)
    logger.warning("Timed out waiting for QuestDB to apply writes to %s", table)


def ensure_schema() -> None:
    """Create the sail log table if it does not exist (idempotent)."""
    try:
        _qdb_exec(SAIL_CONFIG_DDL)
    except Exception as e:
        logger.error("Failed to ensure QuestDB %s table: %s", TABLE, e)


_SELECT_COLUMNS = (
    "ts, main, headsail, downwind, staysail_mode, comment, "
    "central_board, cfoil_board, cfoil_rake"
)


def _row_to_entry(row: list[Any]) -> dict[str, Any]:
    """Convert a _SELECT_COLUMNS row into the dict shape the templates expect."""
    ts, main, headsail, downwind, staysail, comment, central, cfoil, rake = row

    def clean(val: Any) -> str:
        """None and the legacy 'NONE' placeholder both mean empty."""
        return "" if val is None or val in ("None", "NONE") else val

    return {
        "time": datetime.fromisoformat(ts.replace("Z", "+00:00")),
        "main": clean(main) or "DOWN",
        "headsail": clean(headsail),
        "downwind": clean(downwind),
        "staysail_mode": bool(staysail),
        "comment": clean(comment),
        "central_board": clean(central) or "UP",
        "cfoil_board": clean(cfoil) or "UP",
        "cfoil_rake": clean(rake) or "0",
    }


def get_current_sail_config() -> dict[str, Any]:
    """Fetch the most recent (non-deleted) sail configuration."""
    try:
        rows = _qdb_exec(
            f"SELECT {_SELECT_COLUMNS} FROM {TABLE} "
            f"WHERE vessel = {_sql_str(VESSEL)} AND coalesce(deleted, false) = false "
            f"AND ts > dateadd('d', -30, now()) ORDER BY ts DESC LIMIT 1"
        )["dataset"]
        if rows:
            entry = _row_to_entry(rows[0])
            entry.pop("time")
            return entry
    except Exception as e:
        logger.error("Failed to fetch sail config from QuestDB: %s", e)
    return dict(DEFAULT_CONFIG)


def write_sail_config(
    main: str,
    headsail: str,
    downwind: str,
    staysail_mode: bool,
    comment: str,
    central_board: str = "UP",
    cfoil_board: str = "UP",
    cfoil_rake: str = "0",
    timestamp: datetime | None = None,
) -> bool:
    """Write a sail configuration entry to QuestDB."""
    ensure_schema()  # cheap; covers QuestDB being unavailable at app start
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Reset rake to "0" when C-foil is UP
    if cfoil_board == "UP":
        cfoil_rake = "0"

    sql = (
        f"INSERT INTO {TABLE} (ts, vessel, main, headsail, downwind, staysail_mode, "
        "comment, central_board, cfoil_board, cfoil_rake) VALUES ("
        f"{_ts_literal(timestamp)}, {_sql_str(VESSEL)}, {_sql_str(main)}, "
        f"{_sql_str(headsail or '')}, {_sql_str(downwind or '')}, "
        f"{'true' if staysail_mode else 'false'}, {_sql_str(comment or '')}, "
        f"{_sql_str(central_board)}, {_sql_str(cfoil_board)}, {_sql_str(cfoil_rake)})"
    )
    try:
        _qdb_exec(sql)
        _wait_applied()
        logger.info(
            "Saved sail config: main=%s, headsail=%s, downwind=%s",
            main, headsail, downwind
        )
        return True
    except Exception as e:
        logger.error("Failed to write sail config to QuestDB: %s", e)
        return False


def get_recent_entries(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch recent (non-deleted) sail log entries, newest first."""
    try:
        rows = _qdb_exec(
            f"SELECT {_SELECT_COLUMNS} FROM {TABLE} "
            f"WHERE vessel = {_sql_str(VESSEL)} AND coalesce(deleted, false) = false "
            f"AND ts > dateadd('d', -7, now()) ORDER BY ts DESC LIMIT {int(limit)}"
        )["dataset"]
        entries = [_row_to_entry(r) for r in rows]
        logger.debug("Fetched %d history entries", len(entries))
        return entries
    except Exception as e:
        logger.error("Failed to fetch recent entries from QuestDB: %s", e)
        return []


def delete_sail_entry(timestamp: datetime) -> bool:
    """Soft-delete a sail configuration entry (QuestDB has no row DELETE)."""
    start = timestamp - timedelta(milliseconds=500)
    stop = timestamp + timedelta(milliseconds=500)
    try:
        _qdb_exec(
            f"UPDATE {TABLE} SET deleted = true WHERE vessel = {_sql_str(VESSEL)} "
            f"AND ts BETWEEN {_ts_literal(start)} AND {_ts_literal(stop)}"
        )
        _wait_applied()
        logger.info("Deleted sail entry at %s", timestamp.isoformat())
        return True
    except Exception as e:
        logger.error("Failed to delete sail entry at %s: %s", timestamp.isoformat(), e)
        return False


ensure_schema()  # create the table on first run (idempotent)


# ============ Helper Functions ============

def format_config_summary(config: dict[str, Any]) -> str:
    """Format sail configuration as readable summary."""
    parts = []

    main = config.get("main") or "DOWN"
    if main in ("DOWN", "None"):
        main = "DOWN"
        parts.append("Main: DOWN")
    else:
        parts.append(f"Main: {main}")

    headsail = config.get("headsail") or ""
    if headsail and headsail != "None":
        name = SAIL_DISPLAY.get(headsail, headsail)
        if config.get("staysail_mode"):
            name += " (S)"
        parts.append(name)
    else:
        headsail = ""

    downwind = config.get("downwind") or ""
    if downwind and downwind != "None":
        parts.append(SAIL_DISPLAY.get(downwind, downwind))
    else:
        downwind = ""

    # Add board state
    board_parts = []
    central = config.get("central_board") or "UP"
    cfoil = config.get("cfoil_board") or "UP"

    if central != "UP":
        board_parts.append(f"C:{SAIL_DISPLAY.get(central, central)}")

    if cfoil != "UP":
        cfoil_rake = config.get("cfoil_rake") or "0"
        board_parts.append(f"F:{SAIL_DISPLAY.get(cfoil, cfoil)}@{cfoil_rake}°")

    if board_parts:
        parts.append(" ".join(board_parts))

    if not headsail and not downwind and main == "DOWN" and not board_parts:
        return "All sails down"

    return " + ".join(parts)


def format_local_time(dt: datetime, tz: ZoneInfo) -> str:
    """Format datetime as HH:MM in given timezone."""
    return dt.astimezone(tz).strftime("%H:%M")


def format_local_datetime(dt: datetime, tz: ZoneInfo) -> str:
    """Format datetime with date and timezone abbreviation."""
    local_dt = dt.astimezone(tz)
    tz_abbrev = local_dt.strftime("%Z")
    return local_dt.strftime(f"%m/%d %H:%M {tz_abbrev}")


# Add helper functions to template globals (after they're defined)
templates.env.globals["format_config_summary"] = format_config_summary


# ============ Routes ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Response:
    """Render the main page."""
    config = get_current_sail_config()
    tz = get_boat_timezone()
    now = datetime.now(timezone.utc)
    
    return templates.TemplateResponse(request, "index.html", {
        "config": config,
        "summary": format_config_summary(config),
        "current_time": format_local_time(now, tz),
        "tz": tz,
    })


@app.post("/sail/{category}/{value}", response_class=HTMLResponse)
async def toggle_sail(request: Request, category: str, value: str) -> Response:
    """
    Toggle a sail selection. Returns updated sail selector partial.

    HTMX calls this when user taps a sail button.
    If tapping already-selected sail, it deselects (sends empty value).
    """
    # Get current pending state from form data (hidden inputs track pending state)
    form = await request.form()

    current_main = form.get("pending_main", "DOWN")
    current_headsail = form.get("pending_headsail", "")
    current_downwind = form.get("pending_downwind", "")
    current_staysail = form.get("pending_staysail", "false") == "true"
    current_central = form.get("pending_central", "UP")
    current_cfoil = form.get("pending_cfoil", "UP")
    current_cfoil_rake = form.get("pending_cfoil_rake", "0")

    # Initialize new values from current
    new_main = current_main
    new_headsail = current_headsail
    new_downwind = current_downwind
    new_staysail = current_staysail
    new_central = current_central
    new_cfoil = current_cfoil
    new_cfoil_rake = current_cfoil_rake

    # Apply the toggle based on category
    # Rules:
    # - Headsails are mutually exclusive (only one at a time)
    # - Downwind sails are mutually exclusive (only one at a time)
    # - Headsails and downwind are mutually exclusive, EXCEPT Jib + Reaching Spin
    # - Staysail mode only available with Jib + Reaching Spin combo
    # - Boards are independent of sails and each other
    # - Rake only relevant when C-foil is deployed (HALF or FULL)

    if category == "main":
        new_main = value if value != current_main else "DOWN"

    elif category == "headsail":
        new_headsail = "" if value == current_headsail else value
        new_staysail = False  # Reset staysail on any headsail change

        # Headsail/downwind mutual exclusion (except Jib + Reaching Spin)
        if new_headsail == "":
            # Deselecting headsail - keep downwind as is
            pass
        elif new_headsail == "JIB" and current_downwind == "REACHING_SPI":
            # Jib + Reaching Spin is allowed
            new_staysail = current_staysail
        else:
            # Any other headsail clears downwind
            new_downwind = ""

    elif category == "downwind":
        new_downwind = "" if value == current_downwind else value
        new_staysail = False  # Reset staysail on any downwind change

        # Headsail/downwind mutual exclusion (except Jib + Reaching Spin)
        if new_downwind == "":
            # Deselecting downwind - keep headsail as is
            pass
        elif new_downwind == "REACHING_SPI" and current_headsail == "JIB":
            # Reaching Spin + Jib is allowed
            new_staysail = current_staysail
        else:
            # Any other downwind clears headsail
            new_headsail = ""

    elif category == "central":
        # Central board toggle - UP acts as "deselect"
        new_central = value if value != current_central else "UP"

    elif category == "cfoil":
        # C-foil board toggle - UP acts as "deselect"
        new_cfoil = value if value != current_cfoil else "UP"
        # Reset rake when C-foil is raised
        if new_cfoil == "UP":
            new_cfoil_rake = "0"

    elif category == "cfoil_rake":
        # Rake toggle - "0" acts as default/deselect
        new_cfoil_rake = value if value != current_cfoil_rake else "0"

    pending = {
        "main": new_main,
        "headsail": new_headsail,
        "downwind": new_downwind,
        "staysail_mode": new_staysail,
        "central_board": new_central,
        "cfoil_board": new_cfoil,
        "cfoil_rake": new_cfoil_rake,
    }

    committed = get_current_sail_config()
    has_changes = (
        pending["main"] != committed["main"]
        or pending["headsail"] != committed["headsail"]
        or pending["downwind"] != committed["downwind"]
        or pending["staysail_mode"] != committed["staysail_mode"]
        or pending["central_board"] != committed["central_board"]
        or pending["cfoil_board"] != committed["cfoil_board"]
        or pending["cfoil_rake"] != committed["cfoil_rake"]
    )
    
    return templates.TemplateResponse(request, "partials/sail_selector.html", {
        "pending": pending,
        "committed": committed,
        "has_changes": has_changes,
        "summary": format_config_summary(pending),
    })


@app.post("/staysail/toggle", response_class=HTMLResponse)
async def toggle_staysail(request: Request) -> Response:
    """Toggle staysail mode."""
    form = await request.form()

    pending = {
        "main": form.get("pending_main", "DOWN"),
        "headsail": form.get("pending_headsail", ""),
        "downwind": form.get("pending_downwind", ""),
        "staysail_mode": form.get("pending_staysail", "false") != "true",  # Toggle
        "central_board": form.get("pending_central", "UP"),
        "cfoil_board": form.get("pending_cfoil", "UP"),
        "cfoil_rake": form.get("pending_cfoil_rake", "0"),
    }

    committed = get_current_sail_config()
    has_changes = (
        pending["main"] != committed["main"]
        or pending["headsail"] != committed["headsail"]
        or pending["downwind"] != committed["downwind"]
        or pending["staysail_mode"] != committed["staysail_mode"]
        or pending["central_board"] != committed["central_board"]
        or pending["cfoil_board"] != committed["cfoil_board"]
        or pending["cfoil_rake"] != committed["cfoil_rake"]
    )

    return templates.TemplateResponse(request, "partials/sail_selector.html", {
        "pending": pending,
        "committed": committed,
        "has_changes": has_changes,
        "summary": format_config_summary(pending),
    })


@app.post("/save", response_class=HTMLResponse)
async def save_config(request: Request) -> Response:
    """Save current configuration to QuestDB."""
    form = await request.form()

    main = form.get("pending_main", "DOWN")
    headsail = form.get("pending_headsail", "")
    downwind = form.get("pending_downwind", "")
    staysail_mode = form.get("pending_staysail", "false") == "true"
    comment = form.get("comment", "")
    central_board = form.get("pending_central", "UP")
    cfoil_board = form.get("pending_cfoil", "UP")
    cfoil_rake = form.get("pending_cfoil_rake", "0")

    # Handle backdating
    backdate = form.get("backdate_enabled", "false") == "true"
    timestamp = None
    if backdate:
        date_str = form.get("backdate_date", "")
        hour = int(form.get("backdate_hour", 0))
        minute = int(form.get("backdate_minute", 0))
        if date_str:
            tz = get_boat_timezone()
            from datetime import date as date_type
            d = date_type.fromisoformat(date_str)
            # Add random microseconds to prevent timestamp collisions: the table
            # dedups on (ts, vessel), so identical timestamps would overwrite.
            random_microseconds = random.randint(0, 999999)
            local_dt = datetime(d.year, d.month, d.day, hour, minute, 0, random_microseconds, tzinfo=tz)
            timestamp = local_dt.astimezone(timezone.utc)

    success = write_sail_config(
        main, headsail, downwind, staysail_mode, comment,
        central_board, cfoil_board, cfoil_rake, timestamp
    )

    # Return updated sail selector
    config = get_current_sail_config()

    response = templates.TemplateResponse(request, "partials/sail_selector.html", {
        "pending": config,  # After save, pending = committed
        "committed": config,
        "has_changes": False,
        "summary": format_config_summary(config),
        "save_success": success,
    })

    # Use HX-Trigger header to reliably trigger history refresh
    if success:
        response.headers["HX-Trigger"] = "historyUpdate"

    return response


def format_history_entry(entry: dict[str, Any]) -> str:
    """Format a history entry for display."""
    parts = []
    if entry["main"]:
        parts.append(f"M:{entry['main']}")
    if entry["headsail"]:
        h = SAIL_DISPLAY.get(entry["headsail"], entry["headsail"])
        if entry["staysail_mode"]:
            h += "(S)"
        parts.append(h)
    if entry["downwind"]:
        parts.append(SAIL_DISPLAY.get(entry["downwind"], entry["downwind"]))

    # Add board state
    central = entry.get("central_board") or "UP"
    cfoil = entry.get("cfoil_board") or "UP"
    if central != "UP":
        parts.append(f"C:{SAIL_DISPLAY.get(central, central)}")
    if cfoil != "UP":
        rake = entry.get("cfoil_rake") or "0"
        parts.append(f"F:{SAIL_DISPLAY.get(cfoil, cfoil)}@{rake}°")

    return " + ".join(parts) if parts else "All down"


@app.get("/history", response_class=HTMLResponse)
async def get_history(request: Request) -> Response:
    """Get history panel content."""
    entries = get_recent_entries(50)
    tz = get_boat_timezone()

    # Format entries for display
    formatted = []
    for entry in entries:
        formatted.append({
            "time": entry["time"],
            "time_str": format_local_datetime(entry["time"], tz),
            "config": format_history_entry(entry),
            "comment": entry.get("comment", ""),
            "iso": entry["time"].isoformat(),
        })

    return templates.TemplateResponse(request, "partials/history.html", {
        "entries": formatted,
    })


@app.delete("/entry/{timestamp}", response_class=HTMLResponse)
async def delete_entry(request: Request, timestamp: str) -> Response:
    """Delete a history entry."""
    dt = datetime.fromisoformat(timestamp)
    delete_sail_entry(dt)

    # Return updated history with flag to trigger config refresh
    entries = get_recent_entries(50)
    tz = get_boat_timezone()

    formatted = []
    for entry in entries:
        formatted.append({
            "time": entry["time"],
            "time_str": format_local_datetime(entry["time"], tz),
            "config": format_history_entry(entry),
            "comment": entry.get("comment", ""),
            "iso": entry["time"].isoformat(),
        })

    return templates.TemplateResponse(request, "partials/history.html", {
        "entries": formatted,
        "after_delete": True,
    })


@app.get("/time", response_class=HTMLResponse)
async def get_time(request: Request) -> str:
    """Get current time (for periodic refresh)."""
    tz = get_boat_timezone()
    now = datetime.now(timezone.utc)
    return format_local_time(now, tz)


@app.get("/config", response_class=HTMLResponse)
async def get_config(request: Request) -> Response:
    """Get current sail config partial (for refresh after delete)."""
    config = get_current_sail_config()
    return templates.TemplateResponse(request, "partials/sail_selector.html", {
        "pending": config,
        "committed": config,
        "has_changes": False,
        "summary": format_config_summary(config),
    })
