"""
Booking manager — schedule storage and APScheduler-based execution.

Schedules are persisted in /data/schedules.json.
Each schedule defines WHEN to run the booking script and WHAT to book.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import telegram_notifier as telegram

_LOGGER = logging.getLogger(__name__)

SCHEDULES_PATH = Path("/data/schedules.json")
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class BookingManager:
    """Manages recurring auto-booking schedules using APScheduler."""

    def __init__(self, api_factory, config: dict):
        """
        api_factory: callable returning a logged-in HorsePlusAPI instance
        config: dict from /data/options.json
        """
        self._api_factory = api_factory
        self._config = config
        self._schedules: List[Dict] = []
        self._lock = threading.Lock()
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._load()

    # ── Lifecycle ───────────────────────────────────────────────────────────────

    def start(self):
        self._scheduler.start()
        self._reschedule_all()
        _LOGGER.info("Booking manager started with %d schedule(s)", len(self._schedules))

    def stop(self):
        self._scheduler.shutdown(wait=False)

    def update_config(self, config: dict):
        self._config = config

    # ── CRUD ────────────────────────────────────────────────────────────────────

    def list_schedules(self) -> List[Dict]:
        with self._lock:
            return list(self._schedules)

    def get_schedule(self, schedule_id: str) -> Optional[Dict]:
        with self._lock:
            return next((s for s in self._schedules if s["id"] == schedule_id), None)

    def create_schedule(self, data: dict) -> Dict:
        schedule = {
            "id": str(uuid.uuid4()),
            "name": data.get("name", "Unnamed"),
            "enabled": data.get("enabled", True),
            # Trigger: when to run the booking script
            "trigger_weekday": int(data["trigger_weekday"]),   # 0=Mon … 6=Sun
            "trigger_time": data["trigger_time"],              # "HH:MM" local time
            # Booking target
            "booking_date_offset": int(data.get("booking_date_offset", 0)),  # days from trigger
            "booking_time": data["booking_time"],              # "HH:MM" local time
            "duration_hours": float(data["duration_hours"]),
            # IDs
            "facility_id": data["facility_id"],
            "facility_name": data.get("facility_name", ""),
            "horse_id": data["horse_id"],
            "horse_name": data.get("horse_name", ""),
            "activity_id": data.get("activity_id"),
            # Retry
            "retry_count": int(data.get("retry_count", self._config.get("retry_count", 3))),
            "retry_delay_seconds": int(data.get("retry_delay_seconds", self._config.get("retry_delay_seconds", 2))),
            # State
            "created_at": datetime.utcnow().isoformat(),
            "last_run": None,
            "last_status": None,
            "last_message": None,
            "next_run": None,
        }
        with self._lock:
            self._schedules.append(schedule)
            self._save()
        self._register_schedule(schedule)
        _LOGGER.info("Schedule created: %s (%s)", schedule["name"], schedule["id"])
        return schedule

    def update_schedule(self, schedule_id: str, data: dict) -> Optional[Dict]:
        with self._lock:
            schedule = next((s for s in self._schedules if s["id"] == schedule_id), None)
            if not schedule:
                return None
            updatable = [
                "name", "enabled", "trigger_weekday", "trigger_time",
                "booking_date_offset", "booking_time", "duration_hours",
                "facility_id", "facility_name", "horse_id", "horse_name",
                "activity_id", "retry_count", "retry_delay_seconds",
            ]
            for key in updatable:
                if key in data:
                    schedule[key] = data[key]
            # Cast types
            for k in ("trigger_weekday", "booking_date_offset", "retry_count", "retry_delay_seconds"):
                if k in schedule:
                    schedule[k] = int(schedule[k])
            schedule["duration_hours"] = float(schedule["duration_hours"])
            self._save()

        self._unregister_schedule(schedule_id)
        if schedule.get("enabled"):
            self._register_schedule(schedule)
        _LOGGER.info("Schedule updated: %s", schedule_id)
        return schedule

    def delete_schedule(self, schedule_id: str) -> bool:
        self._unregister_schedule(schedule_id)
        with self._lock:
            before = len(self._schedules)
            self._schedules = [s for s in self._schedules if s["id"] != schedule_id]
            if len(self._schedules) == before:
                return False
            self._save()
        _LOGGER.info("Schedule deleted: %s", schedule_id)
        return True

    def toggle_schedule(self, schedule_id: str) -> Optional[Dict]:
        with self._lock:
            schedule = next((s for s in self._schedules if s["id"] == schedule_id), None)
            if not schedule:
                return None
            schedule["enabled"] = not schedule["enabled"]
            self._save()

        self._unregister_schedule(schedule_id)
        if schedule["enabled"]:
            self._register_schedule(schedule)
            _LOGGER.info("Schedule enabled: %s", schedule_id)
        else:
            _LOGGER.info("Schedule disabled: %s", schedule_id)
        return schedule

    # ── Scheduler integration ───────────────────────────────────────────────────

    def _reschedule_all(self):
        self._scheduler.remove_all_jobs()
        for schedule in self._schedules:
            if schedule.get("enabled"):
                self._register_schedule(schedule)

    def _register_schedule(self, schedule: dict):
        tz_name = self._config.get("timezone", "Europe/Berlin")
        hour, minute = schedule["trigger_time"].split(":")
        # APScheduler weekday: 0=Mon … 6=Sun (same as Python)
        dow = schedule["trigger_weekday"]

        self._scheduler.add_job(
            func=self._execute_booking,
            trigger=CronTrigger(
                day_of_week=dow,
                hour=int(hour),
                minute=int(minute),
                timezone=tz_name,
            ),
            id=schedule["id"],
            replace_existing=True,
            kwargs={"schedule_id": schedule["id"]},
        )

        # Update next_run in storage
        job = self._scheduler.get_job(schedule["id"])
        if job and job.next_run_time:
            with self._lock:
                s = next((s for s in self._schedules if s["id"] == schedule["id"]), None)
                if s:
                    s["next_run"] = job.next_run_time.isoformat()
                    self._save()

    def _unregister_schedule(self, schedule_id: str):
        try:
            self._scheduler.remove_job(schedule_id)
        except Exception:
            pass

    # ── Booking execution ───────────────────────────────────────────────────────

    def _execute_booking(self, schedule_id: str):
        schedule = self.get_schedule(schedule_id)
        if not schedule or not schedule.get("enabled"):
            return

        _LOGGER.info("Executing schedule '%s' (%s)", schedule["name"], schedule_id)

        tz = ZoneInfo(self._config.get("timezone", "Europe/Berlin"))
        now_local = datetime.now(tz)

        # Calculate target date
        target_date = (now_local + timedelta(days=schedule["booking_date_offset"])).date()
        bh, bm = map(int, schedule["booking_time"].split(":"))
        start_local = datetime(target_date.year, target_date.month, target_date.day, bh, bm, tzinfo=tz)
        end_local = start_local + timedelta(hours=schedule["duration_hours"])

        from datetime import timezone as dt_timezone
        start_iso = start_local.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_iso = end_local.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        api = self._api_factory()
        if not api:
            self._update_status(schedule_id, "error", "API not available (check credentials)")
            return

        result = None
        for attempt in range(1, schedule["retry_count"] + 1):
            if attempt > 1:
                import time
                time.sleep(schedule["retry_delay_seconds"])
                _LOGGER.info("Retry attempt %d/%d for schedule '%s'", attempt, schedule["retry_count"], schedule["name"])

            try:
                result = api.book_facility(
                    facility_id=schedule["facility_id"],
                    horse_id=schedule["horse_id"],
                    start_iso=start_iso,
                    end_iso=end_iso,
                    activity_id=schedule.get("activity_id"),
                )
                if result.get("success"):
                    break
            except Exception as exc:
                result = {"success": False, "error": str(exc)}

        success = result and result.get("success")
        status = "success" if success else "error"
        date_str = start_local.strftime("%A %d.%m.%Y %H:%M")
        tz_str = schedule.get("facility_name", schedule["facility_id"])
        horse = schedule.get("horse_name", schedule["horse_id"])

        if success:
            msg = (
                f"✅ <b>Automatische Buchung erfolgreich</b>\n\n"
                f"📍 {tz_str}\n"
                f"🐴 {horse}\n"
                f"📅 {date_str}\n"
                f"⏱ {schedule['duration_hours']}h"
            )
            _LOGGER.info("Schedule '%s' executed successfully: %s", schedule["name"], date_str)
        else:
            error = (result or {}).get("error", "Unbekannter Fehler")
            conflicts = (result or {}).get("conflicts", [])
            conflict_str = "\n".join(f"  • {c}" for c in conflicts)
            msg = (
                f"❌ <b>Automatische Buchung fehlgeschlagen</b>\n\n"
                f"📍 {tz_str}\n"
                f"🐴 {horse}\n"
                f"📅 {date_str}\n"
                f"❗ {error}"
                + (f"\n{conflict_str}" if conflict_str else "")
            )
            _LOGGER.error("Schedule '%s' failed: %s", schedule["name"], error)

        # Send Telegram notification
        tok = self._config.get("telegram_bot_token", "")
        cid = self._config.get("telegram_chat_id", "")
        if tok and cid:
            telegram.send(tok, cid, msg)

        self._update_status(schedule_id, status, msg)

    def _update_status(self, schedule_id: str, status: str, message: str):
        with self._lock:
            schedule = next((s for s in self._schedules if s["id"] == schedule_id), None)
            if schedule:
                schedule["last_run"] = datetime.utcnow().isoformat()
                schedule["last_status"] = status
                schedule["last_message"] = message
                # Refresh next_run
                job = self._scheduler.get_job(schedule_id)
                if job and job.next_run_time:
                    schedule["next_run"] = job.next_run_time.isoformat()
                self._save()

    # ── Persistence ─────────────────────────────────────────────────────────────

    def _load(self):
        if SCHEDULES_PATH.exists():
            try:
                with SCHEDULES_PATH.open() as f:
                    self._schedules = json.load(f)
                _LOGGER.info("Loaded %d schedule(s) from disk", len(self._schedules))
            except Exception as exc:
                _LOGGER.error("Failed to load schedules: %s", exc)
                self._schedules = []
        else:
            self._schedules = []

    def _save(self):
        """Must be called with _lock held."""
        try:
            SCHEDULES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with SCHEDULES_PATH.open("w") as f:
                json.dump(self._schedules, f, indent=2)
        except Exception as exc:
            _LOGGER.error("Failed to save schedules: %s", exc)
