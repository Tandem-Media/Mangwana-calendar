"""
parser.py — Invitation Parser

Sends a raw WhatsApp message text to Claude and extracts structured
event data from it. Returns a clean dict or raises ParseError if the
message doesn't look like an invitation at all.
"""

import json
import logging
import os
import zoneinfo
from datetime import datetime
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ParseError(ValueError):
    """Raised when a message cannot be parsed as an event invitation."""


# ---------------------------------------------------------------------------
# Prompt & Tool Definitions
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are Mangwana, a private calendar assistant for Nyaradzo Maphosa (Nyari), \
a senior legal practitioner in Harare, Zimbabwe.
Your sole job is to seamlessly process text invitations, meeting notices, court dates, and \
social events forwarded from her WhatsApp groups or clients.

The local timezone is Africa/Harare (CAT, UTC+2).
Relative references (e.g., "tomorrow", "this Friday", "next week Monday") must be resolved \
strictly relative to the provided current anchor date.
"""

# Tool schema — forces Claude to return a typed dict rather than free-form text.
# This eliminates all JSON parsing fragility.
_CALENDAR_TOOL_SCHEMA = {
    "name": "extract_calendar_metadata",
    "description": "Output structured JSON properties extracted from event notices or schedule texts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_invitation": {
                "type": "boolean",
                "description": "False if the message is clearly general chatter, a legal advice query, or chat banter without explicit scheduling intent."
            },
            "title": {
                "type": "string",
                "description": "Short, clear event name — clean up informal titles gracefully (e.g., 'Chipo bday tmrw' -> 'Chipo\\'s Birthday')"
            },
            "date": {
                "type": "string",
                "description": "YYYY-MM-DD format, null if not mentioned"
            },
            "start_time": {
                "type": "string",
                "description": "HH:MM 24-hour format, null if not mentioned"
            },
            "end_time": {
                "type": "string",
                "description": "HH:MM 24-hour format, null if not mentioned"
            },
            "location": {
                "type": "string",
                "description": "Venue name or address, null if not mentioned"
            },
            "rsvp_deadline": {
                "type": "string",
                "description": "YYYY-MM-DD format, null if not mentioned"
            },
            "rsvp_contact": {
                "type": "string",
                "description": "Name or number to RSVP to, null if not mentioned"
            },
            "dress_code": {
                "type": "string",
                "description": "Null if not mentioned"
            },
            "notes": {
                "type": "string",
                "description": "Any other important details or context, null if none"
            }
        },
        "required": ["is_invitation", "title", "date", "start_time", "end_time"]
    }
}


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def parse_invitation(message: str, api_key: Optional[str] = None) -> dict:
    """
    Parse a WhatsApp message and return structured event data.

    Parameters
    ----------
    message : The raw text of the WhatsApp message.
    api_key : Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns
    -------
    dict matching the schema above, e.g.:
        parse_invitation("Please join us for the Mazwi wedding reception,
            Saturday 21 June at Borrowdale Brooke Golf Club, 18:30. Smart casual.")
        # → {"title": "Mazwi Wedding Reception", "date": "2025-06-21", "start_time": "18:30", ...}

    Raises
    ------
    ParseError  — if the message is not an invitation or parsing fails.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=key)

    # Anchor today's date to Harare's clock, not the server's system clock
    harare_tz = zoneinfo.ZoneInfo("Africa/Harare")
    today_local = datetime.now(harare_tz).date().isoformat()

    system_instruction = f"{_SYSTEM_PROMPT}\nToday's Anchor Date Context: {today_local}"
    user_content = (
        f"Extract the event details from this WhatsApp message:\n\n"
        f"---\n{message.strip()}\n---"
    )

    logger.info("Sending message to Claude for parsing (%d chars)", len(message))

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=system_instruction,
        messages=[{"role": "user", "content": user_content}],
        tools=[_CALENDAR_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "extract_calendar_metadata"},
    )

    # Tool use response: input is always a clean typed dict — no JSON parsing needed
    try:
        data = response.content[0].input
    except (IndexError, AttributeError) as exc:
        raise ParseError("Claude did not return a tool call response.") from exc

    if not data.get("is_invitation"):
        raise ParseError("Message does not appear to be an event invitation.")

    logger.info("Parsed event: %s on %s", data.get("title"), data.get("date"))
    return data