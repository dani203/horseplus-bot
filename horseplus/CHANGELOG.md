# Changelog

## 1.0.6

- Fix booking, facility calendar, and appointments requests for the current HorsePlus API using `momentRange.start` and `momentRange.end`.
- Include `personId` when fetching preferred reservation intervals.
- Update the HorsePlus app-version header to match the successful browser capture.
- Add offline regression tests for API payloads, empty booking responses, and availability conflicts.

## 1.0.0

- Initial release.
- Web UI (Dashboard, Schedules, Calendar) served via Home Assistant Ingress.
- Recurring auto-booking schedules with configurable retries, replacing cron.
- Telegram notifications for booking success/failure.
- All credentials configured via the add-on Configuration tab — no secrets in code.
- Full logging to the Home Assistant Log tab.
