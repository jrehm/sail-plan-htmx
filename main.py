"""
Morticia Sail Plan Tracker - HTMX Version

FastAPI backend with HTMX-powered frontend for logging sail configurations.
"""

from __future__ import annotations

__version__ = "0.9.0"

import os
import tomllib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from timezonefinder import TimezoneFinder

# Load environment variables
load_dotenv()

# Configuration
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "openplotter")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "default")
SIGNALK_URL = os.getenv("SIGNALK_URL", "http://localhost:3000")

# Timezone finder (reused)
_tz_finder = TimezoneFinder()

# Load boat config
def load_boat_config() -> dict:
    app_dir = Path(__file__).parent
    config_path = app_dir / "boat_config.toml"
    example_path = app_dir / "boat_config.toml.example"
    
    if config_path.exists():
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    elif example_path.exists():
        with open(example_path, "rb") as f:
            return tomllib.load(f)
    else:
        raise FileNotFoundError("boat_config.toml not found")

_boat_config = load_boat_config()
BOAT_NAME = _boat_config.get("boat", {}).get("name", "Boat")
MAIN_STATES = _boat_config.get("sails", {}).get("main", {}).get("options", [])
HEADSAILS = _boat_config.get("sails", {}).get("headsail", {}).get("options", [])
DOWNWIND_SAILS = _boat_config.get("sails", {}).get("downwind", {}).get("options", [])
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
    except requests.RequestException:
        pass
    return None


def get_boat_timezone() -> ZoneInfo:
    """Get timezone from GPS position, fallback to local."""
    position = get_boat_position()
    if position:
        tz_name = _tz_finder.timezone_at(lat=position[0], lng=position[1])
        if tz_name:
            return ZoneInfo(tz_name)
    # Fallback to system timezone
    return datetime.now().astimezone().tzinfo


# ============ InfluxDB ============

def get_influx_client() -> InfluxDBClient:
    return InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)


def get_current_sail_config() -> dict:
    """Fetch most recent sail configuration."""
    client = get_influx_client()
    query_api = client.query_api()
    
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
        |> range(start: -30d)
        |> filter(fn: (r) => r["_measurement"] == "sail_config")
        |> filter(fn: (r) => r["vessel"] == "morticia")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> sort(columns: ["_time"], desc: true)
        |> limit(n: 1)
    '''
    
    def sanitize(val, default=""):
        """Convert None, 'None', or 'NONE' to default value."""
        if val is None or val == "None" or val == "NONE":
            return default
        return val

    try:
        tables = query_api.query(query)
        for table in tables:
            for record in table.records:
                client.close()
                return {
                    "main": sanitize(record.values.get("main"), "DOWN"),
                    "headsail": sanitize(record.values.get("headsail"), ""),
                    "downwind": sanitize(record.values.get("downwind"), ""),
                    "staysail_mode": record.values.get("staysail_mode", False),
                    "comment": sanitize(record.values.get("comment"), ""),
                }
    except Exception:
        pass
    
    client.close()
    return {"main": "DOWN", "headsail": "", "downwind": "", "staysail_mode": False, "comment": ""}


def write_sail_config(
    main: str,
    headsail: str,
    downwind: str,
    staysail_mode: bool,
    comment: str,
    timestamp: datetime | None = None,
) -> bool:
    """Write sail configuration to InfluxDB."""
    client = get_influx_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Use "NONE" placeholder instead of empty string to avoid InfluxDB field merging issues
    headsail = headsail if headsail else "NONE"
    downwind = downwind if downwind else "NONE"

    point = (
        Point("sail_config")
        .tag("vessel", "morticia")
        .field("main", main)
        .field("headsail", headsail)
        .field("downwind", downwind)
        .field("staysail_mode", staysail_mode)
        .field("comment", comment)
        .time(timestamp, WritePrecision.NS)
    )
    
    try:
        write_api.write(bucket=INFLUX_BUCKET, record=point)
        client.close()
        return True
    except Exception:
        client.close()
        return False


def get_recent_entries(limit: int = 50) -> list[dict]:
    """Fetch recent sail log entries."""
    client = get_influx_client()
    query_api = client.query_api()
    
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
        |> range(start: -7d)
        |> filter(fn: (r) => r["_measurement"] == "sail_config")
        |> filter(fn: (r) => r["vessel"] == "morticia")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> sort(columns: ["_time"], desc: true)
        |> limit(n: {limit})
    '''
    
    def sanitize(val):
        """Convert None or NONE placeholder to empty string."""
        if val is None or val == "None" or val == "NONE":
            return ""
        return val

    entries = []
    try:
        tables = query_api.query(query)
        for table in tables:
            for record in table.records:
                entries.append({
                    "time": record.get_time(),
                    "main": sanitize(record.values.get("main")) or "DOWN",
                    "headsail": sanitize(record.values.get("headsail")),
                    "downwind": sanitize(record.values.get("downwind")),
                    "staysail_mode": record.values.get("staysail_mode", False),
                    "comment": sanitize(record.values.get("comment")),
                })
    except Exception:
        pass
    
    client.close()
    return entries


