"""
tests/test_parser.py — Unit tests for the Mangwana invitation parser.

All Anthropic API calls are mocked — no real API key needed in CI.
Tests cover:
  - Successful extraction of a social invitation
  - Successful extraction of a legal/court notice
  - Non-invitation messages are rejected cleanly
  - Missing API key raises EnvironmentError
  - Malformed tool response raises ParseError
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from parser import ParseError, parse_invitation


# ---------------------------------------------------------------------------
# Helpers — build mock Anthropic responses
# ---------------------------------------------------------------------------

def _mock_tool_response(data: dict):
    """
    Build a minimal mock that looks like an Anthropic tool-use response.
    response.content[0].input → data
    """
    content_block = MagicMock()
    content_block.input = data

    response = MagicMock()
    response.content = [content_block]
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    """Ensure ANTHROPIC_API_KEY is always set for tests that don't test its absence."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseInvitation:

    @patch("parser.anthropic.Anthropic")
    def test_social_invitation_parsed_correctly(self, mock_anthropic_cls):
        """A typical social invitation returns all expected fields."""
        mock_event = {
            "is_invitation": True,
            "title": "Mazwi Wedding Reception",
            "date": "2026-06-21",
            "start_time": "18:30",
            "end_time": None,
            "location": "Borrowdale Brooke Golf Club",
            "rsvp_deadline": None,
            "rsvp_contact": None,
            "dress_code": "Smart Casual",
            "notes": None,
        }
        mock_anthropic_cls.return_value.messages.create.return_value = (
            _mock_tool_response(mock_event)
        )

        result = parse_invitation(
            "Please join us for the Mazwi wedding reception, "
            "Saturday 21 June at Borrowdale Brooke Golf Club, 18:30. Smart casual."
        )

        assert result["title"] == "Mazwi Wedding Reception"
        assert result["date"] == "2026-06-21"
        assert result["start_time"] == "18:30"
        assert result["location"] == "Borrowdale Brooke Golf Club"
        assert result["dress_code"] == "Smart Casual"

    @patch("parser.anthropic.Anthropic")
    def test_legal_notice_parsed_correctly(self, mock_anthropic_cls):
        """A court hearing notice is treated as a high-priority invitation."""
        mock_event = {
            "is_invitation": True,
            "title": "High Court Hearing — Moyo v Ncube",
            "date": "2026-06-10",
            "start_time": "09:00",
            "end_time": None,
            "location": "High Court, Harare",
            "rsvp_deadline": None,
            "rsvp_contact": None,
            "dress_code": None,
            "notes": "Bring all pleadings filed to date.",
        }
        mock_anthropic_cls.return_value.messages.create.return_value = (
            _mock_tool_response(mock_event)
        )

        result = parse_invitation(
            "Hearing in Moyo v Ncube set down for 10 June 2026 at 09:00 "
            "before Justice Dube, High Court Harare. Please bring all pleadings."
        )

        assert result["is_invitation"] is True
        assert result["date"] == "2026-06-10"
        assert result["start_time"] == "09:00"
        assert "High Court" in result["location"]

    @patch("parser.anthropic.Anthropic")
    def test_non_invitation_raises_parse_error(self, mock_anthropic_cls):
        """General chat messages are rejected with ParseError."""
        mock_anthropic_cls.return_value.messages.create.return_value = (
            _mock_tool_response({
                "is_invitation": False,
                "title": None,
                "date": None,
                "start_time": None,
                "end_time": None,
            })
        )

        with pytest.raises(ParseError):
            parse_invitation("Hie, just checking if you received the documents I sent.")

    @patch("parser.anthropic.Anthropic")
    def test_rsvp_fields_extracted(self, mock_anthropic_cls):
        """RSVP deadline and contact are captured when present."""
        mock_event = {
            "is_invitation": True,
            "title": "Chipo's Baby Shower",
            "date": "2026-07-05",
            "start_time": "14:00",
            "end_time": "17:00",
            "location": "13 Quinnington Road, Borrowdale",
            "rsvp_deadline": "2026-06-28",
            "rsvp_contact": "Tendai — 0771234567",
            "dress_code": "Pink or Blue",
            "notes": None,
        }
        mock_anthropic_cls.return_value.messages.create.return_value = (
            _mock_tool_response(mock_event)
        )

        result = parse_invitation(
            "You're invited to Chipo's baby shower! 5 July, 2pm–5pm at "
            "13 Quinnington Road Borrowdale. Dress: pink or blue. "
            "RSVP to Tendai 0771234567 by 28 June."
        )

        assert result["rsvp_deadline"] == "2026-06-28"
        assert result["rsvp_contact"] == "Tendai — 0771234567"
        assert result["end_time"] == "17:00"

    def test_missing_api_key_raises_environment_error(self, monkeypatch):
        """EnvironmentError is raised immediately if no API key is available."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            parse_invitation("Some message", api_key=None)

    @patch("parser.anthropic.Anthropic")
    def test_malformed_tool_response_raises_parse_error(self, mock_anthropic_cls):
        """If the API returns an unexpected structure, ParseError is raised cleanly."""
        bad_response = MagicMock()
        bad_response.content = []   # empty — no tool call block

        mock_anthropic_cls.return_value.messages.create.return_value = bad_response

        with pytest.raises(ParseError):
            parse_invitation("Join us for the annual dinner on Friday.")
