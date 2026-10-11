"""
plugins/google_calendar.py — Reads, creates, updates and deletes events on the
user's Google Calendar via OAuth. First use opens a browser for one-time consent;
after that, a saved token is reused (and auto-refreshed) silently.

Supports timed events (start + end or duration), all-day events, and multi-day
all-day events. Creating an event with the same title on the same day UPDATES
the existing one instead of making a duplicate.

Creating and deleting are blocked while Demo Mode (core/demo_mode.py) is on —
listing your calendar still works normally.
"""
import importlib.util
import json
import sys
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from memory.config_manager import get_plugin_config

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_TIME_FORMATS = ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"]


# ── Setup / auth ──────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _token_path() -> Path:
    return _base_dir() / "config" / "google_calendar_token.json"


def _get_demo_mode_module():
    key = "jarvis_ext_demo_mode"
    if key in sys.modules:
        return sys.modules[key]
    path = _base_dir() / "core" / "demo_mode.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(key, None)
        return None
    return mod


def _demo_mode_on() -> bool:
    dm = _get_demo_mode_module()
    try:
        return bool(dm and dm.is_demo_mode())
    except Exception:
        return False


def _plugin_config() -> dict:
    """Reads client_id/client_secret from the plugin settings UI, falling back to
    config/api_keys.json (google_calendar_client_id / _client_secret)."""
    cfg = {}
    try:
        cfg = get_plugin_config("google_calendar") or {}
    except Exception:
        cfg = {}
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        try:
            api_cfg = json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
            cfg = {
                "client_id":     cfg.get("client_id")     or api_cfg.get("google_calendar_client_id", ""),
                "client_secret": cfg.get("client_secret") or api_cfg.get("google_calendar_client_secret", ""),
            }
        except Exception:
            pass
    return cfg


