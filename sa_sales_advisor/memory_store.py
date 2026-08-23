#!/usr/bin/env python3
"""Apply confirmed patches and render concise customer Markdown views."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from presentation import clean_public_value, contains_internal_language
from pipeline_store import render as render_pipeline


ALLOWED_FIELDS = {
    "name", "aliases", "owner", "source_channel", "company_name", "job_title", "industry", "contacts", "status", "stage",
    "intent_level", "needs", "budget", "timeline", "decision_chain", "objections",
    "competitors", "last_contact_at", "next_followup_at", "latest_update",
    "followup_reason", "next_action", "reply_suggestion", "risks", "won_details",
    "lost_details", "unconfirmed", "evidence", "pipeline_stage", "opportunity_amount",
    "currency", "expected_close_date", "win_probability"
}
PUBLIC_FIELDS = ALLOWED_FIELDS - {"evidence"}


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
    customer = clean_public_value(customer)
    name = customer.get("name") or customer.get("customer_id")
    contacts = customer.get("contacts", [])
    status_label = {
        "prospect": "潜在客户", "active": "推进中", "won": "已成交",
        "lost": "未成交", "paused": "暂缓", "dormant": "沉默",
    }.get(customer.get("status"), customer.get("status") or "未确认")
    intent_label = {
        "high": "高意向", "medium": "中意向", "low": "低意向", "unknown": "待确认",
    }.get(customer.get("intent_level"), customer.get("intent_level") or "待确认")
    card = f"""# {name}｜客户卡片

> 更新时间：{customer.get('updated_at', '')}

## 身份信息

- 行业：{customer.get('industry') or '未确认'}
- 公司：{customer.get('company_name') or '未确认'}
- 职位：{customer.get('job_title') or '未确认'}
- 来源渠道：{customer.get('source_channel') or '未确认'}
- 销售负责人：{customer.get('owner') or '未确认'}

### 联系人

{bullets(contacts)}

## 当前状态

- 客户状态：{status_label}
- 成交阶段：{customer.get('stage') or '未确认'}
- 销售漏斗：{customer.get('pipeline_stage') or '初步接触'}
- 机会金额：{customer.get('opportunity_amount') if customer.get('opportunity_amount') is not None else '未确认'} {customer.get('currency') or 'CNY'}
- 预计成交：{customer.get('expected_close_date') or '未确认'}
- 成交概率：{customer.get('win_probability') if customer.get('win_probability') is not None else '未确认'}%
- 意向程度：{intent_label}
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

- 状态：{status_label}
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
    dirty = sorted(key for key in PUBLIC_FIELDS if key in patch and contains_internal_language(patch[key]))
    if dirty:
        raise SystemExit(
            "customer-facing fields contain internal processing language: "
            + ", ".join(dirty)
            + ". Rewrite them as direct business conclusions before updating."
        )
    valid_stages = ["初步接触", "需求确认", "方案演示", "报价谈判", "赢单", "输单"]
    if "pipeline_stage" in patch and patch["pipeline_stage"] not in valid_stages:
        raise SystemExit("pipeline_stage must be one of: " + "、".join(valid_stages))
    if "win_probability" in patch:
        value = patch["win_probability"]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
            raise SystemExit("win_probability must be an integer from 0 to 100")
    if "opportunity_amount" in patch:
        value = patch["opportunity_amount"]
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0):
            raise SystemExit("opportunity_amount must be a non-negative number or null")
    if "expected_close_date" in patch and patch["expected_close_date"] not in (None, ""):
        try:
            date.fromisoformat(str(patch["expected_close_date"]))
        except ValueError as exc:
            raise SystemExit("expected_close_date must use YYYY-MM-DD") from exc
    previous_pipeline_stage = customer.get("pipeline_stage")
    for key, value in patch.items():
        customer[key] = value
    timestamp = now_iso()
    next_pipeline_stage = customer.get("pipeline_stage")
    if next_pipeline_stage and next_pipeline_stage != previous_pipeline_stage:
        history = customer.setdefault("stage_history", [])
        history.append({"stage": next_pipeline_stage, "entered_at": timestamp})
        if next_pipeline_stage == "赢单":
            customer["status"] = "won"
            customer["win_probability"] = 100
        elif next_pipeline_stage == "输单":
            customer["status"] = "lost"
            customer["win_probability"] = 0
        elif customer.get("status") in {"prospect", "dormant"}:
            customer["status"] = "active"
    customer["updated_at"] = timestamp
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
    pipeline_result = render_pipeline(root, date.today())
    print(json.dumps({"status": "updated", "customer_id": args.customer_id, "fields": sorted(patch), "pipeline_report": pipeline_result["report"]}, ensure_ascii=False, indent=2))


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
