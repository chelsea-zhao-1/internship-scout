import base64
import json
import os
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _build_service():
    creds_raw = os.environ.get("GMAIL_CREDENTIALS")
    token_raw = os.environ.get("GMAIL_TOKEN")

    if not token_raw:
        raise RuntimeError("GMAIL_TOKEN environment variable is not set")

    token_data = json.loads(token_raw)

    # Extract client_id / client_secret — prefer GMAIL_CREDENTIALS but fall back
    # to values embedded inside the token file (both formats work).
    if creds_raw:
        creds_data = json.loads(creds_raw)
        # credentials.json may nest under "installed" or "web"
        client_info = creds_data.get("installed") or creds_data.get("web") or creds_data
        client_id = client_info["client_id"]
        client_secret = client_info["client_secret"]
        token_uri = client_info.get("token_uri", "https://oauth2.googleapis.com/token")
    else:
        client_id = token_data["client_id"]
        client_secret = token_data["client_secret"]
        token_uri = token_data.get("token_uri", "https://oauth2.googleapis.com/token")

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data["refresh_token"],
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("gmail", "v1", credentials=creds)


def send_email(subject: str, body: str) -> None:
    recipient = os.environ.get("NOTIFY_EMAIL")
    if not recipient:
        raise RuntimeError("NOTIFY_EMAIL environment variable is not set")

    service = _build_service()

    message = MIMEText(body, "plain")
    message["to"] = recipient
    message["subject"] = subject

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId="me", body={"raw": encoded}
    ).execute()
