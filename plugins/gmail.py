"""
plugins/gmail.py — Reads and sends Gmail via OAuth. Reuses the same Google
Cloud OAuth client as plugins/google_calendar.py (no new credentials needed),
but keeps its own separate token file since it needs a different permission
scope. First use opens a browser for one-time consent for this new scope.

Guards sending/replying behind Demo Mode (core/demo_mode.py) — listing and
reading email still work normally even with demo mode on.
"""
import base64
import importlib.util
import json
import sys
from email.mime.text import MIMEText
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from memory.config_manager import get_plugin_config

_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_last_emails_cache: list[dict] = []


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _token_path() -> Path:
    return _base_dir() / "config" / "gmail_token.json"


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


def _truthy(value, default: bool) -> bool:
    """The model sends booleans as strings ('false', 'no'), so `is False` never matched."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "1", "y")


def _unread_total(service) -> int | None:
    """Exact unread count for the inbox (the list only fetches a few messages)."""
    try:
        label = service.users().labels().get(userId="me", id="INBOX").execute()
        return int(label.get("messagesUnread", 0))
    except Exception:
        return None


def _plugin_config() -> dict:
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
        raise RuntimeError("Gmail isn't connected — add your Client ID and Secret first (same as Calendar).")

    flow = InstalledAppFlow.from_client_config(_client_config(), _SCOPES)
    creds = flow.run_local_server(port=0, timeout_seconds=120)   # browser consent, gives up after 2 min
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _get_service():
    return build("gmail", "v1", credentials=_get_credentials())


def _header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    for part in payload.get("parts", []) or []:
        result = _extract_body(part)
        if result:
            return result

    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        import re
        html = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        return re.sub(r"<[^>]+>", " ", html).strip()

    return ""


def _fetch_list(service, query: str, max_results: int) -> list[dict]:
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = result.get("messages", [])

    out = []
    for m in messages:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date", "Message-ID"],
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        out.append({
            "id": m["id"],
            "threadId": msg.get("threadId", ""),
            "from": _header(headers, "From"),
            "subject": _header(headers, "Subject") or "(no subject)",
            "date": _header(headers, "Date"),
            "message_id_header": _header(headers, "Message-ID"),
        })
    return out


def _send_email(service, to: str, subject: str, body: str,
                 thread_id: str = None, in_reply_to: str = None) -> None:
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    body_payload = {"raw": raw}
    if thread_id:
        body_payload["threadId"] = thread_id

    service.users().messages().send(userId="me", body=body_payload).execute()


def run(parameters: dict, player=None, session_memory=None) -> str:
    global _last_emails_cache
    params = parameters or {}
    action = (params.get("action") or "list").strip().lower()

    if action in ("send", "reply"):
        dm = _get_demo_mode_module()
        try:
            demo_on = bool(dm and dm.is_demo_mode())
        except Exception:
            demo_on = False
        if demo_on:
            return "Sending is disabled while demo mode is on, sir."

    try:
        service = _get_service()
    except Exception as e:
        msg = f"Sir, I couldn't connect to Gmail: {e}"
        _log(msg, player)
        return msg

    if action == "send":
        to      = (params.get("to") or "").strip()
        subject = (params.get("subject") or "").strip()
        body    = (params.get("body") or "").strip()
        if not to or not subject or not body:
            return "I need a recipient, subject, and message body to send an email, sir."
        try:
            _send_email(service, to, subject, body)
        except Exception as e:
            msg = f"Sir, I couldn't send that email: {e}"
            _log(msg, player)
            return msg
        msg = f"Email sent to {to}, sir."
        _log(msg, player)
        return msg

    if action == "reply":
        index = params.get("index")
        body  = (params.get("body") or "").strip()
        if not index or not body:
            return "I need to know which email to reply to, and what to say, sir."
        try:
            idx = int(index) - 1
            original = _last_emails_cache[idx]
        except (ValueError, IndexError):
            return "I don't have that email cached, sir — try listing your inbox again first."

        to_addr = original["from"]
        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        try:
            _send_email(service, to_addr, subject, body,
                        thread_id=original["threadId"],
                        in_reply_to=original["message_id_header"])
        except Exception as e:
            msg = f"Sir, I couldn't send that reply: {e}"
            _log(msg, player)
            return msg
        msg = f"Reply sent to {to_addr}, sir."
        _log(msg, player)
        return msg

    if action == "read":
        index = params.get("index")
        if not index:
            return "Which email, sir? Give me a number from the list."
        try:
            idx = int(index) - 1
            cached = _last_emails_cache[idx]
        except (ValueError, IndexError):
            return "I don't have that email cached, sir — try listing your inbox again first."

        try:
            full = service.users().messages().get(userId="me", id=cached["id"], format="full").execute()
            body_text = _extract_body(full.get("payload", {})) or "(no readable body found)"
            service.users().messages().modify(
                userId="me", id=cached["id"], body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except Exception as e:
            msg = f"Sir, I couldn't open that email: {e}"
            _log(msg, player)
            return msg

        msg = (
            f"From {cached['from']}, subject '{cached['subject']}':\n{body_text[:2000]}"
        )
        _log(f"Read email {index}: {cached['subject']}", player)
        return msg

    # action == "list" (default)
    unread_only = _truthy(params.get("unread_only"), default=True)
    query = "in:inbox is:unread" if unread_only else "in:inbox"
    max_results = params.get("max_results")
    try:
        max_results = int(max_results) if max_results else 8
    except (TypeError, ValueError):
        max_results = 8
    max_results = max(1, min(max_results, 20))

    try:
        emails = _fetch_list(service, query, max_results)
    except Exception as e:
        msg = f"Sir, I couldn't fetch your inbox: {e}"
        _log(msg, player)
        return msg

    _last_emails_cache = emails

    if not emails:
        msg = "Your inbox is clear, sir — nothing unread." if "is:unread" in query else "No emails found, sir."
        _log(msg, player)
        return msg

    def _sender(raw: str) -> str:
        return raw.split("<")[0].strip().strip('"') or raw

    lines = [f"{i+1}. From {_sender(e['from'])}: '{e['subject']}'" for i, e in enumerate(emails)]
    total = _unread_total(service) if unread_only else None
    if total is not None and total > len(emails):
        head = f"You have {total} unread emails, sir. The latest {len(emails)}: "
    elif unread_only:
        head = f"You have {len(emails)} unread email(s), sir: "
    else:
        head = f"Your latest {len(emails)} email(s), sir: "
    msg = head + "; ".join(lines)
    _log(msg, player)
    _show(player, "Gmail", head + "\n" + "\n".join(lines))
    return msg


def _log(message: str, player=None) -> None:
    print(f"[Gmail] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


def _show(player, title: str, text: str) -> None:
    """Puts the list in the HUD's content panel, if the UI supports it."""
    if player and hasattr(player, "show_content"):
        try:
            player.show_content(title, text)
        except Exception:
            pass