def _client_config() -> dict:
    cfg = _plugin_config()
    return {
        "installed": {
            "client_id":     cfg.get("client_id", ""),
            "client_secret": cfg.get("client_secret", ""),
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def _get_credentials() -> Credentials:
    token_path = _token_path()
    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            creds = None

    cfg = _plugin_config()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise RuntimeError("Google Calendar isn't connected — add your Client ID and Secret first.")

    flow = InstalledAppFlow.from_client_config(_client_config(), _SCOPES)
    creds = flow.run_local_server(port=0, timeout_seconds=120)   # browser consent, gives up after 2 min
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _get_service():
    return build("calendar", "v3", credentials=_get_credentials())


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _local_tz():
    return datetime.now().astimezone().tzinfo


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("true", "yes", "1", "y")


def _parse_date(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _parse_time(text: str) -> dtime | None:
    text = (text or "").strip().upper().replace(".", "")
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _parse_datetime(value: str, fallback_day: date | None) -> datetime | None:
    """Accepts '2026-09-28T08:30:00', '2026-09-28 08:30', or just '8:30 AM'
    (combined with fallback_day). Returns a timezone-aware datetime or None."""
    value = (value or "").strip()
    if not value:
        return None
    dt = None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        t = _parse_time(value)
        if t is not None and fallback_day is not None:
            dt = datetime.combine(fallback_day, t)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_local_tz())
    return dt


def _fmt_day(d: date) -> str:
    return d.strftime("%A, %d %B %Y")


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _describe(ev: dict) -> str:
    """Human-readable line for one event, handling all-day events correctly."""
    title = ev.get("summary", "Untitled event")
    start, end = ev.get("start", {}), ev.get("end", {})
    if "date" in start:  # all-day (end date is exclusive in the Google API)
        s = date.fromisoformat(start["date"])
        e = date.fromisoformat(end.get("date", start["date"])) - timedelta(days=1)
        if e <= s:
            return f"All day — {title}"
        return f"All day {s.strftime('%d %b')} to {e.strftime('%d %b')} — {title}"
    s = datetime.fromisoformat(start["dateTime"])
    e = datetime.fromisoformat(end["dateTime"]) if "dateTime" in end else None
    span = f"{_fmt_time(s)}–{_fmt_time(e)}" if e else _fmt_time(s)
    if e and e.date() != s.date():
        span += f" (ends {e.strftime('%a %d %b')})"
    return f"{span} — {title}"


def _events_on(service, day: date, days: int = 1) -> list[dict]:
    tz = _local_tz()
    start = datetime.combine(day, dtime.min, tzinfo=tz)
    end = start + timedelta(days=max(1, days))
    result = service.events().list(
        calendarId="primary",
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def _matching(events: list[dict], title: str) -> list[dict]:
    t = title.strip().lower()
    return [ev for ev in events if (ev.get("summary") or "").strip().lower() == t]


# ── Actions ───────────────────────────────────────────────────────────────────

def _build_event_body(params: dict) -> tuple[dict | None, str, date | None]:
    """Returns (event_body, human_summary, day) or (None, error_message, None)."""
    title = (params.get("title") or "").strip()
    all_day = _truthy(params.get("all_day"))
    day = _parse_date(params.get("date") or "") or _parse_date(params.get("start_time") or "")

    if not title:
        return None, "I need a title for the event, sir.", None

    if all_day:
        if day is None:
            return None, "I need the date for that all-day event, sir.", None
        end_day = _parse_date(params.get("end_date") or "") or day
        if end_day < day:
            end_day = day
        body = {
            "summary": title,
            "start": {"date": day.isoformat()},
            "end":   {"date": (end_day + timedelta(days=1)).isoformat()},  # exclusive
        }
        if end_day == day:
            summary = f"'{title}' as an all-day event on {_fmt_day(day)}"
        else:
            summary = f"'{title}' as an all-day event from {_fmt_day(day)} to {_fmt_day(end_day)}"
        return body, summary, day

    start_dt = _parse_datetime(params.get("start_time") or "", day)
    if start_dt is None:
        return None, ("I need a start time for that event, sir — or say it's all day."), None
    day = start_dt.date()

    end_dt = _parse_datetime(params.get("end_time") or "", day)
    if end_dt is None:
        try:
            minutes = int(float(params.get("duration_minutes") or 60))
        except (TypeError, ValueError):
            minutes = 60
        end_dt = start_dt + timedelta(minutes=max(5, minutes))
    elif end_dt <= start_dt:
        # "7 AM till 12 AM" means midnight at the END of the day, not the start.
        end_dt += timedelta(days=1)

    body = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat()},
        "end":   {"dateTime": end_dt.isoformat()},
    }
    ends = _fmt_time(end_dt) if end_dt.date() == day else f"{_fmt_time(end_dt)} on {end_dt.strftime('%A %d %B')}"
    summary = f"'{title}' on {_fmt_day(day)} from {_fmt_time(start_dt)} to {ends}"
    return body, summary, day


def _create(service, params: dict, player) -> str:
    body, summary, day = _build_event_body(params)
    if body is None:
        return summary

    # Same title on the same day → update instead of creating a duplicate.
    existing = _matching(_events_on(service, day), body["summary"])
    if existing:
        service.events().update(calendarId="primary", eventId=existing[0]["id"], body=body).execute()
        for extra in existing[1:]:  # clean up older duplicates
            service.events().delete(calendarId="primary", eventId=extra["id"]).execute()
        msg = f"Updated {summary}, sir."
    else:
        service.events().insert(calendarId="primary", body=body).execute()
        msg = f"Booked {summary}, sir."

    _log(msg, player)
    _show(player, "Calendar", _day_listing(service, day))
    return msg


def _delete(service, params: dict, player) -> str:
    title = (params.get("title") or "").strip()
    day = _parse_date(params.get("date") or "") or _parse_date(params.get("start_time") or "")
    if not title or day is None:
        return "Tell me the event's title and date so I delete the right one, sir."
    matches = _matching(_events_on(service, day), title)
    if not matches:
        return f"I couldn't find '{title}' on {_fmt_day(day)}, sir."
    for ev in matches:
        service.events().delete(calendarId="primary", eventId=ev["id"]).execute()
    msg = f"Deleted {len(matches)} event(s) called '{title}' on {_fmt_day(day)}, sir."
    _log(msg, player)
    return msg


def _day_listing(service, day: date, days: int = 1) -> str:
    events = _events_on(service, day, days)
    label = _fmt_day(day) if days == 1 else f"{_fmt_day(day)} (+{days - 1} days)"
    if not events:
        return f"Nothing on the calendar for {label}."
    lines = [f"{label}:"]
    current = None
    for ev in events:
        s = ev["start"].get("date") or ev["start"].get("dateTime", "")[:10]
        if days > 1 and s != current:
            current = s
            lines.append(f"\n{date.fromisoformat(s).strftime('%A %d %B')}")
        lines.append(f"  • {_describe(ev)}")
    return "\n".join(lines)


def _list(service, params: dict, player) -> str:
    day = _parse_date(params.get("date") or "") or datetime.now().date()
    try:
        days = max(1, min(int(float(params.get("days") or 1)), 31))
    except (TypeError, ValueError):
        days = 1
    text = _day_listing(service, day, days)
    _log(text.replace("\n", " "), player)
    _show(player, "Calendar", text)
    return text + " sir."


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "list").strip().lower()

    if action in ("create", "add", "book", "update", "delete", "remove", "cancel") and _demo_mode_on():
        return "Changing calendar events is disabled while demo mode is on, sir."

    try:
        service = _get_service()
    except Exception as e:
        msg = f"Sir, I couldn't connect to Google Calendar: {e}"
        _log(msg, player)
        return msg

    try:
        if action in ("create", "add", "book", "update"):
            return _create(service, params, player)
        if action in ("delete", "remove", "cancel"):
            return _delete(service, params, player)
        return _list(service, params, player)
    except Exception as e:
        msg = f"Sir, the calendar request failed: {e}"
        _log(msg, player)
        return msg


