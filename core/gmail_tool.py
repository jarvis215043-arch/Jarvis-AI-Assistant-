"""
core/gmail_tools.py — Gmail integration for JARVIS.

Capabilities:
  - count / list / search emails            (list_emails, count_unread)
  - read a full email                       (read_email)
  - summarize unread mail using your LLM    (summarize_inbox)
  - create drafts                           (create_draft)
  - send + reply (with a confirmation gate) (send_email, reply_to_email)
  - mark as read                            (mark_as_read)

Setup files (both live in JARVIS's config/ folder):
  config/gmail_credentials.json  <- OAuth "Desktop app" client, downloaded from Google Cloud
  config/gmail_token.json        <- created automatically after your first login

First-time login / quick test:
    python core/gmail_tools.py

Safety: send_email() and reply_to_email() do NOT send unless confirmed=True.
Without it they return a preview, so JARVIS can read the draft back to you and
only send after you say yes.

Requires:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""
import base64
import html
import importlib.util
import re
import sys
from email.message import EmailMessage
from pathlib import Path

# gmail.modify = read, send, draft, label. It can NOT permanently delete mail.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_service_cache = None


# ─────────────────────────────────────────────────────────────
# Paths / auth
# ─────────────────────────────────────────────────────────────
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config_dir() -> Path:
    d = _base_dir() / "config"
    d.mkdir(exist_ok=True)
    return d


def _calendar_client_config():
    """Builds an OAuth client config from the Google Calendar plugin's credentials
    (plugin settings first, then config/api_keys.json). Returns None if absent."""
    client_id = client_secret = ""
    try:
        from memory.config_manager import get_plugin_config
        cfg = get_plugin_config("google_calendar") or {}
        client_id = cfg.get("client_id", "")
        client_secret = cfg.get("client_secret", "")
    except Exception:
        pass
    if not client_id or not client_secret:
        try:
            import json
            api_cfg = json.loads((_config_dir() / "api_keys.json").read_text(encoding="utf-8"))
            client_id = client_id or api_cfg.get("google_calendar_client_id", "")
            client_secret = client_secret or api_cfg.get("google_calendar_client_secret", "")
        except Exception:
            pass
    if not client_id or not client_secret:
        return None
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def _service():
    """Authenticated Gmail API client (cached). Opens a browser on first run."""
    global _service_cache
    if _service_cache is not None:
        return _service_cache

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token_path = _config_dir() / "gmail_token.json"
    creds_path = _config_dir() / "gmail_credentials.json"

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None  # refresh token dead/revoked -> log in again

        if not creds or not creds.valid:
            if creds_path.exists():
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            else:
                # No separate Gmail file: reuse the Google Calendar OAuth client.
                # One OAuth client works for every API enabled in the project.
                client_config = _calendar_client_config()
                if client_config is None:
                    raise FileNotFoundError(
                        f"Gmail isn't set up yet: {creds_path} is missing and no "
                        "Google Calendar client_id/client_secret was found to reuse."
                    )
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json(), encoding="utf-8")

    _service_cache = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _service_cache


# ─────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────
def _headers(msg: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _decode(data: str) -> str:
    data += "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    return re.sub(r"\n\s*\n+", "\n\n", raw).strip()


def _extract_body(payload: dict) -> str:
    """Prefer text/plain; fall back to stripped text/html."""
    plain, htm = [], []

    def walk(part: dict):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            htm.append(_decode(data))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    if htm:
        return _html_to_text("\n".join(htm))
    return ""


def _build_raw(to: str, subject: str, body: str, cc: str = "", extra: dict | None = None) -> str:
    m = EmailMessage()
    m["To"] = to
    m["Subject"] = subject
    if cc:
        m["Cc"] = cc
    for k, v in (extra or {}).items():
        m[k] = v
    m.set_content(body)
    return base64.urlsafe_b64encode(m.as_bytes()).decode()


# ─────────────────────────────────────────────────────────────
# Reading
# ─────────────────────────────────────────────────────────────
def count_unread() -> int:
    label = _service().users().labels().get(userId="me", id="INBOX").execute()
    return int(label.get("messagesUnread", 0))


def list_emails(query: str = "is:unread in:inbox", max_results: int = 5) -> list[dict]:
    """
    query uses normal Gmail search syntax, e.g.
      "is:unread"                     "from:amazon newer_than:7d"
      "subject:invoice has:attachment"  "is:starred"
    """
    svc = _service()
    res = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    out = []
    for m in res.get("messages", []):
        msg = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        h = _headers(msg)
        out.append({
            "id": m["id"],
            "from": h.get("from", "?"),
            "subject": h.get("subject", "(no subject)"),
            "date": h.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "unread": "UNREAD" in msg.get("labelIds", []),
        })
    return out


def read_email(message_id: str, max_chars: int = 4000) -> dict:
    msg = _service().users().messages().get(userId="me", id=message_id, format="full").execute()
    h = _headers(msg)
    body = _extract_body(msg.get("payload", {})) or msg.get("snippet", "")
    return {
        "id": message_id,
        "from": h.get("from", "?"),
        "to": h.get("to", ""),
        "subject": h.get("subject", "(no subject)"),
        "date": h.get("date", ""),
        "body": body[:max_chars],
    }


def mark_as_read(message_id: str) -> str:
    _service().users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()
    return "Marked as read."


# ─────────────────────────────────────────────────────────────
# Writing (drafts / send / reply)
# ─────────────────────────────────────────────────────────────
def create_draft(to: str, subject: str, body: str, cc: str = "") -> str:
    raw = _build_raw(to, subject, body, cc)
    _service().users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return f"Draft to {to} saved in your Gmail drafts."


def send_email(to: str, subject: str, body: str, cc: str = "", confirmed: bool = False) -> str:
    if not confirmed:
        return (
            "PREVIEW (not sent yet)\n"
            f"To: {to}\nSubject: {subject}\n\n{body}\n\n"
            "Say the word and I'll send it."
        )
    raw = _build_raw(to, subject, body, cc)
    _service().users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Email sent to {to}."


def reply_to_email(message_id: str, body: str, confirmed: bool = False) -> str:
    svc = _service()
    orig = svc.users().messages().get(
        userId="me", id=message_id, format="metadata",
        metadataHeaders=["From", "Reply-To", "Subject", "Message-ID", "References"],
    ).execute()
    h = _headers(orig)

    to = h.get("reply-to") or h.get("from", "")
    subject = h.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    if not confirmed:
        return (
            "REPLY PREVIEW (not sent yet)\n"
            f"To: {to}\nSubject: {subject}\n\n{body}\n\n"
            "Say the word and I'll send it."
        )

    msg_id = h.get("message-id", "")
    refs = (h.get("references", "") + " " + msg_id).strip()
    raw = _build_raw(to, subject, body, extra={"In-Reply-To": msg_id, "References": refs})
    svc.users().messages().send(
        userId="me", body={"raw": raw, "threadId": orig.get("threadId")}
    ).execute()
    return f"Reply sent to {to}."


# ─────────────────────────────────────────────────────────────
# LLM-powered summary (uses your existing Gemini -> Ollama fallback)
# ─────────────────────────────────────────────────────────────
def _load_generate_text():
    try:
        from core.text_generation import generate_text
        return generate_text
    except Exception:
        pass
    path = _base_dir() / "core" / "text_generation.py"
    if not path.exists():
        return None
    key = "jarvis_ext_text_generation"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
    return sys.modules[key].generate_text


def summarize_inbox(max_results: int = 5) -> str:
    emails = list_emails("is:unread in:inbox", max_results)
    if not emails:
        return "Your inbox is clear — no unread emails."

    gen = _load_generate_text()
    parts = []
    for i, e in enumerate(emails, 1):
        full = read_email(e["id"], max_chars=1200)
        parts.append(f"[{i}] From: {full['from']}\nSubject: {full['subject']}\n{full['body']}")

    if gen is None:  # no LLM available -> plain list
        return "\n".join(f"{i}. {e['from']} — {e['subject']}" for i, e in enumerate(emails, 1))

    prompt = (
        "You are JARVIS, a concise voice assistant. Summarize these unread emails for the user. "
        "One short line per email: who it's from and what they want. Flag anything urgent or "
        "needing a reply. Plain text, no markdown, no preamble.\n\n" + "\n\n---\n\n".join(parts)
    )
    return gen(prompt)


# ─────────────────────────────────────────────────────────────
# Single entry point for JARVIS
# ─────────────────────────────────────────────────────────────
def _fmt_list(emails: list[dict]) -> str:
    if not emails:
        return "No matching emails found."
    lines = []
    for i, e in enumerate(emails, 1):
        name = e["from"].split("<")[0].strip().strip('"') or e["from"]
        lines.append(f"{i}. {name} — {e['subject']}  (id: {e['id']})")
    return "\n".join(lines)


def handle(action: str, **kw) -> str:
    """
    JARVIS calls this. Always returns a string that's safe to speak/show.
      handle("count")
      handle("list", query="from:boss", max_results=3)
      handle("read", message_id="...")
      handle("summarize")
      handle("draft", to="a@b.com", subject="Hi", body="...")
      handle("send",  to="a@b.com", subject="Hi", body="...", confirmed=True)
      handle("reply", message_id="...", body="...", confirmed=True)
      handle("mark_read", message_id="...")
    """
    try:
        a = (action or "").lower().strip()
        if a in ("count", "count_unread"):
            n = count_unread()
            return f"You have {n} unread email{'s' if n != 1 else ''}."
        if a in ("list", "search", "check"):
            return _fmt_list(list_emails(kw.get("query", "is:unread in:inbox"),
                                         int(kw.get("max_results", 5))))
        if a == "read":
            e = read_email(kw["message_id"])
            return f"From: {e['from']}\nSubject: {e['subject']}\nDate: {e['date']}\n\n{e['body']}"
        if a in ("summarize", "summary"):
            return summarize_inbox(int(kw.get("max_results", 5)))
        if a == "draft":
            return create_draft(kw["to"], kw["subject"], kw["body"], kw.get("cc", ""))
        if a == "send":
            return send_email(kw["to"], kw["subject"], kw["body"], kw.get("cc", ""),
                              bool(kw.get("confirmed", False)))
        if a == "reply":
            return reply_to_email(kw["message_id"], kw["body"], bool(kw.get("confirmed", False)))
        if a in ("mark_read", "mark_as_read"):
            return mark_as_read(kw["message_id"])
        return f"Unknown Gmail action: {action}"
    except FileNotFoundError as e:
        return str(e)
    except KeyError as e:
        return f"Missing required field for Gmail '{action}': {e}"
    except Exception as e:
        return f"Gmail error: {e}"


if __name__ == "__main__":
    # First-run login + smoke test
    print(handle("count"))
    print(handle("list", max_results=3))