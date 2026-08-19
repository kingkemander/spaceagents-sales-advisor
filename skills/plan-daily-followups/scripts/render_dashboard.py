#!/usr/bin/env python3
"""Render a standalone daily sales dashboard from local customer JSON files."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path


def parse_day(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def classify(customer: dict, today: date) -> tuple[str, int]:
    due = parse_day(customer.get("next_followup_at"))
    status = customer.get("status")
    if status in {"won", "lost"} and not customer.get("next_action"):
        return "waiting", 5
    if due and due < today:
        return "overdue", 100
    if due == today:
        return "must", 80
    if due and due <= today + timedelta(days=2):
        return "suggested", 60
    if customer.get("risks"):
        return "risk", 45
    if status in {"active", "prospect"} and customer.get("next_action"):
        return "suggested", 30
    return "waiting", 10


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--date", help="YYYY-MM-DD; defaults to local today")
    args = parser.parse_args()
    root = Path(args.workspace).expanduser().resolve()
    today = date.fromisoformat(args.date) if args.date else date.today()
    customers = []
    for path in sorted((root / "customers").glob("*/customer.json")):
        customer = json.loads(path.read_text(encoding="utf-8"))
        bucket, score = classify(customer, today)
        customer_view = {
            "customer_id": customer.get("customer_id"),
            "name": customer.get("name"),
            "status": customer.get("status"),
            "stage": customer.get("stage"),
            "intent_level": customer.get("intent_level"),
            "last_contact_at": customer.get("last_contact_at"),
            "next_followup_at": customer.get("next_followup_at"),
            "latest_update": customer.get("latest_update"),
            "followup_reason": customer.get("followup_reason"),
            "next_action": customer.get("next_action"),
            "reply_suggestion": customer.get("reply_suggestion"),
            "risks": customer.get("risks", []),
            "bucket": bucket,
            "priority": score,
            "source": str(path.relative_to(root)),
        }
        customers.append(customer_view)
    customers.sort(key=lambda x: (-x["priority"], x.get("next_followup_at") or "9999"))
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    data = {"schema_version": 1, "generated_at": generated_at, "date": today.isoformat(), "customers": customers}
    dashboard_dir = root / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    (dashboard_dir / "dashboard-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    template = Path(__file__).resolve().parent.parent / "assets/dashboard-template.html"
    html = template.read_text(encoding="utf-8")
    html = html.replace("__DASHBOARD_DATA_JSON__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    html = html.replace("__GENERATED_AT__", generated_at)
    (dashboard_dir / "index.html").write_text(html, encoding="utf-8")
    counts = {key: sum(1 for x in customers if x["bucket"] == key) for key in ["must", "suggested", "overdue", "risk", "waiting"]}
    print(json.dumps({"status": "rendered", "dashboard": str(dashboard_dir / "index.html"), "customers": len(customers), "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