def _log(message: str, player=None) -> None:
    print(f"[GoogleCalendar] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


def _show(player, title: str, text: str) -> None:
    """Puts the result in the HUD's content panel, if the UI supports it."""
    if player and hasattr(player, "show_content"):
        try:
            player.show_content(title, text)
        except Exception:
            pass


PLUGIN = {
    "name": "google_calendar",
    "description": (
        "Reads, creates, updates or deletes events on the user's Google Calendar. "
        "action='list' with date (YYYY-MM-DD, default today) and optional days (how many days to show). "
        "action='create' books an event: needs title plus EITHER all_day=true with date "
        "(and optional end_date for multi-day) OR start_time with end_time or duration_minutes. "
        "Creating the same title on the same day updates it instead of duplicating it, so use "
        "action='create' again to change an event's time. action='delete' with title and date removes it. "
        "Only call create once you know the title, the date, and either the times or that it is all day — "
        "ask the user for anything missing first. After it returns, repeat the booked date and times "
        "exactly as the result states them."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action":           {"type": "STRING",  "description": "'list', 'create' or 'delete'. Defaults to 'list'."},
            "title":            {"type": "STRING",  "description": "Event title. Required for create and delete."},
            "date":             {"type": "STRING",  "description": "Day of the event or day to list, YYYY-MM-DD."},
            "days":             {"type": "NUMBER",  "description": "For list: how many days to show from date (default 1, max 31)."},
            "all_day":          {"type": "BOOLEAN", "description": "True for an all-day event (no times needed)."},
            "end_date":         {"type": "STRING",  "description": "Last day of a multi-day all-day event, YYYY-MM-DD."},
            "start_time":       {"type": "STRING",  "description": "Start, ISO 8601 e.g. '2026-09-28T08:30:00' (or '08:30' together with date)."},
            "end_time":         {"type": "STRING",  "description": "End, ISO 8601 or 'HH:MM'. Midnight at the end of the day = '00:00'."},
            "duration_minutes": {"type": "NUMBER",  "description": "Length in minutes, used only if end_time is not given (default 60)."},
        },
        "required": [],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "google_calendar",
    "title": "Google Calendar",
    "fields": [
        {"key": "client_id", "label": "OAuth Client ID", "type": "text"},
        {"key": "client_secret", "label": "OAuth Client Secret", "type": "password"},
    ],
}