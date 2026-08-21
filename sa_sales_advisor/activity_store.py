#!/usr/bin/env python3
"""Append and read local sales activity events for reminders and daily sync."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime
from pathlib import Path


EVENT_TYPES = {"completed", "milestone", "deferred", "cancelled", "note"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_time(value: str | None) -> str:
    if not value:
        return now_iso()
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.isoformat(timespec="seconds")


def event_path(root: Path) -> Path:
    return root / "logs/task-events.jsonl"


def append_event(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    path = event_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event_id": f"evt-{uuid.uuid4().hex[:12]}",
        "event_type": args.event_type,
        "title": args.title.strip(),
        "customer_id": (args.customer_id or "").strip(),
        "customer_name": (args.customer_name or "").strip(),
        "details": (args.details or "").strip(),
        "occurred_at": parse_time(args.occurred_at),
        "recorded_at": now_iso(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "recorded", **event}, ensure_ascii=False, indent=2))
    return 0


def load_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def list_events(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    events = load_events(event_path(root))
    if args.date:
        events = [item for item in events if str(item.get("occurred_at", ""))[:10] == args.date]
    if args.event_type:
        events = [item for item in events if item.get("event_type") == args.event_type]
    print(json.dumps({"events": events}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    add = sub.add_parser("add")
    add.add_argument("--root", required=True)
    add.add_argument("--event-type", choices=sorted(EVENT_TYPES), required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--customer-id")
    add.add_argument("--customer-name")
    add.add_argument("--details")
    add.add_argument("--occurred-at")
    add.set_defaults(func=append_event)

    show = sub.add_parser("list")
    show.add_argument("--root", required=True)
    show.add_argument("--date")
    show.add_argument("--event-type", choices=sorted(EVENT_TYPES))
    show.set_defaults(func=list_events)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
