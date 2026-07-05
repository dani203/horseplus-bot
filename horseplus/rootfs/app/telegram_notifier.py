"""
Telegram notification helper.
Sends plain-text or HTML messages to a configured chat.
"""
import logging
import requests

_LOGGER = logging.getLogger(__name__)


def send(bot_token: str, chat_id: str, message: str, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message. Returns True on success."""
    if not bot_token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": parse_mode},
            timeout=10,
        )
        if resp.status_code != 200:
            _LOGGER.warning("Telegram send failed: %s", resp.text[:200])
            return False
        return True
    except Exception as exc:
        _LOGGER.error("Telegram error: %s", exc)
        return False
