import base64
import datetime as dt
import json
import os
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def _service_account_info_from_env():
    """
    Vercel / CI: set GOOGLE_CREDENTIALS_JSON to the full JSON string, or
    GOOGLE_CREDENTIALS_B64 to base64-encoded JSON (avoids multiline env issues).
    """
    b64 = os.getenv("GOOGLE_CREDENTIALS_B64", "").strip()
    if b64:
        raw = base64.b64decode(b64).decode("utf-8")
        return json.loads(raw)
    raw_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if raw_json:
        return json.loads(raw_json)
    return None


def _authenticate_google_docs():
    info = _service_account_info_from_env()
    if info is not None:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    else:
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
        )
    return build("docs", "v1", credentials=creds)


def _parse_due_date(raw_due_date: str):
    raw = raw_due_date.strip()
    if not raw:
        return None

    lowered = raw.lower()
    if lowered in {"unknown", "n/a", "none", "date unknown"}:
        return None

    formats = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d",
        "%B %d",
    )
    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(raw, fmt).date()
            if fmt in ("%b %d", "%B %d"):
                parsed = parsed.replace(year=dt.date.today().year)
            return parsed
        except ValueError:
            continue

    return None


def get_homework_entries(doc_id: str) -> list:
    docs_service = _authenticate_google_docs()
    doc = docs_service.documents().get(documentId=doc_id).execute()

    paragraphs = []
    for block in doc.get("body", {}).get("content", []):
        paragraph = block.get("paragraph")
        if not paragraph:
            continue

        text_parts = []
        has_strikethrough = False
        for element in paragraph.get("elements", []):
            text_run = element.get("textRun")
            if not text_run:
                continue
            text_parts.append(text_run.get("content", ""))
            if text_run.get("textStyle", {}).get("strikethrough", False):
                has_strikethrough = True

        text = "".join(text_parts).strip()
        if text:
            paragraphs.append({"text": text, "strikethrough": has_strikethrough})

    entries = []
    current_due_date = None
    due_header_regex = re.compile(r"^Due\s+(.+)$", re.IGNORECASE)

    for paragraph in paragraphs:
        raw_line = paragraph["text"]
        header_match = due_header_regex.match(raw_line)
        if header_match:
            current_due_date = _parse_due_date(header_match.group(1))
            continue

        line = re.sub(r"^[\u2022\-]\s*", "", raw_line).strip()
        completed_by_checkbox = bool(re.match(r"^\[x\]\s*", line, flags=re.IGNORECASE))
        line = re.sub(r"^\[[x ]\]\s*", "", line, flags=re.IGNORECASE)

        if "—" in line:
            subject, description = line.split("—", 1)
        elif " - " in line:
            subject, description = line.split(" - ", 1)
        else:
            continue

        subject = subject.strip()
        description = description.strip()
        if not subject or not description:
            continue

        entries.append(
            {
                "due_date": current_due_date.isoformat() if current_due_date else "",
                "subject": subject,
                "description": description,
                "completed": paragraph["strikethrough"] or completed_by_checkbox,
            }
        )

    return entries
