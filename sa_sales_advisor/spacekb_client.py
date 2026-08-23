#!/usr/bin/env python3
"""Local SpaceKB configuration, retrieval, upload, and private daily sync."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import mimetypes
import os
import re
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen


DEFAULT_BASE_URL = "http://123.56.18.172:30000"
DEFAULT_KNOWLEDGE_BASE_ID = "ecec0261-5cfc-4aae-af76-605c98b3fd59"
DEFAULT_DOMAIN = "__private__"
USER_AGENT = "SpaceAgents-Sales-Advisor/0.12.0"
MAX_LIST_ITEMS = 100
MAX_CHUNK_ITEMS = 20
MAX_CHUNK_CHARS = 2000
MAX_SEARCH_DOCUMENTS = 50
MAX_SEARCH_RESULTS = 12
MAX_SEARCH_CHARS = 2000


class SpaceKBError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def config_path(workspace: Path) -> Path:
    return workspace / ".spaceagents/plugins/sa-sales-advisor/user-config/spacekb.json"


def secret_path(workspace: Path) -> Path:
    return workspace / ".spaceagents/secrets/sa-sales-advisor-spacekb.key"


def atomic_write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    if mode is not None:
        os.chmod(temp, mode)
    temp.replace(path)
    if mode is not None:
        os.chmod(path, mode)


def ensure_safe_url(base_url: str, allow_insecure_http: bool) -> str:
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SpaceKBError("SpaceKB Base URL 无效")
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and parsed.hostname not in local_hosts and not allow_insecure_http:
        raise SpaceKBError(
            "当前 SpaceKB 地址使用公网 HTTP。为避免 API Key 明文传输，请改用 HTTPS；"
            "仅在明确接受测试风险时使用 --allow-insecure-http。"
        )
    return normalized


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpaceKBError("SpaceKB 尚未配置，请先运行 knowledge configure") from exc
    except json.JSONDecodeError as exc:
        raise SpaceKBError(f"SpaceKB 本地配置损坏：{path}") from exc
    if not isinstance(value, dict):
        raise SpaceKBError("SpaceKB 本地配置格式不正确")
    return value


def load_credentials(workspace: Path) -> tuple[dict, str]:
    config = read_json(config_path(workspace))
    key_file = secret_path(workspace)
    try:
        api_key = key_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise SpaceKBError("SpaceKB API Key 尚未保存在本机") from exc
    if not api_key:
        raise SpaceKBError("SpaceKB API Key 为空")
    config["base_url"] = ensure_safe_url(
        str(config.get("base_url", "")), bool(config.get("allow_insecure_http", False))
    )
    return config, api_key


class SpaceKBClient:
    def __init__(self, base_url: str, knowledge_base_id: str, api_key: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.kb_id = knowledge_base_id
        self.api_key = api_key
        self.timeout = timeout

    @property
    def root(self) -> str:
        return f"{self.base_url}/api/knowledge-bases/{quote(self.kb_id, safe='')}"

    def request_json(self, method: str, url: str, body: bytes | None = None, headers: dict | None = None):
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        request_headers.update(headers or {})
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            hostname = urlparse(url).hostname
            if hostname in {"localhost", "127.0.0.1", "::1"}:
                response_context = build_opener(ProxyHandler({})).open(request, timeout=self.timeout)
            else:
                response_context = urlopen(request, timeout=self.timeout)
            with response_context as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise SpaceKBError(f"SpaceKB 请求失败（HTTP {exc.code}）：{detail}") from exc
        except URLError as exc:
            raise SpaceKBError(f"无法连接 SpaceKB：{exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SpaceKBError("SpaceKB 返回了无法解析的响应") from exc

    def info(self):
        return self.request_json("GET", self.root)

    def list_documents(self, domain: str | None = None):
        url = f"{self.root}/documents"
        if domain:
            url += "?" + urlencode({"domain": domain})
        return self.request_json("GET", url)

    def chunks(self, doc_id: str):
        return self.request_json("GET", f"{self.root}/documents/{quote(doc_id, safe='')}/chunks")

    def upload(self, file_path: Path, domain: str):
        boundary = "----SpaceAgents" + uuid.uuid4().hex
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        parts = []
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"target_domain\"\r\n\r\n{domain}\r\n".encode()
        )
        parts.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"{file_path.name}\"\r\nContent-Type: {mime}\r\n\r\n"
            ).encode("utf-8")
        )
        parts.append(file_path.read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        return self.request_json(
            "POST",
            f"{self.root}/documents",
            b"".join(parts),
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )


def client_for(workspace: Path) -> tuple[SpaceKBClient, dict]:
    config, api_key = load_credentials(workspace)
    client = SpaceKBClient(config["base_url"], config["knowledge_base_id"], api_key)
    return client, config


def configure(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    base_url = ensure_safe_url(args.base_url, args.allow_insecure_http)
    if args.api_key_stdin:
        api_key = sys.stdin.readline().strip()
    elif args.api_key_env:
        api_key = os.environ.get(args.api_key_env, "").strip()
    else:
        api_key = getpass.getpass("SpaceKB API Key（输入不会显示）: ").strip()
    if not api_key:
        raise SpaceKBError("未输入 SpaceKB API Key")
    client = SpaceKBClient(base_url, args.knowledge_base_id, api_key)
    if not args.skip_test:
        client.info()
    config = {
        "schema_version": 1,
        "base_url": base_url,
        "knowledge_base_id": args.knowledge_base_id,
        "default_domain": args.default_domain,
        "allow_insecure_http": bool(args.allow_insecure_http),
        "configured_at": now_iso(),
    }
    atomic_write(config_path(workspace), json.dumps(config, ensure_ascii=False, indent=2) + "\n", 0o600)
    ignore_file = secret_path(workspace).parent / ".gitignore"
    if not ignore_file.exists():
        atomic_write(ignore_file, "*\n!.gitignore\n", 0o600)
    atomic_write(secret_path(workspace), api_key + "\n", 0o600)
    print(
        json.dumps(
            {
                "status": "configured",
                "base_url": base_url,
                "knowledge_base_id": args.knowledge_base_id,
                "default_domain": args.default_domain,
                "api_key": "saved-locally-redacted",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def status(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    config, _ = load_credentials(workspace)
    result = {**config, "api_key": "configured", "secret_path": "local-private-file"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def list_documents(args: argparse.Namespace) -> int:
    client, config = client_for(Path(args.workspace).expanduser().resolve())
    value = client.list_documents(args.domain or config.get("default_domain"))
    documents = value.get("documents", value.get("items", [])) if isinstance(value, dict) else value
    if not isinstance(documents, list):
        raise SpaceKBError("SpaceKB 文档列表格式不符合预期")
    offset = max(0, args.offset)
    limit = max(1, min(args.limit, MAX_LIST_ITEMS))
    selected = []
    for document in documents[offset : offset + limit]:
        if not isinstance(document, dict):
            continue
        selected.append(
            {
                key: str(document[key])[:500]
                for key in ("id", "filename", "name", "status", "domain", "created_at", "updated_at")
                if document.get(key) is not None
            }
        )
    print(
        json.dumps(
            {
                "documents": selected,
                "pagination": {
                    "offset": offset,
                    "limit": limit,
                    "returned": len(selected),
                    "total": len(documents),
                    "has_more": offset + limit < len(documents),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def show_chunks(args: argparse.Namespace) -> int:
    client, _ = client_for(Path(args.workspace).expanduser().resolve())
    value = client.chunks(args.doc_id)
    chunks = value.get("chunks", value.get("items", [])) if isinstance(value, dict) else value
    if not isinstance(chunks, list):
        raise SpaceKBError("SpaceKB 文档分块格式不符合预期")
    offset = max(0, args.offset)
    limit = max(1, min(args.limit, MAX_CHUNK_ITEMS))
    max_chars = max(100, min(args.max_chars, MAX_CHUNK_CHARS))
    selected = []
    for chunk in chunks[offset : offset + limit]:
        if not isinstance(chunk, dict):
            continue
        content = str(chunk.get("content", ""))
        selected.append(
            {
                "id": chunk.get("id"),
                "page_num": chunk.get("page_num"),
                "content": content[:max_chars],
                "content_truncated": len(content) > max_chars,
            }
        )
    print(
        json.dumps(
            {
                "document_id": args.doc_id,
                "chunks": selected,
                "pagination": {
                    "offset": offset,
                    "limit": limit,
                    "returned": len(selected),
                    "total": len(chunks),
                    "has_more": offset + limit < len(chunks),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def query_terms(query: str) -> list[str]:
    compact = re.sub(r"\s+", "", query.lower())
    words = [item for item in re.split(r"[^\w\u4e00-\u9fff]+", query.lower()) if len(item) >= 2]
    pairs = [compact[i : i + 2] for i in range(max(0, len(compact) - 1))]
    return list(dict.fromkeys(words + pairs))[:40]


def search(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    client, config = client_for(workspace)
    documents = client.list_documents(args.domain or config.get("default_domain"))
    if isinstance(documents, dict):
        documents = documents.get("documents", documents.get("items", []))
    if not isinstance(documents, list):
        raise SpaceKBError("SpaceKB 文档列表格式不符合预期")
    terms = query_terms(args.query)
    results = []
    max_documents = max(1, min(args.max_documents, MAX_SEARCH_DOCUMENTS))
    result_limit = max(1, min(args.limit, MAX_SEARCH_RESULTS))
    max_chars = max(100, min(args.max_chars, MAX_SEARCH_CHARS))
    for document in documents[:max_documents]:
        if not isinstance(document, dict) or not document.get("id"):
            continue
        chunks = client.chunks(str(document["id"]))
        if isinstance(chunks, dict):
            chunks = chunks.get("chunks", chunks.get("items", []))
        for chunk in chunks if isinstance(chunks, list) else []:
            content = str(chunk.get("content", ""))
            lowered = content.lower()
            score = sum(lowered.count(term) for term in terms)
            if score:
                results.append(
                    {
                        "score": score,
                        "document_id": document.get("id"),
                        "filename": document.get("filename"),
                        "chunk_id": chunk.get("id"),
                        "page_num": chunk.get("page_num"),
                        "content": content[:max_chars],
                        "content_truncated": len(content) > max_chars,
                    }
                )
    results.sort(key=lambda item: item["score"], reverse=True)
    print(json.dumps({"query": args.query[:500], "results": results[:result_limit]}, ensure_ascii=False, indent=2))
    return 0


def upload_file(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    client, config = client_for(workspace)
    file_path = Path(args.file).expanduser().resolve()
    if not file_path.is_file():
        raise SpaceKBError(f"文件不存在：{file_path}")
    value = client.upload(file_path, args.domain or config.get("default_domain", DEFAULT_DOMAIN))
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            values.append(item)
    return values


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def daily_markdown(sales_root: Path, target_date: date) -> str:
    events = [
        item
        for item in load_jsonl(sales_root / "logs/task-events.jsonl")
        if str(item.get("occurred_at", ""))[:10] == target_date.isoformat()
    ]
    completed = [item for item in events if item.get("event_type") == "completed"]
    milestones = [item for item in events if item.get("event_type") == "milestone"]
    updated_customers = []
    upcoming = []
    for path in sorted((sales_root / "customers").glob("*/customer.json")):
        try:
            customer = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(customer.get("updated_at", ""))[:10] == target_date.isoformat():
            updated_customers.append(customer)
        due = parse_date(customer.get("next_followup_at"))
        if due and target_date <= due <= target_date + timedelta(days=7):
            upcoming.append((due, customer))

    lines = [
        "---",
        "document_type: sales-daily-summary",
        f"date: {target_date.isoformat()}",
        "visibility: private",
        f"generated_at: {now_iso()}",
        "---",
        "",
        f"# 销售工作日报｜{target_date.isoformat()}",
        "",
        "## 今日已完成",
        "",
    ]
    if completed:
        for item in completed:
            customer = f"｜{item.get('customer_name')}" if item.get("customer_name") else ""
            details = f"：{item.get('details')}" if item.get("details") else ""
            lines.append(f"- {item.get('title', '已完成事项')}{customer}{details}")
    else:
        lines.append("- 今日尚未记录已完成事项。")

    lines.extend(["", "## 今日重要节点", ""])
    for item in milestones:
        customer = f"｜{item.get('customer_name')}" if item.get("customer_name") else ""
        details = f"：{item.get('details')}" if item.get("details") else ""
        lines.append(f"- {item.get('title', '重要节点')}{customer}{details}")
    for customer in updated_customers:
        lines.append(
            f"- {customer.get('name', '未命名客户')}｜{customer.get('stage') or '阶段未确认'}："
            f"{customer.get('latest_update') or '今日客户状态已更新'}"
        )
    if not milestones and not updated_customers:
        lines.append("- 今日尚未记录新的重要客户节点。")

    lines.extend(["", "## 未来七天关键安排", ""])
    if upcoming:
        for due, customer in sorted(upcoming, key=lambda item: item[0]):
            lines.append(
                f"- {due.isoformat()}｜{customer.get('name', '未命名客户')}："
                f"{customer.get('next_action') or customer.get('followup_reason') or '确认下一步'}"
            )
    else:
        lines.append("- 暂无已确认的未来七天客户节点。")
    lines.extend(["", "> 本文档由销售本人私有工作区同步，仅用于个人知识沉淀。", ""])
    return "\n".join(lines)


def sync_log_path(sales_root: Path) -> Path:
    return sales_root / "logs/spacekb-sync.jsonl"


def sync_daily(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    sales_root = Path(args.sales_root).expanduser().resolve()
    target_date = date.fromisoformat(args.date) if args.date else datetime.now().astimezone().date()
    output = sales_root / "exports/spacekb" / f"SA销售日报-{target_date.isoformat()}.md"
    content = daily_markdown(sales_root, target_date)
    atomic_write(output, content)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    previous = [
        item
        for item in load_jsonl(sync_log_path(sales_root))
        if item.get("date") == target_date.isoformat() and item.get("status") == "uploaded"
    ]
    if previous and not args.force:
        print(
            json.dumps(
                {
                    "status": "already-uploaded",
                    "date": target_date.isoformat(),
                    "local_file": str(output),
                    "document_id": previous[-1].get("document_id"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    client, config = client_for(workspace)
    response = client.upload(output, args.domain or config.get("default_domain", DEFAULT_DOMAIN))
    record = {
        "date": target_date.isoformat(),
        "status": "uploaded",
        "document_id": response.get("id") if isinstance(response, dict) else None,
        "remote_status": response.get("status") if isinstance(response, dict) else None,
        "sha256": digest,
        "uploaded_at": now_iso(),
    }
    path = sync_log_path(sales_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({**record, "local_file": str(output)}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    setup = sub.add_parser("configure")
    setup.add_argument("--workspace", required=True)
    setup.add_argument("--base-url", default=DEFAULT_BASE_URL)
    setup.add_argument("--knowledge-base-id", default=DEFAULT_KNOWLEDGE_BASE_ID)
    setup.add_argument("--default-domain", default=DEFAULT_DOMAIN)
    setup.add_argument("--api-key-stdin", action="store_true")
    setup.add_argument("--api-key-env")
    setup.add_argument("--allow-insecure-http", action="store_true")
    setup.add_argument("--skip-test", action="store_true", help=argparse.SUPPRESS)
    setup.set_defaults(func=configure)

    state = sub.add_parser("status")
    state.add_argument("--workspace", required=True)
    state.set_defaults(func=status)

    documents = sub.add_parser("list")
    documents.add_argument("--workspace", required=True)
    documents.add_argument("--domain")
    documents.add_argument("--offset", type=int, default=0)
    documents.add_argument("--limit", type=int, default=50)
    documents.set_defaults(func=list_documents)

    chunks = sub.add_parser("chunks")
    chunks.add_argument("--workspace", required=True)
    chunks.add_argument("--doc-id", required=True)
    chunks.add_argument("--offset", type=int, default=0)
    chunks.add_argument("--limit", type=int, default=8)
    chunks.add_argument("--max-chars", type=int, default=1600)
    chunks.set_defaults(func=show_chunks)

    find = sub.add_parser("search")
    find.add_argument("--workspace", required=True)
    find.add_argument("--query", required=True)
    find.add_argument("--domain")
    find.add_argument("--max-documents", type=int, default=20)
    find.add_argument("--limit", type=int, default=8)
    find.add_argument("--max-chars", type=int, default=1600)
    find.set_defaults(func=search)

    upload = sub.add_parser("upload")
    upload.add_argument("--workspace", required=True)
    upload.add_argument("--file", required=True)
    upload.add_argument("--domain")
    upload.set_defaults(func=upload_file)

    daily = sub.add_parser("sync-daily")
    daily.add_argument("--workspace", required=True)
    daily.add_argument("--sales-root", required=True)
    daily.add_argument("--date")
    daily.add_argument("--domain", default=DEFAULT_DOMAIN)
    daily.add_argument("--force", action="store_true")
    daily.set_defaults(func=sync_daily)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return args.func(args)
    except SpaceKBError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
