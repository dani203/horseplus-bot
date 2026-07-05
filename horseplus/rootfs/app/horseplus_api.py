"""
HorsePlus API Client
Adapted from the original horseplus_api.py — no file I/O, credentials passed as parameters.
"""
import logging
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://my.horseplus.app"
APP_VERSION = "7adf7cb2146d7a32c984158240a8256837154f49"


class HorsePlusAPI:
    """Thread-safe HorsePlus API client with automatic session renewal."""

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36",
            "Accept": "application/json;charset=utf-8",
            "Content-Type": "application/json;charset=UTF-8",
            "x-app-version": APP_VERSION,
            "Origin": BASE_URL,
        })
        self.user_data: Optional[Dict[str, Any]] = None
        self._reauth_in_progress = False

    # ── Authentication ──────────────────────────────────────────────────────────

    def login(self) -> Dict[str, Any]:
        """Authenticate and return full user data."""
        endpoint = f"{BASE_URL}/api/unauthorized/application/authentication/login"
        payload = {"emailAddress": self.email, "password": self.password}

        old_headers = dict(self.session.headers)
        self.session = requests.Session()
        self.session.headers.update(old_headers)

        _LOGGER.info("Logging in as %s ...", self.email)
        response = self.session.post(endpoint, json=payload)
        response.raise_for_status()

        data = response.json()
        self.user_data = data.get("user", {})

        if "Authorization" in response.headers:
            self.session.headers["Authorization"] = response.headers["Authorization"]

        _LOGGER.info(
            "Login successful — %s %s @ %s",
            self.user_data.get("name", {}).get("firstName"),
            self.user_data.get("name", {}).get("lastName"),
            self.user_data.get("farm", {}).get("name"),
        )
        return data

    def ensure_logged_in(self) -> bool:
        """Login if not already authenticated. Returns True on success."""
        if self.user_data:
            return True
        try:
            self.login()
            return True
        except Exception as exc:
            _LOGGER.error("Login failed: %s", exc)
            return False

    def _reauth(self, retry_func, *args, **kwargs):
        """Re-authenticate after session expiry and retry the original call."""
        if self._reauth_in_progress:
            raise RuntimeError("Re-authentication loop detected.")
        _LOGGER.warning("Session expired (401) — re-authenticating...")
        try:
            self._reauth_in_progress = True
            self.login()
            result = retry_func(*args, **kwargs)
            return result
        finally:
            self._reauth_in_progress = False

    # ── Generic request helpers ─────────────────────────────────────────────────

    def _get(self, endpoint: str, **kwargs) -> Any:
        url = f"{BASE_URL}{endpoint}"
        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            if exc.response.status_code == 401 and not self._reauth_in_progress:
                return self._reauth(self._get, endpoint, **kwargs)
            raise

    def _post(self, endpoint: str, data: Any = None, **kwargs) -> Any:
        url = f"{BASE_URL}{endpoint}"
        try:
            response = self.session.post(url, json=data, **kwargs)
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {"success": True}
            return response.json()
        except requests.HTTPError as exc:
            if exc.response.status_code == 401 and not self._reauth_in_progress:
                return self._reauth(self._post, endpoint, data, **kwargs)
            raise

    # ── Data fetchers ───────────────────────────────────────────────────────────

    def get_facilities(self) -> List[Dict]:
        return self.user_data.get("farm", {}).get("facilities", [])

    def get_horses(self) -> List[Dict]:
        data = self._post("/api/horse-management/get-available-horses-query", {
            "userId": self.user_data["id"],
            "farmId": self.user_data["farm"]["id"],
        })
        return data.get("own", []) + data.get("shared", [])

    def get_activity_types(self) -> List[Dict]:
        return self._post("/api/facility-reservations/get-preferred-intervals-query", {
            "userId": self.user_data["id"],
            "farmId": self.user_data["farm"]["id"],
        })

    def get_facility_activities(self, facility_id: str) -> List[Dict]:
        """Return activities observed in recent bookings for this facility."""
        now = datetime.utcnow()
        events = self.get_facility_calendar(
            facility_id,
            (now - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00.000Z"),
            (now + timedelta(days=60)).strftime("%Y-%m-%dT23:59:59.000Z"),
        )
        seen: Dict[str, Dict] = {}
        for event in events:
            if event.get("type") == "FACILITY_RESERVATION":
                act = event.get("facilityReservationActivity")
                if act:
                    act_id = act.get("facilityReservationActivityId")
                    if act_id and act_id not in seen:
                        seen[act_id] = act
        return list(seen.values())

    def get_facility_calendar(self, facility_id: str, date_from: str, date_to: str) -> List[Dict]:
        return self._post("/api/facilities/get-calendar-events-for-facility-query", {
            "facilityId": facility_id,
            "rangeFrom": date_from,
            "rangeTo": date_to,
            "userId": self.user_data["id"],
            "farmId": self.user_data["farm"]["id"],
        })

    def get_appointments_for_month(self, year: int, month: int) -> List[Dict]:
        start = datetime(year, month, 1)
        end = (datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)) - timedelta(seconds=1)
        return self._post("/api/dashboard/get-appointments-for-month-query", {
            "timeFrame": {
                "momentFrom": start.isoformat() + "Z",
                "momentTo": end.isoformat() + "Z",
            },
            "userId": self.user_data["id"],
            "farmId": self.user_data["farm"]["id"],
        })

    def check_availability(self, facility_id: str, start_iso: str, end_iso: str) -> Dict:
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        date_from = start_dt.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT00:00:00.000Z")
        date_to = end_dt.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT23:59:59.000Z")
        events = self.get_facility_calendar(facility_id, date_from, date_to)

        conflicts = []
        for event in events:
            ef = event.get("from", "").replace(".000000", ".000")
            et = event.get("to", "").replace(".000000", ".000")
            if not ef or not et:
                continue
            ef_dt = datetime.fromisoformat(ef)
            et_dt = datetime.fromisoformat(et)
            if not (end_dt <= ef_dt or start_dt >= et_dt):
                details = event
                ctype = event.get("type", "")
                if ctype == "FACILITY_BLOCKER":
                    desc = f"Blocked: {details.get('comment', 'Maintenance')}"
                elif ctype == "FACILITY_RESERVATION":
                    horse = details.get("horse", {}).get("name", "Unknown")
                    desc = f"Already booked by '{horse}'"
                else:
                    desc = ctype
                conflicts.append(desc)
        return {"available": not conflicts, "conflicts": conflicts}

    def book_facility(
        self,
        facility_id: str,
        horse_id: str,
        start_iso: str,
        end_iso: str,
        activity_id: Optional[str] = None,
        comment: Optional[str] = None,
        check_availability: bool = True,
    ) -> Dict:
        if check_availability:
            avail = self.check_availability(facility_id, start_iso, end_iso)
            if not avail["available"]:
                return {"success": False, "error": "Time slot not available", "conflicts": avail["conflicts"]}

        if not activity_id:
            activities = self.get_activity_types()
            if not activities:
                activities = self.get_facility_activities(facility_id)
            if not activities:
                return {"success": False, "error": "No activity types found"}
            # Prefer the standard paddock activity
            PREFERRED = "0afb5cd8-ad8b-49a7-b6ad-139eced6e006"
            activity_id = next(
                (a["facilityReservationActivityId"] for a in activities if a.get("facilityReservationActivityId") == PREFERRED),
                activities[0]["facilityReservationActivityId"],
            )

        payload = {
            "facilityId": facility_id,
            "facilityReservationActivityId": activity_id,
            "horseId": horse_id,
            "from": start_iso,
            "to": end_iso,
            "comment": comment,
            "userId": self.user_data["id"],
            "farmId": self.user_data["farm"]["id"],
        }
        try:
            result = self._post("/api/facility-reservations/reserve-facility-command", payload)
            _LOGGER.info("Booking successful: %s → %s", start_iso, end_iso)
            return {"success": True, **result}
        except requests.HTTPError as exc:
            try:
                detail = exc.response.json()
            except Exception:
                detail = exc.response.text[:300]
            _LOGGER.error("Booking failed (%s): %s", exc.response.status_code, detail)
            return {"success": False, "error": str(exc), "detail": detail}
        except Exception as exc:
            _LOGGER.error("Booking error: %s", exc)
            return {"success": False, "error": str(exc)}

    def cancel_reservation(self, reservation_id: str) -> Dict:
        payload = {
            "facilityReservationId": reservation_id,
            "userId": self.user_data["id"],
            "farmId": self.user_data["farm"]["id"],
        }
        for endpoint in [
            "/api/facility-reservation/cancel-facility-reservation-command",
            "/api/facility-reservations/cancel",
        ]:
            try:
                return self._post(endpoint, payload)
            except Exception:
                continue
        return {"success": False, "error": "Could not find cancellation endpoint"}

    def get_user_info(self) -> Dict:
        return self.user_data or {}

    def get_farm_info(self) -> Dict:
        return (self.user_data or {}).get("farm", {})