def delete_sail_entry(timestamp: datetime) -> bool:
    """Delete a sail configuration entry."""
    client = get_influx_client()
    delete_api = client.delete_api()
    
    start = timestamp - timedelta(milliseconds=500)
    stop = timestamp + timedelta(milliseconds=500)
    
    try:
        delete_api.delete(
            start=start,
            stop=stop,
            predicate='_measurement="sail_config" AND vessel="morticia"',
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG,
        )
        client.close()
        return True
    except Exception:
        client.close()
        return False


# ============ Helper Functions ============

def format_config_summary(config: dict) -> str:
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

    if not headsail and not downwind and main == "DOWN":
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
async def index(request: Request):
    """Main page."""
    config = get_current_sail_config()
    tz = get_boat_timezone()
    now = datetime.now(timezone.utc)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "config": config,
        "summary": format_config_summary(config),
        "current_time": format_local_time(now, tz),
        "tz": tz,
    })


@app.post("/sail/{category}/{value}", response_class=HTMLResponse)
async def toggle_sail(request: Request, category: str, value: str):
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
    
    # Apply the toggle
    # Rules:
    # - Headsails are mutually exclusive (only one at a time)
    # - Downwind sails are mutually exclusive (only one at a time)
    # - Headsails and downwind are mutually exclusive, EXCEPT Jib + Reaching Spin
    # - Staysail mode only available with Jib + Reaching Spin combo

    if category == "main":
        new_main = value if value != current_main else "DOWN"
        new_headsail = current_headsail
        new_downwind = current_downwind
        new_staysail = current_staysail

    elif category == "headsail":
        new_main = current_main
        new_headsail = "" if value == current_headsail else value
        new_staysail = False  # Reset staysail on any headsail change

        # Headsail/downwind mutual exclusion (except Jib + Reaching Spin)
        if new_headsail == "":
            # Deselecting headsail - keep downwind as is
            new_downwind = current_downwind
        elif new_headsail == "JIB" and current_downwind == "REACHING_SPI":
            # Jib + Reaching Spin is allowed
            new_downwind = current_downwind
            new_staysail = current_staysail
        else:
            # Any other headsail clears downwind
            new_downwind = ""

    elif category == "downwind":
        new_main = current_main
        new_downwind = "" if value == current_downwind else value
        new_staysail = False  # Reset staysail on any downwind change

        # Headsail/downwind mutual exclusion (except Jib + Reaching Spin)
        if new_downwind == "":
            # Deselecting downwind - keep headsail as is
            new_headsail = current_headsail
        elif new_downwind == "REACHING_SPI" and current_headsail == "JIB":
            # Reaching Spin + Jib is allowed
            new_headsail = current_headsail
            new_staysail = current_staysail
        else:
            # Any other downwind clears headsail
            new_headsail = ""

    else:
        # Unknown category, return current state
        new_main = current_main
        new_headsail = current_headsail
        new_downwind = current_downwind
        new_staysail = current_staysail
    
    pending = {
        "main": new_main,
        "headsail": new_headsail,
        "downwind": new_downwind,
        "staysail_mode": new_staysail,
    }
    
    committed = get_current_sail_config()
    has_changes = (
        pending["main"] != committed["main"]
        or pending["headsail"] != committed["headsail"]
        or pending["downwind"] != committed["downwind"]
        or pending["staysail_mode"] != committed["staysail_mode"]
    )
    
    return templates.TemplateResponse("partials/sail_selector.html", {
        "request": request,
        "pending": pending,
        "committed": committed,
        "has_changes": has_changes,
        "summary": format_config_summary(pending),
    })


