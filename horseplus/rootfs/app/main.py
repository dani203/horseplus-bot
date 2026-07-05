"""
Main entry point for the HorsePlus Booking add-on.
Reads config from /data/options.json, sets up API + BookingManager, starts Flask.
"""
import json
import logging
import os
import sys
import threading
from pathlib import Path

from flask import Flask

# ── Logging — stdout goes to the HA "Log" tab ──────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
_LOGGER = logging.getLogger("horseplus")

# ── Load config ─────────────────────────────────────────────────────────────────
OPTIONS_PATH = Path("/data/options.json")

def load_config() -> dict:
    try:
        with OPTIONS_PATH.open() as f:
            cfg = json.load(f)
        _LOGGER.info("Configuration loaded")
        return cfg
    except FileNotFoundError:
        _LOGGER.error("options.json not found — using empty config")
        return {}
    except Exception as exc:
        _LOGGER.error("Failed to load options.json: %s", exc)
        return {}


# ── Main ─────────────────────────────────────────────────────────────────────────
def main():
    config = load_config()

    email = config.get("email", "").strip()
    password = config.get("password", "").strip()

    if not email or not password:
        _LOGGER.error(
            "No credentials configured! Open the add-on's Configuration tab and set "
            "your HorsePlus email and password, then restart the add-on."
        )

    # ── Set up API ────────────────────────────────────────────────────────────
    from horseplus_api import HorsePlusAPI

    api = HorsePlusAPI(email, password)
    if email and password:
        try:
            api.login()
        except Exception as exc:
            _LOGGER.error("Initial login failed: %s — will retry on first request", exc)

    def api_factory() -> HorsePlusAPI:
        """Return the shared API instance, ensuring it's logged in."""
        if not api.user_data:
            try:
                api.login()
            except Exception as exc:
                _LOGGER.error("Login failed in api_factory: %s", exc)
                return None
        return api

    # ── Set up BookingManager ─────────────────────────────────────────────────
    from booking_manager import BookingManager

    manager = BookingManager(api_factory=api_factory, config=config)
    manager.start()

    # ── Set up Flask ──────────────────────────────────────────────────────────
    import web_app
    web_app.init(api=api, manager=manager, config=config)

    port = int(os.environ.get("PORT", 8099))
    _LOGGER.info("Starting web UI on port %d", port)

    # Run Flask (blocking)
    web_app.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
