#!/usr/bin/env python3
"""Render a standalone daily sales dashboard from local customer JSON files."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from presentation import clean_public_text, clean_public_value
from pipeline_store import OPEN_STAGES, STAGES, number, pipeline_stage, probability


def missing(value) -> bool:
    if value in (None, "", [], {}):
        return True
    text = str(value).strip()
    return not text or text.startswith(("未确认", "待确认", "未知", "暂无"))


def primary_contact(customer: dict) -> dict:
    contacts = [item for item in customer.get("contacts", []) if isinstance(item, dict)]
    name = str(customer.get("name") or "").strip()
    for item in contacts:
        if name and str(item.get("name") or "").strip() == name:
            return item
    for item in contacts:
        if "销售" not in str(item.get("role") or ""):
            return item
    return {}


def customer_information_gaps(customer: dict) -> tuple[list[dict], int]:
    contact = primary_contact(customer)
    company = customer.get("company_name") or contact.get("org")
    job_title = customer.get("job_title") or contact.get("title")
    checks = [
        ("来源渠道", customer.get("source_channel"), "帮助判断客户初次接触背景", "方便问一下，您最初是从哪里了解到我们的？"),
        ("公司全称", company, "便于匹配行业、规模和真实使用场景", "方便留一下您的公司全称吗？我后面准备资料会更准确。"),
        ("客户职位", job_title, "判断关注重点和内部决策角色", "您在这个项目里主要负责使用、选址，还是最终决策？"),
        ("所属行业", customer.get("industry"), "便于准备更贴近业务的案例", "您公司目前主要做哪一块业务？"),
        ("核心需求", customer.get("needs"), "避免只围绕产品参数介绍", "您这次最想优先解决的一个问题是什么？"),
        ("预算范围", customer.get("budget"), "帮助筛选真正可落地的方案", "您希望我们优先按哪个投入区间准备方案？"),
        ("项目周期", customer.get("timeline"), "决定跟进节奏和资料准备顺序", "这件事大概希望在什么时间节点前确定？"),
        ("决策关系", customer.get("decision_chain"), "避免遗漏真正参与判断的人", "下一步还需要哪位同事一起了解或确认？"),
    ]
    gaps = [
        {"field": label, "why": why, "question": question}
        for label, value, why, question in checks
        if missing(value)
    ]
    completeness = round((len(checks) - len(gaps)) / len(checks) * 100)
    return gaps, completeness


def read_markdown_profile(path: Path) -> tuple[dict, dict]:
    if not path.is_file():
        return {}, {}
    lines = path.read_text(encoding="utf-8").splitlines()
    meta = {}
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                value = value.strip().strip('"').strip("'")
                meta[key.strip()] = int(value) if value.isdigit() else value
    sections, heading, collected = {}, None, []
    for line in lines:
        if line.startswith("## "):
            if heading is not None:
                sections[heading] = clean_public_text(" ".join(collected))
            heading, collected = line[3:].strip(), []
        elif heading and line.strip() and not line.startswith("#"):
            collected.append(line.strip().lstrip("- ").strip())
    if heading is not None:
        sections[heading] = clean_public_text(" ".join(collected))
    return meta, sections


def sales_voice_profile(root: Path) -> dict:
    meta, sections = read_markdown_profile(root / "config/sales-soul.md")
    messages = int(meta.get("sample_messages") or 0)
    meetings = int(meta.get("sample_meetings") or 0)
    evidence_units = messages + meetings * 5
    maturity = min(100, round(evidence_units / 40 * 100))
    if evidence_units == 0:
        level, next_step = "待建立", "上传本人发送的聊天样本或可区分说话人的会议纪要"
    elif messages < 20 and meetings < 3:
        level, next_step = "临时风格", "继续补充至少 20 条本人消息或 3 次会议表达"
    elif evidence_units < 40:
        level, next_step = "基础画像", "补充异议处理和关键推进场景，让表达更稳定"
    else:
        level, next_step = "稳定画像", "新沟通后按需确认有效表达，持续微调而不是整体重写"
    fields = ["整体气质", "称呼习惯", "语言特征", "跟进习惯", "异议处理", "禁止表达"]
    return {
        "level": level,
        "maturity": maturity,
        "sample_messages": messages,
        "sample_meetings": meetings,
        "updated_at": meta.get("updated_at") or "",
        "next_step": next_step,
        "sections": {field: sections.get(field) or "尚未形成，等待本人表达样本" for field in fields},
    }


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
    stage_counts = {stage: 0 for stage in STAGES}
    stage_amounts = {stage: 0.0 for stage in STAGES}
    open_amount = 0.0
    weighted_revenue = 0.0
    for path in sorted((root / "customers").glob("*/customer.json")):
        customer = json.loads(path.read_text(encoding="utf-8"))
        bucket, score = classify(customer, today)
        gaps, completeness = customer_information_gaps(customer)
        standard_stage = pipeline_stage(customer)
        amount = number(customer.get("opportunity_amount"))
        chance = probability(customer, standard_stage)
        stage_counts[standard_stage] += 1
        if amount is not None:
            stage_amounts[standard_stage] += amount
            if standard_stage in OPEN_STAGES:
                open_amount += amount
                weighted_revenue += amount * chance / 100
        customer_view = {
            "customer_id": customer.get("customer_id"),
            "name": customer.get("name"),
            "status": customer.get("status"),
            "stage": clean_public_text(customer.get("stage"), "阶段待确认"),
            "pipeline_stage": standard_stage,
            "opportunity_amount": amount,
            "currency": customer.get("currency") or "CNY",
            "expected_close_date": customer.get("expected_close_date"),
            "win_probability": chance,
            "intent_level": customer.get("intent_level"),
            "last_contact_at": customer.get("last_contact_at"),
            "next_followup_at": customer.get("next_followup_at"),
            "latest_update": clean_public_text(customer.get("latest_update"), "暂无新的业务进展"),
            "followup_reason": clean_public_text(customer.get("followup_reason"), "按既定节奏持续跟进"),
            "next_action": clean_public_text(customer.get("next_action"), "确认下一次沟通安排"),
            "reply_suggestion": clean_public_text(customer.get("reply_suggestion")),
            "risks": clean_public_value(customer.get("risks", [])),
            "information_gaps": clean_public_value(gaps),
            "information_completeness": completeness,
            "bucket": bucket,
            "priority": score,
        }
        customers.append(customer_view)
    customers.sort(key=lambda x: (-x["priority"], x.get("next_followup_at") or "9999"))
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    data = {
        "schema_version": 1,
        "generated_at": generated_at,
        "date": today.isoformat(),
        "customers": customers,
        "sales_voice": sales_voice_profile(root),
        "pipeline": {
            "stages": [{"name": stage, "count": stage_counts[stage], "amount": round(stage_amounts[stage], 2)} for stage in STAGES],
            "open_amount": round(open_amount, 2),
            "weighted_revenue": round(weighted_revenue, 2),
            "won_amount": round(stage_amounts["赢单"], 2),
            "risk_count": sum(1 for item in customers if item.get("risks") or item.get("bucket") in {"overdue", "risk"}),
        },
    }
    dashboard_dir = root / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    (dashboard_dir / "dashboard-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    template = Path(__file__).resolve().parent / "templates/dashboard-template.html"
    html = template.read_text(encoding="utf-8")
    html = html.replace("__DASHBOARD_DATA_JSON__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    html = html.replace("__GENERATED_AT__", generated_at)
    (dashboard_dir / "index.html").write_text(html, encoding="utf-8")
    counts = {key: sum(1 for x in customers if x["bucket"] == key) for key in ["must", "suggested", "overdue", "risk", "waiting"]}
    print(json.dumps({"status": "rendered", "dashboard": str(dashboard_dir / "index.html"), "customers": len(customers), "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
