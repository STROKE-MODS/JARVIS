"""
JARVIS Phase 7 — Gmail Integration
Handles:
  - OAuth2 authentication (one-time browser consent, then cached token)
  - Reading recent/unread emails
  - Reading a specific email's full content
  - Sending emails

Requires credentials.json (from Google Cloud Console, OAuth Desktop App
client) in the project root. On first use, a browser window opens for you
to grant access — after that, a token.json is cached so it won't ask again
until the token expires or scopes change.
"""

import os
import base64
import pickle
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# read + send needs both scopes — readonly alone would block sending
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

CREDENTIALS_PATH = os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = "token.json"

_service = None  # cached Gmail API client, built once per process


def _get_service():
    """Return an authenticated Gmail API client, building/caching it on
    first call. Runs the OAuth consent flow in a browser only if no valid
    cached token exists yet."""
    global _service
    if _service is not None:
        return _service

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Gmail credentials not found at '{CREDENTIALS_PATH}'. "
                    "Download OAuth Desktop App credentials from Google Cloud "
                    "Console and save them there, or set GMAIL_CREDENTIALS_PATH "
                    "in .env to the correct path."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    _service = build("gmail", "v1", credentials=creds)
    return _service


def _decode_body(payload) -> str:
    """Extract plain-text body from a Gmail message payload, handling
    both simple and multipart messages."""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        # No plain text part found — recurse into nested multiparts
        for part in payload["parts"]:
            if "parts" in part:
                result = _decode_body(part)
                if result:
                    return result
        return ""
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""


def check_unread_emails(max_results: int = 5) -> str:
    """List recent unread emails — sender, subject, and a short snippet."""
    try:
        service = _get_service()
        results = service.users().messages().list(
            userId="me", labelIds=["UNREAD", "INBOX"], maxResults=max_results
        ).execute()
        messages = results.get("messages", [])

        if not messages:
            return "You have no unread emails, Sir."

        summaries = []
        for m in messages:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject"]
            ).execute()
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            sender = headers.get("From", "Unknown sender")
            subject = headers.get("Subject", "(no subject)")
            snippet = msg.get("snippet", "")[:100]
            summaries.append(f"From {sender}: '{subject}' — {snippet}")

        count = len(messages)
        listing = "; ".join(summaries)
        return f"You have {count} unread email{'s' if count != 1 else ''}, Sir: {listing}"

    except FileNotFoundError as e:
        return str(e)
    except HttpError as e:
        return f"Gmail API error, Sir: {e}"
    except Exception as e:
        return f"Could not check emails, Sir: {e}"


def read_latest_email() -> str:
    """Read the full body of the most recent email in the inbox."""
    try:
        service = _get_service()
        results = service.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=1
        ).execute()
        messages = results.get("messages", [])

        if not messages:
            return "Your inbox is empty, Sir."

        msg = service.users().messages().get(
            userId="me", id=messages[0]["id"], format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        sender = headers.get("From", "Unknown sender")
        subject = headers.get("Subject", "(no subject)")
        body = _decode_body(msg["payload"]).strip()

        body_preview = body[:500] + ("..." if len(body) > 500 else "")
        return f"Latest email, Sir — From {sender}, Subject: '{subject}'. {body_preview}"

    except FileNotFoundError as e:
        return str(e)
    except HttpError as e:
        return f"Gmail API error, Sir: {e}"
    except Exception as e:
        return f"Could not read email, Sir: {e}"


def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail. Requires the gmail.send scope (already
    included in SCOPES above)."""
    if not to or "@" not in to:
        return "I need a valid recipient email address, Sir."

    try:
        service = _get_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject or "(no subject)"

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        service.users().messages().send(userId="me", body={"raw": raw}).execute()

        return f"Email sent to {to}, Sir. Subject: '{subject}'."

    except FileNotFoundError as e:
        return str(e)
    except HttpError as e:
        return f"Gmail API error while sending, Sir: {e}"
    except Exception as e:
        return f"Could not send email, Sir: {e}"