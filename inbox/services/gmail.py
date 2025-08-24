import base64
import json
import os
from email.mime.text import MIMEText
from typing import List, Dict, Any

from django.utils import timezone
from django.db import transaction

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

from ..models import GmailToken

SCOPES = os.getenv("GOOGLE_OAUTH_SCOPES", "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.compose").split()
CLIENT_SECRETS_FILE = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "credentials.json")

def build_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

def _load_creds_from_db(user=None) -> Credentials | None:
    token = GmailToken.objects.filter(user=user).first()
    if not token:
        return None
    data = json.loads(token.token_json)
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    return creds

def _save_creds_to_db(creds: Credentials, user=None):
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
    }
    with transaction.atomic():
        obj, _ = GmailToken.objects.get_or_create(user=user)
        obj.token_json = json.dumps(payload)
        obj.save()

def get_gmail_service(user=None):
    """
    Returns an authenticated Gmail API service.
    Refreshes tokens automatically if expired.
    """
    creds = _load_creds_from_db(user=user)
    if not creds:
        return None  # caller should start OAuth flow

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_creds_to_db(creds, user=user)
        else:
            return None  # need to re-auth

    try:
        service = build("gmail", "v1", credentials=creds)
        return service
    except Exception:
        return None

def fetch_unread(service) -> List[Dict[str, Any]]:
    """
    Returns a lightweight list of unread emails (id, snippet, subject, from, date).
    """
    results = service.users().messages().list(
        userId="me", q="is:unread", maxResults=10
    ).execute()
    messages = results.get("messages", [])
    out = []
    for m in messages:
        full = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        payload = full.get("payload", {})
        headers = payload.get("headers", [])
        hmap = {h["name"].lower(): h["value"] for h in headers}
        out.append({
            "id": m["id"],
            "snippet": full.get("snippet", ""),
            "subject": hmap.get("subject", ""),
            "from": hmap.get("from", ""),
            "date": hmap.get("date", ""),
            "body_text": extract_plain_text(payload),
        })
    return out

def extract_plain_text(payload) -> str:
    """
    Tries to extract plain-text content from Gmail message payload.
    """
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                data = part["body"]["data"]
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            # recurse for nested multiparts
            if part.get("parts"):
                text = extract_plain_text(part)
                if text:
                    return text
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        data = payload["body"]["data"]
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    # fallback to empty string
    return ""

def create_gmail_draft(service, to_email: str, subject: str, body_text: str) -> str:
    """
    Creates a draft message and returns the draft ID.
    """
    msg = MIMEText(body_text)
    msg["to"] = to_email
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()
    return draft.get("id", "")