PLUGIN = {
    "name": "gmail",
    "description": (
        "Reads and sends Gmail. action='list' (default) shows unread inbox "
        "emails, numbered, plus the exact total unread count — trigger on 'check my "
        "email', 'how many unread emails', 'what's in my inbox'. "
        "action='read' with index (the number from the list) reads that email's "
        "full content and marks it read — trigger on 'read email 2', 'open the "
        "first one'. action='send' with to, subject, body sends a new email. "
        "action='reply' with index and body replies to a previously-listed "
        "email — trigger on 'reply to that saying...'. Numbers refer to the "
        "most recent list shown, so list before reading/replying by number."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action":      {"type": "STRING", "description": "'list', 'read', 'send', or 'reply'. Defaults to 'list'."},
            "index":       {"type": "NUMBER", "description": "Email number from the last list shown. Required for 'read' and 'reply'."},
            "to":          {"type": "STRING", "description": "Recipient email address. Required for 'send'."},
            "subject":     {"type": "STRING", "description": "Email subject. Required for 'send'."},
            "body":        {"type": "STRING", "description": "Email body text. Required for 'send' and 'reply'."},
            "unread_only": {"type": "STRING", "description": "Set to 'false' to list all inbox emails, not just unread. Defaults to unread-only."},
            "max_results": {"type": "NUMBER", "description": "How many emails to list. Defaults to 8."}
        },
        "required": []
    },
}

# No PLUGIN_SETTINGS here: Gmail reuses the Client ID/Secret entered in the
# Google Calendar plugin settings. Declaring the same settings block twice made
# two identical "Google Calendar" panels.