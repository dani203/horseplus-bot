# Home Assistant Add-on: HorsePlus Booking

Automated paddock/facility booking for [HorsePlus](https://my.horseplus.app) stables —
with a built-in web UI, flexible recurring schedules, and Telegram notifications.

## About

This add-on replaces the original collection of CLI scripts and cron jobs with a
self-contained service that runs entirely inside Home Assistant:

- **Web UI** (available in the HA sidebar via Ingress) to book instantly, view
  upcoming reservations, browse a monthly calendar, and manage recurring
  auto-booking schedules — create, edit, enable/disable, delete, and "run now".
- **Automatic booking** — define a weekly trigger (e.g. "every Monday at 08:00")
  and a target booking slot (e.g. "7 days later at 16:30 for 1.5h"). The add-on
  books it for you automatically, with configurable retries.
- **Telegram notifications** for booking successes and failures (optional).
- **No hardcoded secrets** — your HorsePlus email/password and Telegram bot
  token are entered in the add-on's Configuration tab and never stored in code.
- **Native HA logging** — all activity appears in the add-on's Log tab.

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮** menu (top right) → **Repositories**.
3. Add this repository's URL: `https://github.com/dani203/horseplus-bot`
4. Find **HorsePlus Booking** in the store list and click **Install**.
5. Go to the **Configuration** tab and enter your HorsePlus email/password
   (and optionally your Telegram bot token + chat ID).
6. Start the add-on, then open its **Web UI** from the sidebar.

See [DOCS.md](horseplus/DOCS.md) for full configuration and usage details.

## Repository structure

This repo follows the standard Home Assistant add-on repository layout:

```
horseplus-addon/
├── repository.json          ← identifies this as an add-on repository
└── horseplus/                ← the add-on itself
    ├── config.yaml
    ├── Dockerfile
    ├── build.yaml
    ├── DOCS.md
    ├── CHANGELOG.md
    ├── icon.png / logo.png
    └── rootfs/app/            ← Flask web app + booking engine
```

## License

MIT
