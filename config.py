"""
config.py — Centralised configuration loader for WhatsApp Invitation Bot.

Priority order (highest → lowest):
  1. Environment variables  (Railway / production)
  2. config.json            (local development fallback)

Any required key missing from both sources will raise a fatal ConfigError
at startup so the app fails fast with a clear message rather than crashing
mid-request.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigError(RuntimeError):
    """Raised when a required configuration value cannot be resolved."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CONFIG_FILE = Path(__file__).parent / "config.json"

_SOURCES: dict[str, str] = {}   # key → "env" | "file" | "default"
_VALUES:  dict[str, Any] = {}   # resolved flat key → value


def _load_file() -> dict:
    """Load config.json if it exists; return empty dict otherwise."""
    if _CONFIG_FILE.exists():
        try:
            with _CONFIG_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            logger.debug("config.json found at %s", _CONFIG_FILE)
            return data
        except json.JSONDecodeError as exc:
            logger.warning("config.json is malformed and will be ignored: %s", exc)
    else:
        logger.debug("config.json not present — relying on environment variables.")
    return {}


def _resolve(
    env_key: str,
    file_data: dict,
    file_key: Optional[str] = None,
    default: Any = None,
    required: bool = False,
) -> Any:
    """
    Resolve a single config value using the priority chain.

    Parameters
    ----------
    env_key   : Name of the environment variable to check first.
    file_data : The dict loaded from config.json.
    file_key  : Dot-separated key path in file_data (defaults to env_key).
    default   : Fallback value if neither env nor file has it.
    required  : If True and nothing resolves, raise ConfigError.
    """
    # 1. Environment variable
    env_val = os.environ.get(env_key)
    if env_val is not None:
        _SOURCES[env_key] = "env"
        return env_val

    # 2. config.json (supports dot-notation: "section.key")
    path = (file_key or env_key).split(".")
    node = file_data
    for segment in path:
        if isinstance(node, dict) and segment in node:
            node = node[segment]
        else:
            node = None
            break

    if node is not None:
        _SOURCES[env_key] = "file"
        return node

    # 3. Hard-coded default
    if default is not None:
        _SOURCES[env_key] = "default"
        return default

    if required:
        raise ConfigError(
            f"\n\n  ✖  Required config value is missing: '{env_key}'\n"
            f"     Set it as an environment variable (Railway → Variables tab)\n"
            f"     or add it to config.json for local development.\n"
        )

    _SOURCES[env_key] = "missing"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class Config:
    """
    Singleton-style config object.  Import and call ``load()`` once at
    startup; then access values as attributes everywhere else.

    Usage
    -----
    ::

        from config import Config
        cfg = Config.load()
        print(cfg.wasender_api_key)
    """

    _instance: Optional["Config"] = None

    # -- resolved values -------------------------------------------------
    openai_api_key:    str
    wasender_api_key:  str
    phone_number_id:   str
    google_calendar_id: str
    port:              int
    host:              str

    def __init__(self, file_data: dict) -> None:
        self.openai_api_key = _resolve(
            "OPENAI_API_KEY",
            file_data,
            file_key="openai.api_key",
            required=False,
        )
        self.wasender_api_key = _resolve(
            "WASENDER_API_KEY",
            file_data,
            file_key="wasender.api_key",
            required=True,           # ← fatal if missing
        )
        self.phone_number_id = _resolve(
            "PHONE_NUMBER_ID",
            file_data,
            file_key="wasender.phone_number_id",
            required=True,           # ← fatal if missing
        )
        self.google_calendar_id = _resolve(
            "GOOGLE_CALENDAR_ID",
            file_data,
            file_key="google.calendar_id",
            required=False,
        )
        port_raw = _resolve(
            "PORT",
            file_data,
            file_key="server.port",
            default="5000",
        )
        try:
            self.port = int(port_raw)
        except (TypeError, ValueError):
            logger.warning("PORT value '%s' is not an integer — defaulting to 5000.", port_raw)
            self.port = 5000

        # Railway requires 0.0.0.0; never change this.
        self.host = "0.0.0.0"

    # -- factory ---------------------------------------------------------

    @classmethod
    def load(cls) -> "Config":
        """Load configuration (idempotent — returns cached instance on repeat calls)."""
        if cls._instance is not None:
            return cls._instance

        file_data = _load_file()
        try:
            instance = cls(file_data)
        except ConfigError as exc:
            # Print directly to stderr so it's visible even if logging isn't set up yet.
            print(str(exc), file=sys.stderr)
            sys.exit(1)

        cls._instance = instance
        instance._log_summary()
        return instance

    # -- diagnostics -----------------------------------------------------

    def _log_summary(self) -> None:
        """Emit a startup summary showing where each value came from."""
        separator = "─" * 60
        lines = [
            "",
            separator,
            "  WhatsApp Bot — Configuration Summary",
            separator,
        ]
        key_map = {
            "OPENAI_API_KEY":     ("openai_api_key",     True),
            "WASENDER_API_KEY":   ("wasender_api_key",   True),
            "PHONE_NUMBER_ID":    ("phone_number_id",    False),
            "GOOGLE_CALENDAR_ID": ("google_calendar_id", False),
            "PORT":               ("port",               False),
        }
        source_label = {
            "env":     "✔  env var",
            "file":    "✔  config.json",
            "default": "○  default",
            "missing": "–  not set",
        }
        for env_key, (attr, is_secret) in key_map.items():
            raw = getattr(self, attr, None)
            source = _SOURCES.get(env_key, "missing")
            label  = source_label.get(source, source)
            if raw and is_secret:
                display = f"{str(raw)[:6]}{'*' * max(0, len(str(raw)) - 6)}"
            else:
                display = str(raw) if raw is not None else "(none)"
            lines.append(f"  {env_key:<22}  {label:<20}  {display}")

        lines += [
            separator,
            f"  Binding on  {self.host}:{self.port}",
            separator,
            "",
        ]
        logger.info("\n".join(lines))

    # -- convenience -----------------------------------------------------

    def as_dict(self) -> dict:
        """Return a non-sensitive summary dict (safe to log / inspect)."""
        return {
            "host":               self.host,
            "port":               self.port,
            "phone_number_id":    self.phone_number_id,
            "google_calendar_id": self.google_calendar_id,
            "openai_api_key":     bool(self.openai_api_key),
            "wasender_api_key":   bool(self.wasender_api_key),
        }
