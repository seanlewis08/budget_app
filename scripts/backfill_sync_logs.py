#!/usr/bin/env python3
"""
Backfill SyncLog entries from ~/BudgetApp/logs/sync.log.

Parses the daemon log file and inserts SyncLog rows for historical syncs
that happened before the SyncLog table was added.

Usage:
    cd ~/DataspellProjects/budget-app
    uv run python3 -m scripts.backfill_sync_logs              # dry run
    uv run python3 -m scripts.backfill_sync_logs --apply       # actually insert
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Ensure project root is on the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from backend.database import SessionLocal, init_db
from backend.models import SyncLog, Account

LOG_PATH = Path.home() / "BudgetApp" / "logs" / "sync.log"

# Patterns
RESULT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[INFO\]\s+"
    r"(.+?):\s+\+(\d+) new, (\d+) updated, (\d+) removed$"
)
FAILED_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[ERROR\]\s+"
    r"(.+?):\s+FAILED — (.*)$"
)
SYNC_START_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[INFO\] Starting Plaid sync"
)


def parse_log(log_path):
    """Parse sync.log and return a list of sync event dicts."""
    events = []
    current_start = None

    with open(log_path) as f:
        for line in f:
            line = line.rstrip()

            # Track sync run start time
            m = SYNC_START_RE.match(line)
            if m:
                current_start = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                continue

            # Successful sync result
            m = RESULT_RE.match(line)
            if m:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                account_name = m.group(2).strip()
                events.append({
                    "started_at": current_start or ts,
                    "finished_at": ts,
                    "account_name": account_name,
                    "status": "success",
                    "added": int(m.group(3)),
                    "modified": int(m.group(4)),
                    "removed": int(m.group(5)),
                    "error_message": None,
                })
                continue

            # Failed sync
            m = FAILED_RE.match(line)
            if m:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                account_name = m.group(2).strip()
                error_msg = m.group(3).strip()
                # Truncate long error messages
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."
                if not error_msg:
                    error_msg = "Unknown error (empty message)"
                events.append({
                    "started_at": current_start or ts,
                    "finished_at": ts,
                    "account_name": account_name,
                    "status": "error",
                    "added": 0,
                    "modified": 0,
                    "removed": 0,
                    "error_message": error_msg,
                })
                continue

    return events


def backfill(events, apply=False):
    """Insert parsed events into the SyncLog table."""
    init_db()
    db = SessionLocal()

    # Build account name -> id map
    accounts = db.query(Account).all()
    name_to_id = {a.name: a.id for a in accounts}

    # Check what already exists so we don't duplicate
    existing = db.query(SyncLog).all()
    existing_keys = set()
    for log in existing:
        key = (log.account_id, log.started_at.isoformat() if log.started_at else "")
        existing_keys.add(key)

    inserted = 0
    skipped = 0

    for event in events:
        account_id = name_to_id.get(event["account_name"])
        if not account_id:
            print(f"  SKIP: Unknown account '{event['account_name']}'")
            skipped += 1
            continue

        # Check for duplicate
        key = (account_id, event["started_at"].isoformat())
        if key in existing_keys:
            skipped += 1
            continue

        duration = (event["finished_at"] - event["started_at"]).total_seconds()

        status_icon = "✓" if event["status"] == "success" else "✗"
        print(
            f"  {status_icon} {event['started_at'].strftime('%b %d %H:%M')} "
            f"{event['account_name']:20s} "
            f"+{event['added']} ~{event['modified']} -{event['removed']}"
            f"{('  ERR: ' + event['error_message'][:60]) if event['error_message'] else ''}"
        )

        if apply:
            log_entry = SyncLog(
                account_id=account_id,
                trigger="scheduled",
                status=event["status"],
                added=event["added"],
                modified=event["modified"],
                removed=event["removed"],
                error_message=event["error_message"],
                duration_seconds=round(duration, 1),
                started_at=event["started_at"],
            )
            db.add(log_entry)
            existing_keys.add(key)

        inserted += 1

    if apply:
        db.commit()
        print(f"\nInserted {inserted} sync log entries, skipped {skipped}.")
    else:
        print(f"\nDRY RUN: Would insert {inserted} entries, skip {skipped}.")
        print("Run with --apply to actually insert.")

    db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill SyncLog from sync.log")
    parser.add_argument("--apply", action="store_true", help="Actually insert (default is dry run)")
    parser.add_argument("--log-file", type=str, default=str(LOG_PATH), help="Path to sync.log")
    args = parser.parse_args()

    log_path = Path(args.log_file)
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    print(f"Parsing {log_path}...")
    events = parse_log(log_path)
    print(f"Found {len(events)} sync events.\n")

    if not events:
        print("Nothing to backfill.")
        return

    backfill(events, apply=args.apply)


if __name__ == "__main__":
    main()