@app.post("/staysail/toggle", response_class=HTMLResponse)
async def toggle_staysail(request: Request):
    """Toggle staysail mode."""
    form = await request.form()
    
    pending = {
        "main": form.get("pending_main", "DOWN"),
        "headsail": form.get("pending_headsail", ""),
        "downwind": form.get("pending_downwind", ""),
        "staysail_mode": form.get("pending_staysail", "false") != "true",  # Toggle
    }
    
    committed = get_current_sail_config()
    has_changes = (
        pending["main"] != committed["main"]
        or pending["headsail"] != committed["headsail"]
        or pending["downwind"] != committed["downwind"]
        or pending["staysail_mode"] != committed["staysail_mode"]
    )
    
    return templates.TemplateResponse("partials/sail_selector.html", {
        "request": request,
        "pending": pending,
        "committed": committed,
        "has_changes": has_changes,
        "summary": format_config_summary(pending),
    })


@app.post("/save", response_class=HTMLResponse)
async def save_config(request: Request):
    """Save current configuration to InfluxDB."""
    form = await request.form()

    main = form.get("pending_main", "DOWN")
    headsail = form.get("pending_headsail", "")
    downwind = form.get("pending_downwind", "")
    staysail_mode = form.get("pending_staysail", "false") == "true"
    comment = form.get("comment", "")
    
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
            local_dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
            timestamp = local_dt.astimezone(timezone.utc)
    
    success = write_sail_config(main, headsail, downwind, staysail_mode, comment, timestamp)

    # Return updated sail selector
    config = get_current_sail_config()

    response = templates.TemplateResponse("partials/sail_selector.html", {
        "request": request,
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


@app.get("/history", response_class=HTMLResponse)
async def get_history(request: Request):
    """Get history panel content."""
    entries = get_recent_entries(50)
    tz = get_boat_timezone()

    # Format entries for display
    formatted = []
    for entry in entries:
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
        
        formatted.append({
            "time": entry["time"],
            "time_str": format_local_datetime(entry["time"], tz),
            "config": " + ".join(parts) if parts else "All down",
            "comment": entry.get("comment", ""),
            "iso": entry["time"].isoformat(),
        })
    
    return templates.TemplateResponse("partials/history.html", {
        "request": request,
        "entries": formatted,
    })


@app.delete("/entry/{timestamp}", response_class=HTMLResponse)
async def delete_entry(request: Request, timestamp: str):
    """Delete a history entry."""
    dt = datetime.fromisoformat(timestamp)
    delete_sail_entry(dt)

    # Return updated history with flag to trigger config refresh
    entries = get_recent_entries(50)
    tz = get_boat_timezone()

    formatted = []
    for entry in entries:
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

        formatted.append({
            "time": entry["time"],
            "time_str": format_local_datetime(entry["time"], tz),
            "config": " + ".join(parts) if parts else "All down",
            "comment": entry.get("comment", ""),
            "iso": entry["time"].isoformat(),
        })

    return templates.TemplateResponse("partials/history.html", {
        "request": request,
        "entries": formatted,
        "after_delete": True,
    })


@app.get("/time", response_class=HTMLResponse)
async def get_time(request: Request):
    """Get current time (for periodic refresh)."""
    tz = get_boat_timezone()
    now = datetime.now(timezone.utc)
    return format_local_time(now, tz)


@app.get("/config", response_class=HTMLResponse)
async def get_config(request: Request):
    """Get current sail config partial (for refresh after delete)."""
    config = get_current_sail_config()
    return templates.TemplateResponse("partials/sail_selector.html", {
        "request": request,
        "pending": config,
        "committed": config,
        "has_changes": False,
        "summary": format_config_summary(config),
    })
