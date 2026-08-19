#!/usr/bin/env python3
"""Apply confirmed patches and render concise customer Markdown views."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


ALLOWED_FIELDS = {
    "name", "aliases", "owner", "industry", "contacts", "status", "stage",
    "intent_level", "needs", "budget", "timeline", "decision_chain", "objections",
    "competitors", "last_contact_at", "next_followup_at", "latest_update",
    "followup_reason", "next_action", "reply_suggestion", "risks", "won_details",
    "lost_details", "unconfirmed", "evidence"
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bullets(values, empty="未确认") -> str:
    if not values:
        return f"- {empty}"
    if isinstance(values, str):
        return f"- {values or empty}"
    lines = []
    for value in values:
        if isinstance(value, dict):
            compact = "；".join(f"{k}：{v}" for k, v in value.items() if v not in (None, "", [], {}))
            if compact:
                lines.append(f"- {compact}")
        elif str(value).strip():
            lines.append(f"- {str(value).strip()}")
    return "\n".join(lines) if lines else f"- {empty}"


def find_customer(root: Path, customer_id: str) -> tuple[Path, dict, dict]:
    index_path = root / "indexes/customer-index.json"
    index = load_json(index_path)
    for entry in index.get("customers", []):
        if entry.get("customer_id") == customer_id:
            customer_dir = root / entry["workspace_path"]
            return customer_dir, load_json(customer_dir / "customer.json"), index
    raise SystemExit(f"unknown customer_id: {customer_id}")


def render(customer_dir: Path, customer: dict) -> None:
    name = customer.get("name") or customer.get("customer_id")
    contacts = customer.get("contacts", [])
    card = f"""# {name}｜客户卡片

> 更新时间：{customer.get('updated_at', '')}

## 身份信息

- 客户 ID：{customer.get('customer_id', '')}
- 行业：{customer.get('industry') or '未确认'}
- 销售负责人：{customer.get('owner') or '未确认'}

### 联系人

{bullets(contacts)}

## 当前状态

- 客户状态：{customer.get('status') or '未确认'}
- 成交阶段：{customer.get('stage') or '未确认'}
- 意向程度：{customer.get('intent_level') or 'unknown'}
- 最近沟通：{customer.get('last_contact_at') or '未确认'}
- 下次跟进：{customer.get('next_followup_at') or '未确认'}
- 最新变化：{customer.get('latest_update') or '未确认'}

## 核心画像

### 需求
{bullets(customer.get('needs', []))}

- 预算：{customer.get('budget') or '未确认'}
- 项目周期：{customer.get('timeline') or '未确认'}

### 决策链
{bullets(customer.get('decision_chain', []))}

### 主要异议
{bullets(customer.get('objections', []))}

## 成交后进度

{bullets(customer.get('won_details', {}))}

## 未成交原因

{bullets(customer.get('lost_details', {}))}

## 下一步

- 推荐动作：{customer.get('next_action') or '未确认'}
- 推荐理由：{customer.get('followup_reason') or '未确认'}

### 风险
{bullets(customer.get('risks', []))}

## 待确认

{bullets(customer.get('unconfirmed', []), '无')}
"""
    status = f"""# {name}｜当前状态

- 状态：{customer.get('status') or '未确认'}
- 阶段：{customer.get('stage') or '未确认'}
- 最新变化：{customer.get('latest_update') or '未确认'}
- 最近沟通：{customer.get('last_contact_at') or '未确认'}
- 更新时间：{customer.get('updated_at', '')}
"""
    plan = f"""# {name}｜跟进计划

- 下次跟进：{customer.get('next_followup_at') or '未确认'}
- 跟进原因：{customer.get('followup_reason') or '未确认'}
- 推荐动作：{customer.get('next_action') or '未确认'}
- 回复草稿：{customer.get('reply_suggestion') or '待生成'}

## 风险

{bullets(customer.get('risks', []))}
"""
    (customer_dir / "customer-card.md").write_text(card, encoding="utf-8")
    (customer_dir / "current-status.md").write_text(status, encoding="utf-8")
    (customer_dir / "follow-up-plan.md").write_text(plan, encoding="utf-8")


def update(args: argparse.Namespace) -> None:
    root = Path(args.workspace).expanduser().resolve()
    customer_dir, customer, index = find_customer(root, args.customer_id)
    patch = load_json(Path(args.patch_file))
    unknown = sorted(set(patch) - ALLOWED_FIELDS)
    if unknown:
        raise SystemExit(f"unsupported patch fields: {', '.join(unknown)}")
    for key, value in patch.items():
        customer[key] = value
    customer["updated_at"] = now_iso()
    save_json(customer_dir / "customer.json", customer)
    render(customer_dir, customer)

    for entry in index.get("customers", []):
        if entry.get("customer_id") == args.customer_id:
            for key in ["name", "aliases", "owner"]:
                if key in customer:
                    entry[key] = customer[key]
            entry["contacts"] = [x.get("name", "") for x in customer.get("contacts", []) if isinstance(x, dict)]
            entry["updated_at"] = customer["updated_at"]
    index["updated_at"] = customer["updated_at"]
    save_json(root / "indexes/customer-index.json", index)
    print(json.dumps({"status": "updated", "customer_id": args.customer_id, "fields": sorted(patch)}, ensure_ascii=False, indent=2))


def validate(args: argparse.Namespace) -> None:
    root = Path(args.workspace).expanduser().resolve()
    customer_dir, customer, _ = find_customer(root, args.customer_id)
    errors = []
    if customer.get("customer_id") != args.customer_id:
        errors.append("customer_id mismatch")
    for name in ["customer-card.md", "current-status.md", "follow-up-plan.md"]:
        if not (customer_dir / name).exists():
            errors.append(f"missing {name}")
    print(json.dumps({"status": "ok" if not errors else "invalid", "errors": errors}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    update_cmd = sub.add_parser("update")
    update_cmd.add_argument("--workspace", required=True)
    update_cmd.add_argument("--customer-id", required=True)
    update_cmd.add_argument("--patch-file", required=True)
    update_cmd.set_defaults(func=update)
    check = sub.add_parser("validate")
    check.add_argument("--workspace", required=True)
    check.add_argument("--customer-id", required=True)
    check.set_defaults(func=validate)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
