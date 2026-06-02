"""
calendar_writer.py — Google Calendar Integration

Takes a parsed event dict (from parser.py) and creates a Google Calendar
event, returning the event URL.

Prerequisites
-------------
1.  A Google Cloud project with the Calendar API enabled.
2.  A service account JSON key file, path set via GOOGLE_SERVICE_ACCOUNT_FILE,
    OR a JSON string in GOOGLE_SERVICE_ACCOUNT_JSON.
3.  The calendar (GOOGLE_CALENDAR_ID) shared with the service account email.

Usage
-----
    from calendar_writer import write_event
    url = write_event(parsed_event_dict)
"""

import json
import logging
import os
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES         = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE       = "Africa/Harare"
DEFAULT_REMINDER_MINUTES = [1440, 60]  # 24 h and 1 h before


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _get_credentials():
    """Load service account credentials from env (file path or JSON string)."""
    json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if json_str:
        info = json.loads(json_str)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    json_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if json_file:
        return service_account.Credentials.from_service_account_file(json_file, scopes=SCOPES)

    raise EnvironmentError(
        "Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE "
        "to authenticate with Google Calendar."
    )


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def write_event(event_data: dict, calendar_id: Optional[str] = None) -> str:
    """
    Create a Google Calendar event from parsed invitation data.

    Parameters
    ----------
    event_data  : Dict returned by parser.parse_invitation().
    calendar_id : Override for GOOGLE_CALENDAR_ID env var.

    Returns
    -------
    str — The HTML link to the created calendar event.

    Raises
    ------
    HttpError   — on Google API failures.
    ValueError  — if required fields (title, date) are missing.
    """
    title = event_data.get("title")
    date  = event_data.get("date")

    if not title:
        raise ValueError("Event title is required.")
    if not date:
        raise ValueError("Event date is required.")

    cal_id = calendar_id or os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    # -- Build the event body ------------------------------------------------
    start_time = event_data.get("start_time")
    end_time   = event_data.get("end_time")

    if start_time:
        # Timed event
        start = {"dateTime": f"{date}T{start_time}:00", "timeZone": TIMEZONE}
        if end_time:
            end = {"dateTime": f"{date}T{end_time}:00", "timeZone": TIMEZONE}
        else:
            # Default: assume 2-hour event if no end time given
            h, m = map(int, start_time.split(":"))
            end_h = (h + 2) % 24
            end = {"dateTime": f"{date}T{end_h:02d}:{m:02d}:00", "timeZone": TIMEZONE}
    else:
        # All-day event
        start = {"date": date}
        end   = {"date": date}

    # Build description from optional fields
    description_parts = []
    if event_data.get("rsvp_deadline"):
        description_parts.append(f"RSVP by: {event_data['rsvp_deadline']}")
    if event_data.get("rsvp_contact"):
        description_parts.append(f"RSVP to: {event_data['rsvp_contact']}")
    if event_data.get("dress_code"):
        description_parts.append(f"Dress code: {event_data['dress_code']}")
    if event_data.get("notes"):
        description_parts.append(f"\n{event_data['notes']}")
    description_parts.append("\n📅 Added by Mangwana")

    body = {
        "summary":     title,
        "location":    event_data.get("location") or "",
        "description": "\n".join(description_parts),
        "start":       start,
        "end":         end,
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": m}
                for m in DEFAULT_REMINDER_MINUTES
            ],
        },
    }

    # -- Call the API --------------------------------------------------------
    try:
        creds   = _get_credentials()
        service = build("googleapiclient", "v1", credentials=creds)
        # Note: correct service name is "calendar"
        service = build("calendar", "v3", credentials=creds)
        created = service.events().insert(calendarId=cal_id, body=body).execute()
        url = created.get("htmlLink", "")
        logger.info("Calendar event created: %s → %s", title, url)
        return url

    except HttpError as exc:
        logger.error("Google Calendar API error: %s", exc)
        raise
