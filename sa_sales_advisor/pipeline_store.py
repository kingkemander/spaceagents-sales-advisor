#!/usr/bin/env python3
"""Render lead, pipeline, forecast, and risk views from customer master data."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


STAGES = ["初步接触", "需求确认", "方案演示", "报价谈判", "赢单", "输单"]
OPEN_STAGES = STAGES[:4]
DEFAULT_PROBABILITY = {"初步接触": 10, "需求确认": 30, "方案演示": 50, "报价谈判": 75, "赢单": 100, "输单": 0}


def load_customers(root: Path) -> list[dict]:
    customers = []
    for path in sorted((root / "customers").glob("*/customer.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        item["_path"] = str(path.relative_to(root))
        customers.append(item)
    return customers


def parse_date(value) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def pipeline_stage(customer: dict) -> str:
    configured = customer.get("pipeline_stage")
    if configured in STAGES:
        return configured
    if customer.get("status") == "won":
        return "赢单"
    if customer.get("status") == "lost":
        return "输单"
    text = str(customer.get("stage") or "")
    rules = [
        ("报价谈判", ("报价", "谈判", "付款", "合同", "议价")),
        ("方案演示", ("方案", "演示", "看楼", "试驾", "考察")),
        ("需求确认", ("需求", "深度洽谈", "意向")),
    ]
    for stage, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return stage
    return "初步接触"


def number(value) -> Optional[float]:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def probability(customer: dict, stage: str) -> int:
    value = customer.get("win_probability")
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
        return value
    return DEFAULT_PROBABILITY[stage]


def primary_contact(customer: dict) -> dict:
    contacts = [item for item in customer.get("contacts", []) if isinstance(item, dict)]
    return contacts[0] if contacts else {}


def text(value, fallback="未确认") -> str:
    if value in (None, "", [], {}):
        return fallback
    if isinstance(value, list):
        return "；".join(str(item) for item in value if str(item).strip()) or fallback
    return str(value).replace("|", "｜").replace("\n", " ").strip() or fallback


def money(value: Optional[float], currency: str = "CNY") -> str:
    if value is None:
        return "未确认"
    return f"{value:,.0f} {currency}"


def stage_reached(customer: dict, stage: str) -> bool:
    current = pipeline_stage(customer)
    if current in OPEN_STAGES and stage in OPEN_STAGES:
        return OPEN_STAGES.index(current) >= OPEN_STAGES.index(stage)
    if current == "赢单" and stage in [*OPEN_STAGES, "赢单"]:
        return True
    history = {item.get("stage") for item in customer.get("stage_history", []) if isinstance(item, dict)}
    return stage in history


def risk_items(customer: dict, today: date) -> list[str]:
    raw_risks = customer.get("risks", [])
    if isinstance(raw_risks, str):
        raw_risks = [raw_risks]
    risks = [text(item, "") for item in raw_risks if text(item, "")]
    followup = parse_date(customer.get("next_followup_at"))
    close_date = parse_date(customer.get("expected_close_date"))
    if followup and followup < today and pipeline_stage(customer) not in {"赢单", "输单"}:
        risks.append(f"跟进已逾期 {max(1, (today - followup).days)} 天")
    if close_date and close_date <= today + timedelta(days=14) and not customer.get("next_action"):
        risks.append("预计成交日期临近，但下一步动作尚未确认")
    return list(dict.fromkeys(risks))


def render(root: Path, report_date: date) -> dict:
    customers = load_customers(root)
    pipeline_dir = root / "pipeline"
    reports_dir = pipeline_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    lead_lines = [
        "# 销售线索",
        "",
        f"> 更新时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "| 客户/公司 | 联系人 | 联系方式 | 来源 | 行业 | 意向度 | 资料缺口 |",
        "|---|---|---|---|---|---|---|",
    ]
    for customer in customers:
        if pipeline_stage(customer) not in {"初步接触", "需求确认"} or customer.get("status") in {"won", "lost"}:
            continue
        contact = primary_contact(customer)
        missing = []
        for label, value in [
            ("公司", customer.get("company_name")), ("联系人", contact.get("name") or customer.get("name")),
            ("联系方式", contact.get("phone") or contact.get("email") or contact.get("wechat")),
            ("来源", customer.get("source_channel")), ("行业", customer.get("industry")),
        ]:
            if value in (None, "", [], {}):
                missing.append(label)
        lead_lines.append(
            "| " + " | ".join([
                text(customer.get("company_name") or customer.get("name")),
                text(contact.get("name") or customer.get("name")),
                text(contact.get("phone") or contact.get("email") or contact.get("wechat")),
                text(customer.get("source_channel")), text(customer.get("industry")),
                text(customer.get("intent_level"), "unknown"), "、".join(missing) or "无明显缺口",
            ]) + " |"
        )

    pipeline_lines = [
        "# 销售漏斗",
        "",
        f"> 数据日期：{report_date.isoformat()}｜主数据来自各客户 customer.json",
        "",
        "| 客户/机会 | 公司 | 阶段 | 金额 | 成交概率 | 预计成交 | 上次跟进 | 下一步动作 |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    stage_counts = {stage: 0 for stage in STAGES}
    stage_amounts = {stage: 0.0 for stage in STAGES}
    total_open = 0.0
    weighted = 0.0
    overdue = []
    risk_opportunities = []
    for customer in customers:
        stage = pipeline_stage(customer)
        amount = number(customer.get("opportunity_amount"))
        chance = probability(customer, stage)
        currency = text(customer.get("currency"), "CNY")
        stage_counts[stage] += 1
        if amount is not None:
            stage_amounts[stage] += amount
            if stage in OPEN_STAGES:
                total_open += amount
                weighted += amount * chance / 100
        risks = risk_items(customer, report_date)
        if any("逾期" in item for item in risks):
            overdue.append(customer)
        if risks:
            risk_opportunities.append((customer, risks))
        pipeline_lines.append(
            "| " + " | ".join([
                text(customer.get("name")), text(customer.get("company_name")), stage,
                money(amount, currency), f"{chance}%", text(customer.get("expected_close_date")),
                text(customer.get("last_contact_at")), text(customer.get("next_action")),
            ]) + " |"
        )

    conversion_lines = []
    for previous, following in zip(OPEN_STAGES, OPEN_STAGES[1:]):
        base = sum(1 for item in customers if stage_reached(item, previous))
        converted = sum(1 for item in customers if stage_reached(item, following))
        conversion_lines.append((f"{previous} → {following}", converted, base, round(converted / base * 100, 1) if base else None))
    closed = stage_counts["赢单"] + stage_counts["输单"]
    win_rate = round(stage_counts["赢单"] / closed * 100, 1) if closed else None

    report_lines = [
        f"# 销售漏斗报告｜{report_date.isoformat()}", "", "## 漏斗概览", "",
        "| 阶段 | 机会数 | 金额汇总 |", "|---|---:|---:|",
    ]
    report_lines.extend(f"| {stage} | {stage_counts[stage]} | {money(stage_amounts[stage])} |" for stage in STAGES)
    report_lines.extend([
        "", "## 收入预测", "", f"- 在途机会金额：{money(total_open)}",
        f"- 加权预计收入：{money(weighted)}", f"- 已赢单金额：{money(stage_amounts['赢单'])}",
        "", "## 阶段转化", "", "| 转化路径 | 已到达下一阶段 | 基础机会数 | 转化率 |", "|---|---:|---:|---:|",
    ])
    report_lines.extend(
        f"| {label} | {converted} | {base} | {rate if rate is not None else '样本不足'}{'%' if rate is not None else ''} |"
        for label, converted, base, rate in conversion_lines
    )
    report_lines.append(f"| 赢单率 | {stage_counts['赢单']} | {closed} | {win_rate if win_rate is not None else '样本不足'}{'%' if win_rate is not None else ''} |")
    report_lines.extend(["", "## 风险机会", ""])
    if risk_opportunities:
        for customer, risks in risk_opportunities:
            report_lines.append(f"- **{text(customer.get('name'))}**：{'；'.join(risks)}；下一步：{text(customer.get('next_action'))}")
    else:
        report_lines.append("- 当前没有已识别的高风险机会。")
    report_lines.extend(["", "## 数据质量提醒", ""])
    missing_amount = sum(1 for item in customers if pipeline_stage(item) in OPEN_STAGES and number(item.get("opportunity_amount")) is None)
    missing_close = sum(1 for item in customers if pipeline_stage(item) in OPEN_STAGES and not item.get("expected_close_date"))
    report_lines.append(f"- {missing_amount} 个在途机会缺少金额；{missing_close} 个在途机会缺少预计成交日期。")

    (pipeline_dir / "leads.md").write_text("\n".join(lead_lines) + "\n", encoding="utf-8")
    (pipeline_dir / "pipeline.md").write_text("\n".join(pipeline_lines) + "\n", encoding="utf-8")
    report_path = reports_dir / f"{report_date.isoformat()}.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return {
        "status": "rendered", "customers": len(customers), "stage_counts": stage_counts,
        "open_amount": round(total_open, 2), "weighted_revenue": round(weighted, 2),
        "overdue": len(overdue), "report": str(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--date", help="YYYY-MM-DD; defaults to local today")
    args = parser.parse_args()
    root = Path(args.workspace).expanduser().resolve()
    if not (root / "indexes/customer-index.json").is_file():
        raise SystemExit(f"workspace is not initialized: {root}")
    report_date = date.fromisoformat(args.date) if args.date else date.today()
    print(json.dumps(render(root, report_date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
