# BAT Monitor Dashboard 0.1.0

First public release of BAT Monitor Dashboard.

## Highlights

- Monitor multiple BAT jobs from one Windows desktop dashboard.
- Start, stop, restart, edit, and delete monitored tasks.
- Display each task in a movable and resizable live-output panel.
- Preserve panel layout and user settings under `%LOCALAPPDATA%\BatMonitorDashboard\config.json`.
- Clean terminal output for ANSI control sequences, carriage-return progress updates, and Node / Vue / `npm run serve` output.
- Configure task output encoding with `utf-8`, `cp950`, `big5`, or system default.
- Show host health metrics: heartbeat, CPU, memory, system disk, uptime, task count, and network traffic.
- Send Discord Webhook status updates by editing one message instead of spamming the channel.
- Configure Discord status title, Webhook URL, update interval, and daily restart schedule.
- Stop full process trees with `taskkill /T /F`.

## Documentation

- Chinese README: `README.md`
- English README: `README_EN.md`
- Generated README screenshots under `docs/images/`
- Rebuild documentation images with `python tools/generate_readme_images.py`
