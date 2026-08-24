#!/usr/bin/env python3
"""Safely update the SA Sales Advisor runtime from official GitHub releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


MANIFEST_URL = (
    "https://github.com/kingkemander/spaceagents-sales-advisor/"
    "releases/latest/download/update-manifest.json"
)
OFFICIAL_RELEASE_PREFIX = (
    "https://github.com/kingkemander/spaceagents-sales-advisor/releases/download/"
)
MANAGED_AGENT_MARKER = "<!-- managed-by-spaceagents-sales-advisor -->"
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
REQUIRED_RUNTIME_FILES = [
    "sa_sales_advisor/cli.py",
    "sa_sales_advisor/update_client.py",
    "sa_sales_advisor/system_reminder.py",
    "sa_sales_advisor/company_radar.py",
    "sa_sales_advisor/company_radar_confirm.py",
    "scripts/voice-alarm/macos/alarm-reminder.sh",
    "scripts/voice-alarm/macos/schedule-alarm.sh",
    "sa_sales_advisor/image_batch.py",
    "sa_sales_advisor/vision_client.py",
    "sa_sales_advisor/activity_store.py",
    "sa_sales_advisor/spacekb_client.py",
    "sa_sales_advisor/presentation.py",
    "sa_sales_advisor/pipeline_store.py",
    "sa_sales_advisor/automation_client.py",
    "sa_sales_advisor/templates/dashboard-template.html",
    "sa_sales_advisor/templates/sales-advisor-agent.md",
    "playbooks/ingest-customer-materials/PLAYBOOK.md",
    "playbooks/maintain-customer-memory/PLAYBOOK.md",
    "playbooks/learn-sales-voice/PLAYBOOK.md",
    "playbooks/plan-daily-followups/PLAYBOOK.md",
    "playbooks/schedule-sales-reminders/PLAYBOOK.md",
    "playbooks/sync-spacekb/PLAYBOOK.md",
    "playbooks/draft-sales-reply/PLAYBOOK.md",
    "playbooks/coach-sales-growth/PLAYBOOK.md",
    "playbooks/manage-sales-pipeline/PLAYBOOK.md",
    "playbooks/company-intelligence-radar/PLAYBOOK.md",
    "VERSION",
]


def now() -> datetime:
    return datetime.now().astimezone()


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_tuple(value: str) -> tuple[int, int, int]:
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"invalid release version: {value}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def valid_runtime(path: Path, expected_version: str | None = None) -> bool:
    try:
        if not all((path / item).is_file() for item in REQUIRED_RUNTIME_FILES):
            return False
        actual = (path / "VERSION").read_text(encoding="utf-8").strip()
        return expected_version is None or actual == expected_version
    except OSError:
        return False


def safe_member(info: zipfile.ZipInfo, destination: Path) -> bool:
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        return False
    target = (destination / info.filename).resolve()
    base = destination.resolve()
    return target == base or str(target).startswith(str(base) + os.sep)


def extract_safely(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not safe_member(info, destination):
                raise RuntimeError(f"unsafe archive member: {info.filename}")
        bundle.extractall(destination)


def allowed_url(url: str, *, manifest: bool = False) -> bool:
    if os.environ.get("SA_SALES_ADVISOR_TESTING") == "1":
        return urllib.parse.urlparse(url).hostname in {"127.0.0.1", "localhost"} or (
            url == MANIFEST_URL if manifest else url.startswith(OFFICIAL_RELEASE_PREFIX)
        )
    return url == MANIFEST_URL if manifest else url.startswith(OFFICIAL_RELEASE_PREFIX)


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "SpaceAgents-Sales-Advisor-Updater/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_DOWNLOAD_BYTES:
            raise RuntimeError("update download is larger than the allowed limit")
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise RuntimeError("update download is larger than the allowed limit")
    return data


def write_managed_agent(workspace: Path, runtime_root: Path) -> str:
    source = runtime_root / "sa_sales_advisor/templates/sales-advisor-agent.md"
    destination = workspace / ".opencode/agents/销售军师.md"
    content = source.read_text(encoding="utf-8")
    if destination.exists():
        existing = destination.read_text(encoding="utf-8")
        if existing == content:
            return "ready"
        if MANAGED_AGENT_MARKER not in existing:
            return "conflict-preserved"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".md.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(destination)
    return "installed"


def current_info(base: Path) -> dict:
    value = read_json(base / "current.json")
    root = Path(str(value.get("runtime_root", ""))).expanduser()
    if root.is_absolute() and valid_runtime(root):
        return value
    candidates = sorted(base.glob("runtime-v*"), reverse=True)
    for candidate in candidates:
        if valid_runtime(candidate):
            version = (candidate / "VERSION").read_text(encoding="utf-8").strip()
            return {
                "version": version,
                "runtime_root": str(candidate),
                "cli": str(candidate / "sa_sales_advisor/cli.py"),
            }
    raise RuntimeError("no valid installed runtime is available")


def check_due(state: dict, interval_hours: int) -> bool:
    raw = state.get("last_checked_at")
    if not raw:
        return True
    try:
        checked = datetime.fromisoformat(str(raw))
    except ValueError:
        return True
    retry_hours = 1 if state.get("last_result") == "update_failed" else interval_hours
    return now() >= checked + timedelta(hours=retry_hours)


def install_release(workspace: Path, base: Path, manifest: dict) -> dict:
    version = str(manifest.get("version", ""))
    archive_url = str(manifest.get("runtime_url", ""))
    expected_hash = str(manifest.get("runtime_sha256", "")).lower()
    if manifest.get("schema_version") != 1 or manifest.get("channel") != "stable":
        raise RuntimeError("unsupported update manifest")
    version_tuple(version)
    if not allowed_url(archive_url) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise RuntimeError("update manifest contains an untrusted asset")

    target = base / f"runtime-v{version}"
    if valid_runtime(target, version):
        agent_status = write_managed_agent(workspace, target)
        return {"runtime_root": target, "sha256": expected_hash, "agent_status": agent_status}

    staging = base / f".updating-v{version}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    handle = tempfile.NamedTemporaryFile(prefix="sa-sales-update-", suffix=".zip", dir=base, delete=False)
    archive = Path(handle.name)
    handle.close()
    try:
        archive.write_bytes(fetch_bytes(archive_url))
        actual_hash = sha256_file(archive)
        if actual_hash != expected_hash:
            raise RuntimeError("runtime checksum mismatch")
        extract_safely(archive, staging)
        if not valid_runtime(staging, version):
            raise RuntimeError("runtime archive is incomplete")
        if target.exists():
            shutil.rmtree(target)
        staging.replace(target)
        agent_status = write_managed_agent(workspace, target)
        return {"runtime_root": target, "sha256": actual_hash, "agent_status": agent_status}
    finally:
        archive.unlink(missing_ok=True)
        if staging.exists():
            shutil.rmtree(staging)


def check(workspace: Path, interval_hours: int, force: bool, manifest_url: str) -> dict:
    base = workspace / ".spaceagents/plugins/sa-sales-advisor"
    base.mkdir(parents=True, exist_ok=True)
    current = current_info(base)
    state_path = base / "update-state.json"
    state = read_json(state_path)
    if not force and not check_due(state, interval_hours):
        return {"status": "skipped", "reason": "check-not-due", **current}

    checked_at = now().isoformat(timespec="seconds")
    try:
        if not allowed_url(manifest_url, manifest=True):
            raise RuntimeError("untrusted update manifest URL")
        manifest = json.loads(fetch_bytes(manifest_url).decode("utf-8"))
        if not isinstance(manifest, dict):
            raise RuntimeError("invalid update manifest")
        latest = str(manifest.get("version", ""))
        if version_tuple(latest) <= version_tuple(str(current["version"])):
            state = {
                "last_checked_at": checked_at,
                "last_result": "current",
                "current_version": current["version"],
                "latest_version": latest,
            }
            atomic_json(state_path, state)
            return {"status": "current", **current}

        installed = install_release(workspace, base, manifest)
        runtime_root = installed["runtime_root"]
        next_current = {
            "version": latest,
            "runtime_root": str(runtime_root),
            "cli": str(runtime_root / "sa_sales_advisor/cli.py"),
            "installed_at": checked_at,
            "source": manifest["runtime_url"],
            "sha256": installed["sha256"],
            "workspace_agent": installed["agent_status"],
            "workspace_agent_path": str(workspace / ".opencode/agents/销售军师.md"),
        }
        atomic_json(base / "current.json", next_current)
        atomic_json(
            state_path,
            {
                "last_checked_at": checked_at,
                "last_result": "updated",
                "current_version": latest,
                "latest_version": latest,
            },
        )
        return {"status": "updated", "previous_version": current["version"], **next_current}
    except Exception as exc:  # The existing runtime must remain usable if update infrastructure fails.
        atomic_json(
            state_path,
            {
                "last_checked_at": checked_at,
                "last_result": "update_failed",
                "current_version": current["version"],
                "error": str(exc),
            },
        )
        return {"status": "update_failed", "error": str(exc), **current}


def main() -> int:
    parser = argparse.ArgumentParser(description="SA Sales Advisor automatic updater")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--workspace", default=".")
    check_parser.add_argument("--interval-hours", type=int, default=24)
    check_parser.add_argument("--force", action="store_true")
    check_parser.add_argument("--manifest-url", default=MANIFEST_URL, help=argparse.SUPPRESS)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--workspace", default=".")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    base = workspace / ".spaceagents/plugins/sa-sales-advisor"
    if args.command == "status":
        result = {"status": "ready", **current_info(base), "update": read_json(base / "update-state.json")}
    else:
        result = check(workspace, max(1, args.interval_hours), args.force, args.manifest_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
