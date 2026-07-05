# HorsePlus Booking

## Configuration

| Option | Required | Description |
|---|---|---|
| `email` | Yes | Your HorsePlus account email address. |
| `password` | Yes | Your HorsePlus account password. Stored only in the add-on's private config, never in code. |
| `timezone` | Yes | IANA timezone used to interpret all times you enter (e.g. `Europe/Berlin`). |
| `telegram_bot_token` | No | Bot token from [@BotFather](https://t.me/BotFather), used to send booking success/failure notifications. |
| `telegram_chat_id` | No | Chat ID that should receive notifications. Leave empty to disable Telegram notifications. |
| `retry_count` | Yes | Default number of booking attempts for new schedules (1–10). |
| `retry_delay_seconds` | Yes | Default delay between retry attempts, in seconds (0–60). |

After changing configuration, restart the add-on for changes to take effect.

### Finding your Telegram chat ID

1. Create a bot via [@BotFather](https://t.me/BotFather) and copy the token.
2. Send any message to your new bot.
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser.
4. Look for `"chat":{"id": ...}` in the JSON response — that's your chat ID.

## Using the Web UI

Open the add-on's **Web UI** (via the Home Assistant sidebar, or the "Open Web UI"
button on the add-on's Info tab). Three tabs are available:

### Dashboard
- **Book Now** — pick a facility, horse, date/time and duration, and book
  immediately. Availability is checked automatically before booking.
- **Upcoming Bookings** — shows your confirmed reservations for the current
  and next month, with a one-click **Cancel** button.

### Schedules
Create recurring auto-booking rules. Each schedule has two independent parts:

- **When to run** — the weekday + time the add-on should attempt the booking
  (e.g. "every Monday at 08:00", right when a facility's booking window opens).
- **What to book** — how many days after the trigger the target slot is
  (e.g. "+7 days"), the booking time, and duration.

Schedules can be enabled/disabled, edited, deleted, or triggered manually with
**Run now** (useful for testing). The last run's status and the next scheduled
run time are shown on each schedule card.

### Calendar
A month-by-month grid of all your facility reservations. Use the arrows to
navigate between months.

## Notifications

If Telegram is configured, you'll receive a message after every automatic
booking attempt (success or failure, including conflict details) and after
every manual booking made through the web UI.

## Logs

All activity (logins, booking attempts, retries, schedule execution, errors)
is logged to stdout and appears in the add-on's **Log** tab in Home Assistant.

## Data persistence

Schedules are stored in `/data/schedules.json` inside the add-on's persistent
storage, so they survive add-on restarts and updates.

## Troubleshooting

**"Not connected to HorsePlus" banner** — double check your email/password in
the Configuration tab, then restart the add-on and check the Log tab for the
specific login error.

**Booking always fails with "Time slot not available"** — someone else (or
another schedule) has already booked that facility/time. Check the Calendar
tab for conflicts.

**Telegram messages not arriving** — verify the bot token and chat ID, and
make sure you've sent at least one message to the bot first (Telegram
requires this before a bot can message a user).
