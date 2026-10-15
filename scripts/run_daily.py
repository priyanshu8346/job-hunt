#!/usr/bin/env python3
"""Run the daily digest with a process lock and private, rotating logs."""
from __future__ import annotations

import fcntl
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    os.umask(0o077)
    os.chdir(ROOT)
    for name in (".env", "profile.json", "companies.yaml", "config.yaml"):
        if not (ROOT / name).is_file():
            raise SystemExit(f"Missing required file: {name}")
    for module in ("requests", "yaml"):
        if importlib.util.find_spec(module) is None:
            raise SystemExit(f"Missing Python dependency: {module}")
    if sys.argv[1:] == ["--check"]:
        print(f"Runner ready: {ROOT}; Python: {sys.executable}")
        return 0
    if sys.argv[1:]:
        raise SystemExit("Usage: run_daily.py [--check]")

    logs = ROOT / "out" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "daily.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Daily digest already running; skipping overlapping run.")
            return 0
        log_path = logs / "daily.log"
        if log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
            log_path.replace(logs / "daily.previous.log")
        with log_path.open("a", buffering=1) as log:
            print(f"\n[{datetime.now().astimezone().isoformat()}] Starting daily digest", file=log)
            result = subprocess.run(
                [sys.executable, "-u", "-m", "jobhunt", "run", "--send"],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False,
            )
            print(f"[{datetime.now().astimezone().isoformat()}] Exit status: {result.returncode}", file=log)
            return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
