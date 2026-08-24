#!/usr/bin/env python3
"""Store, verify and confirm public company intelligence for sales customers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from company_radar_confirm import confirm_record


SOURCE_LEVELS = {"official_original", "official_aggregate", "company_official", "authoritative_media", "search_lead"}
OFFICIAL_HOST_SUFFIXES = (
    "ccgp.gov.cn", "ggzy.gov.cn", "cebpubservice.com", "creditchina.gov.cn",
    "gsxt.gov.cn", "samr.gov.cn", "gov.cn", "court.gov.cn", "cnipa.gov.cn",
)
TOPIC_GROUPS = {
    "招投标": "招标 OR 采购 OR 采购意向 OR 资格预审 OR 候选人公示 OR 中标 OR 成交 OR 合同公告",
    "项目建设": "项目备案 OR 立项 OR 环评 OR 能评 OR 施工许可 OR 土地 OR 产权交易 OR 开工 OR 投产",
    "经营变化": "工商变更 OR 行政许可 OR 行政处罚 OR 经营异常 OR 严重失信 OR 扩产 OR 搬迁",
    "资本动态": "融资 OR 投资 OR 并购 OR 股权 OR 上市 OR 债券",
    "人才需求": "招聘 OR 校招 OR 社招 OR 新增岗位",
    "司法风险": "诉讼 OR 开庭 OR 判决 OR 执行 OR 破产 OR 被执行人",
    "创新动态": "专利 OR 商标 OR 软件著作权 OR 新产品 OR 战略合作 OR 官方新闻",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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


def normalize_code(value: str) -> str:
    code = re.sub(r"\s+", "", value or "").upper()
    if code and not re.fullmatch(r"[0-9A-Z]{18}", code):
        raise SystemExit("unified social credit code must contain exactly 18 letters or digits")
    return code


def normalize_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, val) for key, val in query if not key.lower().startswith(("utm_", "spm"))]
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, urllib.parse.urlencode(query), ""))


def identity_path(root: Path) -> Path:
    return root / "indexes/company-identity-index.json"


def evidence_path(root: Path) -> Path:
    return root / "indexes/company-intelligence.jsonl"


def load_identities(root: Path) -> dict:
    return read_json(identity_path(root), {"schema_version": 1, "updated_at": "", "companies": {}})


def register(args: argparse.Namespace) -> None:
    root = Path(args.workspace).expanduser().resolve()
    legal_name = args.legal_name.strip()
    credit_code = normalize_code(args.credit_code)
    if not legal_name and not credit_code:
        raise SystemExit("legal-name or credit-code is required")
    index = load_identities(root)
    record = {
        "customer_id": args.customer_id,
        "legal_name": legal_name,
        "credit_code": credit_code,
        "region": args.region.strip(),
        "former_names": sorted(set(args.former_name)),
        "brands": sorted(set(args.brand)),
        "related_companies": sorted(set(args.related_company)),
        "updated_at": now_iso(),
    }
    index["companies"][args.customer_id] = record
    index["updated_at"] = record["updated_at"]
    write_json(identity_path(root), index)
    print(json.dumps({"status": "registered", "identity": record, "ready_for_verified_monitoring": bool(credit_code or (legal_name and record["region"]))}, ensure_ascii=False, indent=2))


def search_plan(args: argparse.Namespace) -> None:
    root = Path(args.workspace).expanduser().resolve()
    identity = load_identities(root).get("companies", {}).get(args.customer_id)
    if not identity:
        raise SystemExit(f"company identity is not registered for customer: {args.customer_id}")
    term = identity.get("credit_code") or f'"{identity.get("legal_name", "")}"'
    queries = [{"topic": topic, "query": f"{term} ({keywords})"} for topic, keywords in TOPIC_GROUPS.items()]
    legal_name = identity.get("legal_name", "")
    if legal_name:
        queries.extend([
            {"topic": "政府采购", "query": f'"{legal_name}" site:ccgp.gov.cn'},
            {"topic": "公共资源交易", "query": f'"{legal_name}" site:ggzy.gov.cn'},
            {"topic": "政府公开信息", "query": f'"{legal_name}" site:gov.cn'},
            {"topic": "企业官方动态", "query": f'"{legal_name}" 官网 OR 官方'},
        ])
    print(json.dumps({"status": "ok", "identity": identity, "max_results": args.max_results, "queries": queries}, ensure_ascii=False, indent=2))


def source_level(record: dict) -> str:
    explicit = str(record.get("source_level", ""))
    if explicit in SOURCE_LEVELS:
        return explicit
    host = urllib.parse.urlsplit(str(record.get("source_url", ""))).hostname or ""
    if any(host == suffix or host.endswith("." + suffix) for suffix in OFFICIAL_HOST_SUFFIXES):
        return "official_original"
    return "search_lead"


def verify(identity: dict, record: dict) -> tuple[str, str]:
    try:
        supplied_code = normalize_code(str(record.get("credit_code", "")))
    except SystemExit:
        return "rejected", "统一社会信用代码格式无效"
    expected_code = identity.get("credit_code", "")
    if supplied_code and expected_code and supplied_code != expected_code:
        return "rejected", "统一社会信用代码与客户企业不一致"
    accessible = record.get("original_accessible") is True
    published = bool(str(record.get("published_at", "")).strip())
    level = source_level(record)
    if not accessible or not published or level == "search_lead":
        return "pending", "缺少可访问原文、发布日期或仅有搜索线索"
    if supplied_code and expected_code and supplied_code == expected_code:
        return "verified", "统一社会信用代码精确匹配且原文可核验"
    expected_name = identity.get("legal_name", "").strip()
    supplied_name = str(record.get("company_name", "")).strip()
    expected_region = identity.get("region", "").strip()
    supplied_region = str(record.get("region", "")).strip()
    if expected_name and supplied_name == expected_name and expected_region and supplied_region == expected_region:
        return "verified", "企业法定全称和注册地区匹配且原文可核验"
    return "pending", "企业主体匹配信息不足"


def existing_keys(path: Path) -> set[str]:
    keys = set()
    if not path.is_file():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            keys.add(str(json.loads(line).get("dedup_key", "")))
        except ValueError:
            continue
    return keys


def import_records(args: argparse.Namespace) -> None:
    root = Path(args.workspace).expanduser().resolve()
    identity = load_identities(root).get("companies", {}).get(args.customer_id)
    if not identity:
        raise SystemExit(f"company identity is not registered for customer: {args.customer_id}")
    payload = read_json(Path(args.input_file).expanduser(), None)
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise SystemExit("input JSON must be a list or an object containing records")
    path = evidence_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    known = existing_keys(path)
    saved = []
    with path.open("a", encoding="utf-8") as handle:
        for raw in records:
            if not isinstance(raw, dict):
                continue
            try:
                url = normalize_url(str(raw.get("source_url", "")))
            except ValueError:
                continue
            key_material = str(raw.get("external_id") or url or (str(raw.get("title", "")) + str(raw.get("published_at", ""))))
            dedup_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
            if dedup_key in known:
                continue
            status, reason = verify(identity, raw)
            record = {
                "schema_version": 1,
                "evidence_id": "ci-" + dedup_key[:16],
                "dedup_key": dedup_key,
                "customer_id": args.customer_id,
                "title": str(raw.get("title", "")).strip(),
                "event_type": str(raw.get("event_type", "其他")).strip(),
                "company_role": str(raw.get("company_role", "待确认")).strip(),
                "summary": str(raw.get("summary", "")).strip(),
                "amount": raw.get("amount"),
                "region": str(raw.get("region", "")).strip(),
                "published_at": str(raw.get("published_at", "")).strip(),
                "source_name": str(raw.get("source_name", "")).strip(),
                "source_url": url,
                "source_level": source_level(raw),
                "verification_status": status,
                "verification_reason": reason,
                "collected_at": now_iso(),
                "confirmed_at": None,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            known.add(dedup_key)
            saved.append(record)
    counts = {state: sum(item["verification_status"] == state for item in saved) for state in ["verified", "pending", "rejected"]}
    print(json.dumps({"status": "imported", "saved": len(saved), "counts": counts, "records": saved}, ensure_ascii=False, indent=2))


def list_records(args: argparse.Namespace) -> None:
    root = Path(args.workspace).expanduser().resolve()
    records = []
    if evidence_path(root).is_file():
        for line in evidence_path(root).read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if item.get("customer_id") == args.customer_id and (not args.status or item.get("verification_status") == args.status):
                records.append(item)
    records.sort(key=lambda item: (item.get("published_at", ""), item.get("collected_at", "")), reverse=True)
    print(json.dumps({"status": "ok", "records": records}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    identity = sub.add_parser("register")
    identity.add_argument("--workspace", required=True)
    identity.add_argument("--customer-id", required=True)
    identity.add_argument("--legal-name", default="")
    identity.add_argument("--credit-code", default="")
    identity.add_argument("--region", default="")
    identity.add_argument("--former-name", action="append", default=[])
    identity.add_argument("--brand", action="append", default=[])
    identity.add_argument("--related-company", action="append", default=[])
    identity.set_defaults(func=register)
    plan = sub.add_parser("plan")
    plan.add_argument("--workspace", required=True)
    plan.add_argument("--customer-id", required=True)
    plan.add_argument("--max-results", type=int, choices=range(1, 101), default=100)
    plan.set_defaults(func=search_plan)
    ingest = sub.add_parser("import")
    ingest.add_argument("--workspace", required=True)
    ingest.add_argument("--customer-id", required=True)
    ingest.add_argument("--input-file", required=True)
    ingest.set_defaults(func=import_records)
    listing = sub.add_parser("list")
    listing.add_argument("--workspace", required=True)
    listing.add_argument("--customer-id", required=True)
    listing.add_argument("--status", choices=["verified", "pending", "rejected"])
    listing.set_defaults(func=list_records)
    confirmation = sub.add_parser("confirm")
    confirmation.add_argument("--workspace", required=True)
    confirmation.add_argument("--customer-id", required=True)
    confirmation.add_argument("--evidence-id", required=True)
    confirmation.set_defaults(func=confirm_record)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
