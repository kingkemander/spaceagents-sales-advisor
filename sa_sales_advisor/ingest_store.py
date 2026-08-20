#!/usr/bin/env python3
"""Create customers, register confirmed materials, and validate workspace links."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "customer"


def require_workspace(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    required = root / "indexes/customer-index.json"
    if not required.exists():
        raise SystemExit(f"workspace is not initialized: {root}")
    return root


def rel_inside(root: Path, value: str) -> str:
    path = Path(value).expanduser().resolve()
    try:
        return str(path.relative_to(root))
    except ValueError as exc:
        raise SystemExit(f"path must be inside workspace: {path}") from exc


def find_entry(index: dict, customer_id: str) -> dict:
    for item in index.get("customers", []):
        if item.get("customer_id") == customer_id:
            return item
    raise SystemExit(f"unknown customer_id: {customer_id}")


def create_customer(args: argparse.Namespace) -> None:
    root = require_workspace(args.workspace)
    index_path = root / "indexes/customer-index.json"
    index = load_json(index_path)
    normalized = args.name.strip().casefold()
    for item in index.get("customers", []):
        names = [item.get("name", ""), *item.get("aliases", [])]
        if normalized in {str(x).strip().casefold() for x in names}:
            raise SystemExit(f"customer name or alias already exists: {item['customer_id']}")

    numbers = []
    for item in index.get("customers", []):
        match = re.fullmatch(r"cus-(\d{6})", item.get("customer_id", ""))
        if match:
            numbers.append(int(match.group(1)))
    customer_id = f"cus-{(max(numbers, default=0) + 1):06d}"
    folder_name = f"{customer_id}-{slugify(args.slug or args.name)}"
    customer_dir = root / "customers" / folder_name
    for rel in ["sources/original", "sources/markdown", "timeline"]:
        (customer_dir / rel).mkdir(parents=True, exist_ok=True)

    created_at = now_iso()
    customer = {
        "schema_version": 1,
        "customer_id": customer_id,
        "name": args.name.strip(),
        "aliases": [x.strip() for x in args.alias if x.strip()],
        "owner": args.owner.strip() if args.owner else "",
        "source_channel": "",
        "company_name": "",
        "job_title": "",
        "industry": "",
        "contacts": [],
        "status": "prospect",
        "stage": "",
        "intent_level": "unknown",
        "needs": [],
        "budget": "",
        "timeline": "",
        "decision_chain": [],
        "objections": [],
        "competitors": [],
        "last_contact_at": None,
        "next_followup_at": None,
        "latest_update": "新建客户，等待材料确认",
        "followup_reason": "",
        "next_action": "",
        "reply_suggestion": "",
        "risks": [],
        "won_details": {},
        "lost_details": {},
        "unconfirmed": [],
        "evidence": [],
        "created_at": created_at,
        "updated_at": created_at,
    }
    save_json(customer_dir / "customer.json", customer)
    (customer_dir / "customer-card.md").write_text(f"# {args.name}｜客户卡片\n\n等待首次资料确认。\n", encoding="utf-8")
    (customer_dir / "current-status.md").write_text(f"# {args.name}｜当前状态\n\n- 状态：潜在客户\n", encoding="utf-8")
    (customer_dir / "follow-up-plan.md").write_text(f"# {args.name}｜跟进计划\n\n- 下一步：待确认\n", encoding="utf-8")
    (customer_dir / "evidence-index.md").write_text(f"# {args.name}｜证据索引\n", encoding="utf-8")

    entry = {
        "customer_id": customer_id,
        "name": args.name.strip(),
        "aliases": customer["aliases"],
        "contacts": [],
        "owner": customer["owner"],
        "workspace_path": f"customers/{folder_name}",
        "updated_at": created_at,
    }
    index.setdefault("customers", []).append(entry)
    index["updated_at"] = created_at
    save_json(index_path, index)
    print(json.dumps({"status": "created", **entry}, ensure_ascii=False, indent=2))


def register_material(args: argparse.Namespace) -> None:
    root = require_workspace(args.workspace)
    customer_index = load_json(root / "indexes/customer-index.json")
    entry = find_entry(customer_index, args.customer_id)
    material_path = root / "indexes/material-index.json"
    materials = load_json(material_path)
    if any(x.get("source_hash") == args.source_hash for x in materials.get("materials", [])):
        raise SystemExit("material with this hash is already registered")
    original_rel = rel_inside(root, args.original)
    markdown_rel = rel_inside(root, args.markdown)
    if not (root / original_rel).exists() or not (root / markdown_rel).exists():
        raise SystemExit("original and markdown files must exist before registration")
    ingestion_id = "ing-" + datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    record = {
        "ingestion_id": ingestion_id,
        "customer_id": args.customer_id,
        "source_hash": args.source_hash,
        "original_path": original_rel,
        "markdown_path": markdown_rel,
        "confirmed_by": args.confirmed_by,
        "confirmed_at": now_iso(),
        "status": "committed",
    }
    materials.setdefault("materials", []).append(record)
    materials["updated_at"] = now_iso()
    save_json(material_path, materials)
    with (root / "indexes/ingestion-ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "registered", "customer": entry["name"], **record}, ensure_ascii=False, indent=2))


def hash_file(args: argparse.Namespace) -> None:
    digest = hashlib.sha256()
    with Path(args.file).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    print(digest.hexdigest())


def validate(args: argparse.Namespace) -> None:
    root = require_workspace(args.workspace)
    index = load_json(root / "indexes/customer-index.json")
    errors = []
    seen_ids = set()
    seen_paths = set()
    for entry in index.get("customers", []):
        cid = entry.get("customer_id")
        rel = entry.get("workspace_path")
        if cid in seen_ids:
            errors.append(f"duplicate customer_id: {cid}")
        if rel in seen_paths:
            errors.append(f"duplicate workspace_path: {rel}")
        seen_ids.add(cid)
        seen_paths.add(rel)
        customer_file = root / str(rel) / "customer.json"
        if not customer_file.exists():
            errors.append(f"missing customer.json: {rel}")
            continue
        customer = load_json(customer_file)
        if customer.get("customer_id") != cid:
            errors.append(f"customer_id mismatch: {rel}")
    result = {"status": "ok" if not errors else "invalid", "customers": len(seen_ids), "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--workspace", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--slug")
    create.add_argument("--owner", default="")
    create.add_argument("--alias", action="append", default=[])
    create.set_defaults(func=create_customer)

    register = sub.add_parser("register-material")
    register.add_argument("--workspace", required=True)
    register.add_argument("--customer-id", required=True)
    register.add_argument("--original", required=True)
    register.add_argument("--markdown", required=True)
    register.add_argument("--source-hash", required=True)
    register.add_argument("--confirmed-by", required=True)
    register.set_defaults(func=register_material)

    hash_cmd = sub.add_parser("hash")
    hash_cmd.add_argument("--file", required=True)
    hash_cmd.set_defaults(func=hash_file)

    check = sub.add_parser("validate")
    check.add_argument("--workspace", required=True)
    check.set_defaults(func=validate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
