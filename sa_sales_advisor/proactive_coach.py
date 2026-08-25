#!/usr/bin/env python3
"""Local, confirmation-first state for the proactive Sales Advisor."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import ingest_store
import memory_store


PROFILE_FIELDS = ["business", "target_customer", "product", "sales_cycle", "current_goal", "region", "industry"]
QUESTION_MAP = {
    "business": "你现在主要销售什么产品或项目？",
    "target_customer": "你最希望服务的是哪类客户或决策人？",
    "product": "客户通常最看重的产品、方案或项目是什么？",
    "sales_cycle": "从首次接触到成交，通常大约需要多久？",
    "current_goal": "你当前最希望军师优先帮你推进的目标是什么？",
}
REQUIRED_CUSTOMER_FIELDS = {
    "company_name": "客户公司", "contacts": "联系人与联系方式", "source_channel": "来源渠道",
    "industry": "所属行业", "needs": "核心需求", "timeline": "决策时间",
    "decision_chain": "决策关系",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: dict) -> dict:
    if not path.is_file():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except json.JSONDecodeError:
        return default


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def root_path(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    if not (root / "indexes/customer-index.json").is_file():
        raise SystemExit(f"workspace is not initialized: {root}")
    return root


def profile_path(root: Path) -> Path:
    return root / "config/sales-profile.json"


def profile(root: Path) -> dict:
    base = {"schema_version": 1, "updated_at": "", "skipped_fields": [], **{field: "" for field in PROFILE_FIELDS}}
    base.update(read_json(profile_path(root), {}))
    return base


def next_question(data: dict) -> dict:
    skipped = set(data.get("skipped_fields", []))
    for field in PROFILE_FIELDS:
        if field in QUESTION_MAP and not str(data.get(field, "")).strip() and field not in skipped:
            return {"complete": False, "field": field, "question": QUESTION_MAP[field]}
    return {"complete": True, "question": "经营画像已具备基础信息。现在最希望推进哪位客户或哪件销售事项？"}


def profile_status(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    data = profile(root)
    answered = [field for field in PROFILE_FIELDS if str(data.get(field, "")).strip()]
    print(json.dumps({"profile": data, "answered": answered, "next": next_question(data)}, ensure_ascii=False, indent=2))


def profile_update(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    data = profile(root)
    patch = read_json(Path(args.patch_file), {}) if args.patch_file else {args.field: args.value}
    invalid = sorted(set(patch) - set(PROFILE_FIELDS))
    if invalid:
        raise SystemExit("unsupported profile fields: " + ", ".join(invalid))
    for key, value in patch.items():
        data[key] = str(value or "").strip()
        if key in data.get("skipped_fields", []):
            data["skipped_fields"].remove(key)
    data["updated_at"] = now_iso()
    write_json(profile_path(root), data)
    print(json.dumps({"status": "updated", "updated_fields": sorted(patch), "next": next_question(data)}, ensure_ascii=False, indent=2))


def profile_skip(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    if args.field not in QUESTION_MAP:
        raise SystemExit("field cannot be skipped")
    data = profile(root)
    skipped = set(data.get("skipped_fields", []))
    skipped.add(args.field)
    data["skipped_fields"] = sorted(skipped)
    data["updated_at"] = now_iso()
    write_json(profile_path(root), data)
    print(json.dumps({"status": "skipped", "next": next_question(data)}, ensure_ascii=False, indent=2))


def customers(root: Path) -> list[tuple[dict, Path]]:
    index = read_json(root / "indexes/customer-index.json", {"customers": []})
    output = []
    for entry in index.get("customers", []):
        customer_file = root / str(entry.get("workspace_path", "")) / "customer.json"
        if customer_file.is_file():
            output.append((read_json(customer_file, {}), customer_file.parent))
    return output


def resolve_customer(root: Path, raw: str) -> list[dict]:
    needle = raw.strip().casefold()
    if not needle:
        return []
    choices = []
    for item, _ in customers(root):
        names = [item.get("customer_id", ""), item.get("name", ""), *item.get("aliases", [])]
        if any(needle == str(name).strip().casefold() or needle in str(name).strip().casefold() for name in names):
            choices.append({"customer_id": item.get("customer_id"), "name": item.get("name"), "company_name": item.get("company_name", "")})
    return choices


def event_log(root: Path) -> Path:
    return root / "indexes/conversation-events.jsonl"


def load_events(root: Path) -> list[dict]:
    path = event_log(root)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                out.append(value)
        except json.JSONDecodeError:
            continue
    return out


def append_event(root: Path, event: dict) -> None:
    path = event_log(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def note_capture(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    matches = resolve_customer(root, args.customer)
    patch = read_json(Path(args.patch_file), {}) if args.patch_file else {}
    event = {
        "event_id": "cev-" + uuid.uuid4().hex[:12], "kind": "casual_note", "status": "pending_confirmation",
        "raw_note": args.text.strip(), "customer_query": args.customer.strip(), "candidate_customers": matches,
        "customer_id": args.customer_id or (matches[0]["customer_id"] if len(matches) == 1 else ""),
        "facts": args.facts.strip() if args.facts else "", "judgment": args.judgment.strip() if args.judgment else "",
        "recommended_action": args.recommended_action.strip() if args.recommended_action else "", "patch": patch,
        "created_at": now_iso(), "confirmed_at": "",
    }
    append_event(root, event)
    print(json.dumps({"status": event["status"], "event": event, "requires_customer_choice": not event["customer_id"]}, ensure_ascii=False, indent=2))


def note_confirm(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    events = load_events(root)
    found = next((item for item in events if item.get("event_id") == args.event_id), None)
    if not found:
        raise SystemExit("unknown event_id")
    customer_id = args.customer_id or found.get("customer_id")
    if not customer_id:
        raise SystemExit("customer confirmation is required")
    if found.get("status") != "pending_confirmation":
        raise SystemExit("event is already resolved")
    patch = found.get("patch") or {}
    if not isinstance(patch, dict) or not patch:
        raise SystemExit("confirmed event needs a non-empty customer patch")
    patch_path = root / "inbox/confirmed" / f"{found['event_id']}-patch.json"
    write_json(patch_path, patch)
    with contextlib.redirect_stdout(io.StringIO()):
        memory_store.update(SimpleNamespace(workspace=str(root), customer_id=customer_id, patch_file=str(patch_path)))
    found["status"] = "confirmed"
    found["customer_id"] = customer_id
    found["confirmed_at"] = now_iso()
    event_log(root).write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in events), encoding="utf-8")
    queue_generate(SimpleNamespace(workspace=str(root), quiet=True))
    print(json.dumps({"status": "confirmed_and_applied", "event_id": found["event_id"], "customer_id": customer_id}, ensure_ascii=False, indent=2))


def queue_path(root: Path) -> Path:
    return root / "indexes/suggestion-queue.json"


def suggestion_id(customer_id: str, category: str) -> str:
    return f"sug-{customer_id}-{category}"


def queue_generate(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    existing = read_json(queue_path(root), {"schema_version": 1, "suggestions": []})
    old = {item.get("suggestion_id"): item for item in existing.get("suggestions", [])}
    generated = []
    today = date.today()
    for customer, _ in customers(root):
        if customer.get("status") in {"won", "lost"}:
            continue
        cid, name = customer.get("customer_id", ""), customer.get("name", "客户")
        missing = [label for field, label in REQUIRED_CUSTOMER_FIELDS.items() if customer.get(field) in (None, "", [], {})]
        if len(missing) >= 3:
            generated.append({"suggestion_id": suggestion_id(cid, "profile-gap"), "customer_id": cid, "customer_name": name, "category": "资料待补", "priority": "high", "title": f"补齐{name}的关键资料", "reason": "、".join(missing[:4]) + "尚未确认，会影响下一步判断", "action": "下一次沟通优先补问一项最关键资料", "status": old.get(suggestion_id(cid, "profile-gap"), {}).get("status", "pending")})
        next_value = str(customer.get("next_followup_at") or "")[:10]
        try:
            next_date = date.fromisoformat(next_value) if next_value else None
        except ValueError:
            next_date = None
        if next_date and next_date < today:
            generated.append({"suggestion_id": suggestion_id(cid, "overdue"), "customer_id": cid, "customer_name": name, "category": "跟进节点", "priority": "high", "title": f"重新确认{name}的下一步", "reason": f"原定跟进时间为 {next_date.isoformat()}，尚未记录新的结果", "action": customer.get("next_action") or "先确认客户当前安排与下一步时间", "status": old.get(suggestion_id(cid, "overdue"), {}).get("status", "pending")})
        if customer.get("intent_level") == "high" and not customer.get("decision_chain"):
            generated.append({"suggestion_id": suggestion_id(cid, "decision-chain"), "customer_id": cid, "customer_name": name, "category": "决策关系", "priority": "medium", "title": f"确认{name}的决策关系", "reason": "客户意向较高，但关键参与人尚未明确", "action": "自然确认谁参与评估、谁拍板以及各自关注点", "status": old.get(suggestion_id(cid, "decision-chain"), {}).get("status", "pending")})
    for item in generated:
        item["updated_at"] = now_iso()
        item["created_at"] = old.get(item["suggestion_id"], {}).get("created_at", item["updated_at"])
    payload = {"schema_version": 1, "updated_at": now_iso(), "suggestions": generated}
    write_json(queue_path(root), payload)
    if not getattr(args, "quiet", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def queue_list(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    data = read_json(queue_path(root), {"schema_version": 1, "suggestions": []})
    suggestions = data.get("suggestions", [])
    if args.status:
        suggestions = [item for item in suggestions if item.get("status") == args.status]
    priority = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda item: (priority.get(item.get("priority"), 3), item.get("created_at", "")))
    print(json.dumps({"suggestions": suggestions[:args.limit]}, ensure_ascii=False, indent=2))


def queue_decide(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    data = read_json(queue_path(root), {"schema_version": 1, "suggestions": []})
    target = next((item for item in data.get("suggestions", []) if item.get("suggestion_id") == args.suggestion_id), None)
    if not target:
        raise SystemExit("unknown suggestion_id")
    target["status"] = args.decision
    target["decision_note"] = (args.note or "").strip()
    target["decided_at"] = now_iso()
    data["updated_at"] = now_iso()
    write_json(queue_path(root), data)
    append_event(root, {"event_id": "cev-" + uuid.uuid4().hex[:12], "kind": "suggestion_decision", "status": args.decision, "suggestion_id": args.suggestion_id, "customer_id": target.get("customer_id", ""), "created_at": now_iso()})
    print(json.dumps({"status": args.decision, "suggestion": target}, ensure_ascii=False, indent=2))


def calibrate(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    events = [item for item in load_events(root) if item.get("kind") == "suggestion_decision"]
    total = len(events)
    accepted = sum(1 for item in events if item.get("status") == "accepted")
    postponed = sum(1 for item in events if item.get("status") == "deferred")
    ignored = sum(1 for item in events if item.get("status") == "dismissed")
    result = {"period_days": args.days, "decision_count": total, "accepted": accepted, "deferred": postponed, "dismissed": ignored, "question": "这周的提醒和建议，偏多、合适，还是不够及时？"}
    if args.feedback:
        preferences = read_json(root / "config/coach-preferences.json", {"schema_version": 1})
        preferences.update({"last_feedback": args.feedback.strip(), "last_feedback_at": now_iso(), "updated_at": now_iso()})
        write_json(root / "config/coach-preferences.json", preferences)
        result["feedback_saved"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


def review_week(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    since = datetime.now().astimezone() - timedelta(days=7)
    recent = [item for item in load_events(root) if str(item.get("created_at", item.get("recorded_at", ""))) >= since.isoformat(timespec="seconds")]
    data = {"generated_at": now_iso(), "period": f"{since.date().isoformat()} 至 {date.today().isoformat()}", "customer_count": len(customers(root)), "events": recent, "next_focus": args.next_focus or "从待确认建议中选择一项高价值客户动作并完成闭环"}
    if args.save:
        path = root / "growth/reviews" / f"{date.today().isoformat()}-weekly-review.json"
        write_json(path, data)
        data["saved_to"] = str(path.relative_to(root))
    print(json.dumps(data, ensure_ascii=False, indent=2))


def prospect_index(root: Path) -> Path:
    return root / "prospects/index.json"


def prospect_plan(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    data = profile(root)
    industry = args.industry or data.get("industry") or "目标行业"
    region = args.region or data.get("region") or "目标地区"
    target = args.target or data.get("target_customer") or "目标客户"
    plan = {"industry": industry, "region": region, "target": target, "queries": [f"{region} {industry} 招标 采购 公告", f"{region} {industry} 项目 投资 扩产", f"{region} {industry} 企业 官网 新闻"], "allowed_sources": ["政府部门官网", "公共资源交易平台", "企业官网", "公开新闻页面"], "rule": "仅保存可公开访问且保留原文链接的候选线索；不得绕过登录、验证码、封禁或访问控制。"}
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def prospect_import(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    candidate = read_json(Path(args.candidate_file), {})
    required = ["company_name", "source_url", "match_reason"]
    missing = [key for key in required if not str(candidate.get(key, "")).strip()]
    if missing:
        raise SystemExit("candidate missing: " + ", ".join(missing))
    data = read_json(prospect_index(root), {"schema_version": 1, "candidates": []})
    candidate = {"prospect_id": "pro-" + uuid.uuid4().hex[:12], "status": "pending_confirmation", "discovered_at": now_iso(), **candidate}
    data.setdefault("candidates", []).append(candidate)
    data["updated_at"] = now_iso()
    write_json(prospect_index(root), data)
    print(json.dumps({"status": "pending_confirmation", "candidate": candidate}, ensure_ascii=False, indent=2))


def prospect_list(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    data = read_json(prospect_index(root), {"schema_version": 1, "candidates": []})
    values = data.get("candidates", [])
    if args.status:
        values = [item for item in values if item.get("status") == args.status]
    print(json.dumps({"candidates": values}, ensure_ascii=False, indent=2))


def prospect_confirm(args: argparse.Namespace) -> None:
    root = root_path(args.workspace)
    data = read_json(prospect_index(root), {"schema_version": 1, "candidates": []})
    item = next((value for value in data.get("candidates", []) if value.get("prospect_id") == args.prospect_id), None)
    if not item or item.get("status") != "pending_confirmation":
        raise SystemExit("candidate is unavailable for confirmation")
    with contextlib.redirect_stdout(io.StringIO()):
        ingest_store.create_customer(SimpleNamespace(workspace=str(root), name=args.name or item["company_name"], slug="", owner=args.owner or "", alias=[]))
    item["status"] = "converted"
    item["confirmed_at"] = now_iso()
    data["updated_at"] = now_iso()
    write_json(prospect_index(root), data)
    print(json.dumps({"status": "converted", "prospect_id": args.prospect_id}, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SA proactive coach state")
    sub = p.add_subparsers(dest="command", required=True)
    profile_cmd = sub.add_parser("profile")
    ps = profile_cmd.add_subparsers(dest="action", required=True)
    x = ps.add_parser("status"); x.add_argument("--workspace", required=True); x.set_defaults(func=profile_status)
    x = ps.add_parser("update"); x.add_argument("--workspace", required=True); x.add_argument("--field"); x.add_argument("--value"); x.add_argument("--patch-file"); x.set_defaults(func=profile_update)
    x = ps.add_parser("skip"); x.add_argument("--workspace", required=True); x.add_argument("--field", required=True); x.set_defaults(func=profile_skip)
    note = sub.add_parser("note")
    ns = note.add_subparsers(dest="action", required=True)
    x = ns.add_parser("capture"); x.add_argument("--workspace", required=True); x.add_argument("--text", required=True); x.add_argument("--customer", default=""); x.add_argument("--customer-id"); x.add_argument("--facts"); x.add_argument("--judgment"); x.add_argument("--recommended-action"); x.add_argument("--patch-file"); x.set_defaults(func=note_capture)
    x = ns.add_parser("confirm"); x.add_argument("--workspace", required=True); x.add_argument("--event-id", required=True); x.add_argument("--customer-id"); x.set_defaults(func=note_confirm)
    queue = sub.add_parser("suggestions")
    qs = queue.add_subparsers(dest="action", required=True)
    x = qs.add_parser("generate"); x.add_argument("--workspace", required=True); x.set_defaults(func=queue_generate)
    x = qs.add_parser("list"); x.add_argument("--workspace", required=True); x.add_argument("--status"); x.add_argument("--limit", type=int, default=3); x.set_defaults(func=queue_list)
    x = qs.add_parser("decide"); x.add_argument("--workspace", required=True); x.add_argument("--suggestion-id", required=True); x.add_argument("--decision", choices=["accepted", "deferred", "dismissed"], required=True); x.add_argument("--note"); x.set_defaults(func=queue_decide)
    x = sub.add_parser("calibrate"); x.add_argument("--workspace", required=True); x.add_argument("--days", type=int, default=7); x.add_argument("--feedback"); x.set_defaults(func=calibrate)
    x = sub.add_parser("review-week"); x.add_argument("--workspace", required=True); x.add_argument("--next-focus"); x.add_argument("--save", action="store_true"); x.set_defaults(func=review_week)
    prospects = sub.add_parser("prospects")
    prs = prospects.add_subparsers(dest="action", required=True)
    x = prs.add_parser("plan"); x.add_argument("--workspace", required=True); x.add_argument("--industry"); x.add_argument("--region"); x.add_argument("--target"); x.set_defaults(func=prospect_plan)
    x = prs.add_parser("import"); x.add_argument("--workspace", required=True); x.add_argument("--candidate-file", required=True); x.set_defaults(func=prospect_import)
    x = prs.add_parser("list"); x.add_argument("--workspace", required=True); x.add_argument("--status"); x.set_defaults(func=prospect_list)
    x = prs.add_parser("confirm"); x.add_argument("--workspace", required=True); x.add_argument("--prospect-id", required=True); x.add_argument("--name"); x.add_argument("--owner"); x.set_defaults(func=prospect_confirm)
    return p


def main() -> int:
    args = parser().parse_args()
    if args.command == "profile" and args.action == "update" and not args.patch_file and not args.field:
        raise SystemExit("profile update requires --field/--value or --patch-file")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
