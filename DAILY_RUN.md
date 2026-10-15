# Daily Email Digest on macOS (LaunchAgent)

The LaunchAgent `com.jobhunt.daily` runs automatically every morning at **08:00** in your Mac's local timezone.

It executes the project's virtual environment Python directly without requiring VS Code or keeping a terminal open.

---

## 1. Quick Install

Run the one-line setup script from the project root:

```bash
./scripts/setup_daily.sh
```

This generates `~/Library/LaunchAgents/com.jobhunt.daily.plist` with your local directory and Python paths and registers it with `launchd`.

---

## 2. Managing the Schedule

### Check status:
```bash
launchctl print gui/$(id -u)/com.jobhunt.daily
```

### Run an immediate test execution:
```bash
launchctl kickstart gui/$(id -u)/com.jobhunt.daily
```

### Stop / unload the schedule:
```bash
launchctl bootout gui/$(id -u)/com.jobhunt.daily
```

### Reload / restore the schedule:
```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.jobhunt.daily.plist"
```

---

## 3. Logs and Output

Logs are maintained under `out/logs/`:
- `out/logs/daily.log`: Complete execution transcript (fetching, prefiltering, LLM screening, application kit drafting, SMTP email status). Rotates automatically at 5MB.
- `out/logs/daily.previous.log`: Previous log file after rotation.
- `out/logs/scheduler.log`: Launchd daemon startup/exit logs.
- `out/logs/daily.lock`: File-lock to prevent overlapping execution runs.
