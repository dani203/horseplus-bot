import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "horseplus/rootfs/app"))

from horseplus_api import APP_VERSION, BASE_URL, HorsePlusAPI


class HorsePlusAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.api = HorsePlusAPI("test@example.invalid", "test-password")
        self.api.user_data = {
            "id": "user-id",
            "personId": "person-id",
            "farm": {"id": "farm-id"},
        }
        self.api.session.post = Mock()
        self.identity = {
            "userId": "user-id", "personId": "person-id", "farmId": "farm-id",
        }
        self.start = "2026-10-18T11:30:00.000Z"
        self.end = "2026-10-18T13:00:00.000Z"

    def respond(self, body=None, status=200):
        response = requests.Response()
        response.status_code = status
        response._content = b"" if status == 204 else b"[]"
        response.json = Mock(return_value=body)
        self.api.session.post.return_value = response

    def assert_payload(self, endpoint, payload):
        self.api.session.post.assert_called_once_with(BASE_URL + endpoint, json=payload)

    def test_booking_matches_browser_contract_and_accepts_204(self):
        self.respond(status=204)
        result = self.api.book_facility(
            "facility-id", "horse-id", self.start, self.end,
            activity_id="activity-id", check_availability=False,
        )
        self.assertEqual(result, {"success": True})
        self.assert_payload("/api/facility-reservations/reserve-facility-command", {
            "facilityId": "facility-id",
            "facilityReservationActivityId": "activity-id",
            "horseId": "horse-id",
            "momentRange": {"start": self.start, "end": self.end},
            "comment": None,
            **self.identity,
        })

    def test_calendar_matches_browser_contract(self):
        self.respond([])
        self.assertEqual(self.api.get_facility_calendar("facility-id", self.start, self.end), [])
        self.assert_payload("/api/facilities/get-calendar-events-for-facility-query", {
            "facilityId": "facility-id",
            "momentRange": {"start": self.start, "end": self.end},
            **self.identity,
        })

    def test_appointments_use_moment_range_at_year_boundary(self):
        self.respond([])
        self.api.get_appointments_for_month(2026, 12)
        self.assert_payload("/api/dashboard/get-appointments-for-month-query", {
            "momentRange": {"start": "2026-12-01T00:00:00Z", "end": "2026-12-31T23:59:59Z"},
            **self.identity,
        })

    def test_activity_types_include_person_id(self):
        self.respond([])
        self.api.get_activity_types()
        self.assert_payload("/api/facility-reservations/get-preferred-intervals-query", self.identity)

    def test_availability_blocks_overlapping_browser_event(self):
        self.respond([{
            "from": "2026-10-18T11:00:00.000000+00:00",
            "to": "2026-10-18T12:00:00.000000+00:00",
            "type": "FACILITY_RESERVATION",
            "horse": {"name": "Test horse"},
        }])
        result = self.api.book_facility(
            "facility-id", "horse-id", self.start, self.end, activity_id="activity-id",
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Time slot not available")
        self.assertEqual(self.api.session.post.call_count, 1)

    def test_app_version_matches_browser(self):
        self.assertEqual(APP_VERSION, "bea321f2f9eb8ad8f7f32d8696c967584987fbf7")
        self.assertEqual(self.api.session.headers["x-app-version"], APP_VERSION)


if __name__ == "__main__":
    unittest.main()