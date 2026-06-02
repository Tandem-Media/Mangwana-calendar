"""
app.py — Mangwana Core Webhook

Receives inbound WhatsApp messages via Twilio, runs them through the
invitation parser, writes confirmed events to Google Calendar, and
replies to the user with a confirmation or a helpful error message.

Flow
----
  Twilio → POST /webhook → parse_invitation() → write_event() → TwiML reply
"""

import logging

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

from calendar_writer import write_event
from config import Config
from parser import ParseError, parse_invitation

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config + App
# ---------------------------------------------------------------------------
cfg = Config.load()
app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_confirmation(event: dict, calendar_url: str) -> str:
    """Build a friendly WhatsApp confirmation message."""
    lines = ["✅ *Got it! I've added this to your calendar:*", ""]
    lines.append(f"📌 *{event.get('title')}*")

    if event.get("date"):
        date_str = event["date"]
        if event.get("start_time"):
            lines.append(f"🗓  {date_str} at {event['start_time']}")
        else:
            lines.append(f"🗓  {date_str}")

    if event.get("location"):
        lines.append(f"📍 {event['location']}")

    if event.get("dress_code"):
        lines.append(f"👗 {event['dress_code']}")

    if event.get("rsvp_deadline"):
        lines.append(f"⏰ RSVP by {event['rsvp_deadline']}")

    if event.get("rsvp_contact"):
        lines.append(f"📞 RSVP to {event['rsvp_contact']}")

    lines += ["", f"🔗 {calendar_url}"]
    return "\n".join(lines)


def _format_not_invitation() -> str:
    return (
        "👋 Hi! I'm Mangwana, your calendar assistant.\n\n"
        "Forward me an event invitation and I'll add it to your calendar automatically.\n\n"
        "I'll pick up the date, time, venue, dress code, and RSVP details."
    )


def _format_error(detail: str) -> str:
    return (
        f"⚠️ I found the invitation but couldn't add it to your calendar.\n\n"
        f"Reason: {detail}\n\n"
        "You may need to add this one manually."
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "Mangwana"}, 200


@app.post("/webhook")
def webhook():
    """
    Twilio sends inbound WhatsApp messages as a form POST.
    We must return a TwiML response — even an empty one — within 15 seconds.
    """
    incoming_msg = request.form.get("Body", "").strip()
    sender       = request.form.get("From", "unknown")

    logger.info("Inbound message from %s: %r", sender, incoming_msg[:120])

    twiml = MessagingResponse()

    if not incoming_msg:
        twiml.message("I didn't receive any text. Please forward the invitation message.")
        return str(twiml), 200, {"Content-Type": "text/xml"}

    # -- Step 1: Parse -------------------------------------------------------
    try:
        event = parse_invitation(incoming_msg)
    except ParseError as exc:
        logger.info("Not an invitation: %s", exc)
        twiml.message(_format_not_invitation())
        return str(twiml), 200, {"Content-Type": "text/xml"}
    except Exception as exc:
        logger.exception("Unexpected parser error")
        twiml.message(_format_error(str(exc)))
        return str(twiml), 200, {"Content-Type": "text/xml"}

    # -- Step 2: Write to Calendar -------------------------------------------
    try:
        calendar_url = write_event(event, calendar_id=cfg.google_calendar_id)
    except ValueError as exc:
        # Missing required fields (title or date)
        logger.warning("Cannot write event — missing fields: %s", exc)
        twiml.message(_format_error(str(exc)))
        return str(twiml), 200, {"Content-Type": "text/xml"}
    except Exception as exc:
        logger.exception("Google Calendar write failed")
        twiml.message(_format_error("Could not reach Google Calendar. Please try again."))
        return str(twiml), 200, {"Content-Type": "text/xml"}

    # -- Step 3: Confirm -----------------------------------------------------
    reply = _format_confirmation(event, calendar_url)
    twiml.message(reply)
    logger.info("Event added and confirmation sent to %s", sender)

    return str(twiml), 200, {"Content-Type": "text/xml"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Starting Mangwana…")
    app.run(host=cfg.host, port=cfg.port, debug=False)
