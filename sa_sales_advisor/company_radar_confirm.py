#!/usr/bin/env python3
"""Confirm verified company intelligence into a customer's durable timeline."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def find_customer_folder(root: Path, customer_id: str) -> Path:
    index = read_json(root / "indexes/customer-index.json", {"customers": []})
    for item in index.get("customers", []):
        if item.get("customer_id") == customer_id:
            folder = item.get("folder") or item.get("folder_name")
            path = root / "customers" / str(folder or "")
            if folder and path.is_dir():
                return path
    for path in (root / "customers").glob("*/customer.json"):
        if read_json(path, {}).get("customer_id") == customer_id:
            return path.parent
    raise SystemExit(f"customer folder not found: {customer_id}")


def find_evidence(root: Path, customer_id: str, evidence_id: str) -> dict:
    path = root / "indexes/company-intelligence.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if item.get("customer_id") == customer_id and item.get("evidence_id") == evidence_id:
                return item
    raise SystemExit(f"evidence not found: {evidence_id}")


def render_customer_file(customer_dir: Path, records: list[dict]) -> Path:
    lines = ["# 企业动态", "", "以下内容均已核验公开原文，并经销售确认纳入客户档案。", ""]
    for item in records:
        lines.extend([
            f"## {item.get('published_at') or '日期待确认'} · {item.get('title') or '企业动态'}", "",
            f"- 类型：{item.get('event_type') or '其他'}",
            f"- 企业角色：{item.get('company_role') or '待确认'}",
            f"- 摘要：{item.get('summary') or '详见原文'}",
            f"- 来源：[{item.get('source_name') or '公开原文'}]({item.get('source_url')})",
            f"- 证据编号：{item.get('evidence_id')}", "",
        ])
    destination = customer_dir / "company-intelligence.md"
    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return destination


def write_timeline(customer_dir: Path, record: dict, timestamp: str) -> Path:
    timeline = customer_dir / "timeline"
    timeline.mkdir(parents=True, exist_ok=True)
    day = re.sub(r"[^0-9-]", "", str(record.get("published_at", "")))[:10] or datetime.now().date().isoformat()
    destination = timeline / f"{day}-company-intelligence-{record['evidence_id']}.md"
    if not destination.exists():
        destination.write_text("\n".join([
            f"# {record.get('title') or '企业动态'}", "",
            f"- 发生日期：{record.get('published_at') or '待确认'}",
            f"- 类型：{record.get('event_type') or '其他'}",
            f"- 企业角色：{record.get('company_role') or '待确认'}",
            f"- 摘要：{record.get('summary') or '详见原文'}",
            f"- 来源：[{record.get('source_name') or '公开原文'}]({record.get('source_url')})",
            f"- 销售确认时间：{timestamp}", "",
        ]), encoding="utf-8")
    return destination


def confirm_record(args) -> None:
    root = Path(args.workspace).expanduser().resolve()
    record = find_evidence(root, args.customer_id, args.evidence_id)
    if record.get("verification_status") != "verified":
        raise SystemExit("only verified company intelligence can enter the customer timeline")
    customer_dir = find_customer_folder(root, args.customer_id)
    path = root / "indexes/company-intelligence-confirmations.json"
    confirmations = read_json(path, {"schema_version": 1, "updated_at": "", "confirmations": {}})
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    confirmations["confirmations"][args.evidence_id] = {
        "evidence_id": args.evidence_id, "customer_id": args.customer_id, "confirmed_at": timestamp,
    }
    confirmations["updated_at"] = timestamp
    write_json(path, confirmations)
    records = []
    for evidence_id, confirmation in confirmations["confirmations"].items():
        if confirmation.get("customer_id") == args.customer_id:
            try:
                item = find_evidence(root, args.customer_id, evidence_id)
            except SystemExit:
                continue
            if item.get("verification_status") == "verified":
                records.append(item)
    records.sort(key=lambda item: item.get("published_at", ""), reverse=True)
    customer_file = render_customer_file(customer_dir, records)
    timeline_file = write_timeline(customer_dir, record, timestamp)
    print(json.dumps({"status": "confirmed", "evidence_id": args.evidence_id, "customer_file": str(customer_file), "timeline_file": str(timeline_file)}, ensure_ascii=False, indent=2))
