"""
Flask web app — management UI for HorsePlus Booking Add-on.
Served via Home Assistant Ingress (accessible from the HA sidebar).
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, render_template, abort

_LOGGER = logging.getLogger(__name__)

app = Flask(__name__)

# Injected by main.py after startup
_api = None          # HorsePlusAPI instance
_manager = None      # BookingManager instance
_config = {}         # options.json dict


def init(api, manager, config):
    global _api, _manager, _config
    _api = api
    _manager = manager
    _config = config


# ── Helper ──────────────────────────────────────────────────────────────────────

def _require_api():
    if not _api or not _api.user_data:
        abort(503, description="Not connected to HorsePlus. Check credentials in add-on Configuration.")


# ── Status & meta ───────────────────────────────────────────────────────────────

@app.route("/api/status")
def status():
    connected = _api is not None and _api.user_data is not None
    if connected:
        user = _api.get_user_info()
        farm = _api.get_farm_info()
        return jsonify({
            "connected": True,
            "user": f"{user.get('name', {}).get('firstName', '')} {user.get('name', {}).get('lastName', '')}".strip(),
            "farm": farm.get("name", ""),
            "role": user.get("role", ""),
        })
    return jsonify({"connected": False, "error": "Not authenticated"})


@app.route("/api/facilities")
def facilities():
    _require_api()
    return jsonify(_api.get_facilities())


@app.route("/api/horses")
def horses():
    _require_api()
    return jsonify(_api.get_horses())


@app.route("/api/activities")
def activities():
    _require_api()
    facility_id = request.args.get("facility_id")
    if facility_id:
        return jsonify(_api.get_facility_activities(facility_id))
    return jsonify(_api.get_activity_types())


# ── Bookings (current + upcoming) ───────────────────────────────────────────────

@app.route("/api/bookings")
def bookings():
    _require_api()
    tz = ZoneInfo(_config.get("timezone", "Europe/Berlin"))
    now = datetime.now(tz)
    results = []

    # Fetch current and next month
    for year, month in [(now.year, now.month), ((now + timedelta(days=32)).year, (now + timedelta(days=32)).month)]:
        try:
            appts = _api.get_appointments_for_month(year, month)
            facilities_map = {f["facilityId"]: f["name"] for f in _api.get_facilities()}
            for appt in appts:
                if appt.get("type") == "FACILITY_RESERVATION":
                    res = appt.get("facilityReservation", {})
                    tf = res.get("timeFrame", {})
                    start_raw = tf.get("momentFrom", "")
                    end_raw = tf.get("momentTo", "")
                    try:
                        start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).astimezone(tz)
                        end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).astimezone(tz)
                    except Exception:
                        continue
                    if end_dt < now:
                        continue  # skip past bookings
                    fid = res.get("facilityId", "")
                    results.append({
                        "id": res.get("facilityReservationId", ""),
                        "facility": facilities_map.get(fid, fid),
                        "facility_id": fid,
                        "start": start_dt.isoformat(),
                        "end": end_dt.isoformat(),
                        "start_display": start_dt.strftime("%a %d.%m.%Y %H:%M"),
                        "end_display": end_dt.strftime("%H:%M"),
                        "horse": appt.get("horse", {}).get("name", ""),
                    })
        except Exception as exc:
            _LOGGER.warning("Could not fetch bookings for %d/%d: %s", year, month, exc)

    results.sort(key=lambda x: x["start"])
    return jsonify(results)


# ── Book now ────────────────────────────────────────────────────────────────────

@app.route("/api/book", methods=["POST"])
def book_now():
    _require_api()
    data = request.json or {}
    required = ["facility_id", "horse_id", "date", "time", "duration_hours"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {', '.join(missing)}"}), 400

    tz = ZoneInfo(_config.get("timezone", "Europe/Berlin"))
    try:
        start_local = datetime.strptime(f"{data['date']} {data['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        end_local = start_local + timedelta(hours=float(data["duration_hours"]))
        from datetime import timezone as dt_tz
        start_iso = start_local.astimezone(dt_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_iso = end_local.astimezone(dt_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception as exc:
        return jsonify({"success": False, "error": f"Invalid date/time: {exc}"}), 400

    result = _api.book_facility(
        facility_id=data["facility_id"],
        horse_id=data["horse_id"],
        start_iso=start_iso,
        end_iso=end_iso,
        activity_id=data.get("activity_id"),
        comment=data.get("comment"),
    )

    if result.get("success"):
        tok = _config.get("telegram_bot_token", "")
        cid = _config.get("telegram_chat_id", "")
        if tok and cid:
            import telegram_notifier as tg
            tg.send(tok, cid,
                f"✅ <b>Buchung erfolgreich</b>\n\n"
                f"📍 {data.get('facility_name', data['facility_id'])}\n"
                f"🐴 {data.get('horse_name', data['horse_id'])}\n"
                f"📅 {start_local.strftime('%a %d.%m.%Y %H:%M')} ({data['duration_hours']}h)")

    return jsonify(result)


@app.route("/api/bookings/<reservation_id>", methods=["DELETE"])
def cancel_booking(reservation_id):
    _require_api()
    result = _api.cancel_reservation(reservation_id)
    return jsonify(result)


# ── Schedule CRUD ───────────────────────────────────────────────────────────────

@app.route("/api/schedules")
def list_schedules():
    return jsonify(_manager.list_schedules())


@app.route("/api/schedules", methods=["POST"])
def create_schedule():
    data = request.json or {}
    required = ["facility_id", "horse_id", "trigger_weekday", "trigger_time", "booking_time", "duration_hours"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {', '.join(missing)}"}), 400
    schedule = _manager.create_schedule(data)
    return jsonify(schedule), 201


@app.route("/api/schedules/<schedule_id>", methods=["PUT"])
def update_schedule(schedule_id):
    data = request.json or {}
    schedule = _manager.update_schedule(schedule_id, data)
    if not schedule:
        return jsonify({"error": "Not found"}), 404
    return jsonify(schedule)


@app.route("/api/schedules/<schedule_id>", methods=["DELETE"])
def delete_schedule(schedule_id):
    if not _manager.delete_schedule(schedule_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


@app.route("/api/schedules/<schedule_id>/toggle", methods=["POST"])
def toggle_schedule(schedule_id):
    schedule = _manager.toggle_schedule(schedule_id)
    if not schedule:
        return jsonify({"error": "Not found"}), 404
    return jsonify(schedule)


@app.route("/api/schedules/<schedule_id>/run", methods=["POST"])
def run_schedule_now(schedule_id):
    """Manually trigger a schedule immediately."""
    schedule = _manager.get_schedule(schedule_id)
    if not schedule:
        return jsonify({"error": "Not found"}), 404
    import threading
    t = threading.Thread(target=_manager._execute_booking, kwargs={"schedule_id": schedule_id})
    t.start()
    return jsonify({"success": True, "message": "Schedule triggered"})


# ── Calendar ────────────────────────────────────────────────────────────────────

@app.route("/api/calendar")
def calendar():
    _require_api()
    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    tz = ZoneInfo(_config.get("timezone", "Europe/Berlin"))
    facilities_map = {f["facilityId"]: f["name"] for f in _api.get_facilities()}
    try:
        appts = _api.get_appointments_for_month(year, month)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    events = []
    for appt in appts:
        if appt.get("type") == "FACILITY_RESERVATION":
            res = appt.get("facilityReservation", {})
            tf = res.get("timeFrame", {})
            try:
                start_dt = datetime.fromisoformat(tf["momentFrom"].replace("Z", "+00:00")).astimezone(tz)
                end_dt = datetime.fromisoformat(tf["momentTo"].replace("Z", "+00:00")).astimezone(tz)
            except Exception:
                continue
            fid = res.get("facilityId", "")
            events.append({
                "id": res.get("facilityReservationId", ""),
                "facility": facilities_map.get(fid, fid),
                "day": start_dt.day,
                "start_time": start_dt.strftime("%H:%M"),
                "end_time": end_dt.strftime("%H:%M"),
                "horse": appt.get("horse", {}).get("name", ""),
            })
    return jsonify({"year": year, "month": month, "events": events})


# ── UI ──────────────────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def index(path):
    return render_template("index.html")
