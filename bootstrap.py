#!/usr/bin/env python3
"""Install the pinned SA Sales Advisor runtime into the current workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


VERSION = "0.13.0"
RUNTIME_URL = (
    "https://github.com/kingkemander/spaceagents-sales-advisor/releases/download/"
    "v0.13.0/spaceagents-sales-advisor-runtime-v0.13.0.zip"
)
RUNTIME_SHA256 = "cb128a26cc8f684914b30fdc7c953a7f5b20ed65d1c50e7e1fa5635b8651110e"
MANAGED_AGENT_MARKER = "<!-- managed-by-spaceagents-sales-advisor -->"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_safe_member(info: zipfile.ZipInfo, destination: Path) -> bool:
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        return False
    target = (destination / info.filename).resolve()
    base = destination.resolve()
    return target == base or str(target).startswith(str(base) + os.sep)


def extract_safely(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not is_safe_member(info, destination):
                raise RuntimeError(f"unsafe archive member: {info.filename}")
        bundle.extractall(destination)


def valid_runtime(path: Path) -> bool:
    required = [
        path / "sa_sales_advisor/cli.py",
        path / "sa_sales_advisor/image_batch.py",
        path / "sa_sales_advisor/vision_client.py",
        path / "sa_sales_advisor/activity_store.py",
        path / "sa_sales_advisor/spacekb_client.py",
        path / "sa_sales_advisor/presentation.py",
        path / "sa_sales_advisor/pipeline_store.py",
        path / "sa_sales_advisor/automation_client.py",
        path / "sa_sales_advisor/update_client.py",
        path / "sa_sales_advisor/system_reminder.py",
        path / "sa_sales_advisor/company_radar.py",
        path / "sa_sales_advisor/company_radar_confirm.py",
        path / "scripts/voice-alarm/macos/alarm-reminder.sh",
        path / "scripts/voice-alarm/macos/schedule-alarm.sh",
        path / "sa_sales_advisor/templates/dashboard-template.html",
        path / "playbooks/ingest-customer-materials/PLAYBOOK.md",
        path / "playbooks/maintain-customer-memory/PLAYBOOK.md",
        path / "playbooks/learn-sales-voice/PLAYBOOK.md",
        path / "playbooks/plan-daily-followups/PLAYBOOK.md",
        path / "playbooks/schedule-sales-reminders/PLAYBOOK.md",
        path / "playbooks/schedule-sales-reminders/references/automation-prompts.md",
        path / "playbooks/sync-spacekb/PLAYBOOK.md",
        path / "playbooks/sync-spacekb/references/spacekb-api.md",
        path / "playbooks/draft-sales-reply/PLAYBOOK.md",
        path / "playbooks/draft-sales-reply/references/global-sales-wisdom.md",
        path / "playbooks/draft-sales-reply/references/customer-decision-psychology.md",
        path / "playbooks/coach-sales-growth/PLAYBOOK.md",
        path / "playbooks/manage-sales-pipeline/PLAYBOOK.md",
        path / "playbooks/company-intelligence-radar/PLAYBOOK.md",
        path / "sa_sales_advisor/templates/sales-advisor-agent.md",
        path / "VERSION",
    ]
    return all(item.is_file() for item in required) and (path / "VERSION").read_text(encoding="utf-8").strip() == VERSION


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "SpaceAgents-Sales-Advisor/0.13.0"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def atomic_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def write_managed_file(destination: Path, content: str) -> str:
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


def install_workspace_agent(workspace: Path, runtime_root: Path) -> dict:
    """Create the selectable agent only inside the current SpaceAgents workspace."""
    agent_path = workspace / ".opencode/agents/销售军师.md"
    status = write_managed_file(
        agent_path,
        (runtime_root / "sa_sales_advisor/templates/sales-advisor-agent.md").read_text(encoding="utf-8"),
    )
    return {
        "workspace_agent": status,
        "workspace_agent_path": str(agent_path),
    }


def usable_current(base: Path) -> dict | None:
    try:
        value = json.loads((base / "current.json").read_text(encoding="utf-8"))
        root = Path(str(value.get("runtime_root", "")))
        required = [root / "VERSION", root / "sa_sales_advisor/cli.py", root / "sa_sales_advisor/update_client.py"]
        if root.is_absolute() and all(item.is_file() for item in required):
            return value
    except (OSError, ValueError):
        pass
    return None


def set_current(base: Path, workspace: Path, runtime_root: Path, source: str, sha256: str) -> dict:
    workspace_agent = install_workspace_agent(workspace, runtime_root)
    version = (runtime_root / "VERSION").read_text(encoding="utf-8").strip()
    value = {
        "version": version,
        "runtime_root": str(runtime_root),
        "cli": str(runtime_root / "sa_sales_advisor/cli.py"),
        "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source,
        "sha256": sha256,
        **workspace_agent,
    }
    atomic_json(base / "current.json", value)
    return value


def automatic_update(workspace: Path, fallback_runtime: Path, skip: bool = False) -> dict:
    if skip:
        return {"status": "skipped", "reason": "disabled-by-argument"}
    updater = fallback_runtime / "sa_sales_advisor/update_client.py"
    result = subprocess.run(
        [sys.executable, str(updater), "check", "--workspace", str(workspace), "--interval-hours", "24"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {"status": "update_failed", "error": (result.stderr or result.stdout).strip()}
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {"status": "update_failed", "error": "updater returned invalid output"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=".", help="Current Space Agents workspace")
    parser.add_argument("--runtime-url", default=RUNTIME_URL, help=argparse.SUPPRESS)
    parser.add_argument("--runtime-sha256", default=RUNTIME_SHA256, help=argparse.SUPPRESS)
    parser.add_argument("--skip-update-check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    base = workspace / ".spaceagents/plugins/sa-sales-advisor"
    target = base / f"runtime-v{VERSION}"
    cli = target / "sa_sales_advisor/cli.py"
    base.mkdir(parents=True, exist_ok=True)

    installed_now = False

    if not valid_runtime(target):
        staging = base / f".installing-v{VERSION}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        archive_handle = tempfile.NamedTemporaryFile(prefix="sa-sales-runtime-", suffix=".zip", dir=base, delete=False)
        archive = Path(archive_handle.name)
        archive_handle.close()
        try:
            download(args.runtime_url, archive)
            actual = sha256_file(archive)
            if actual != args.runtime_sha256:
                raise RuntimeError(f"runtime checksum mismatch: expected {args.runtime_sha256}, got {actual}")
            extract_safely(archive, staging)
            if not valid_runtime(staging):
                raise RuntimeError("runtime archive is incomplete")
            if target.exists():
                shutil.rmtree(target)
            staging.replace(target)
            installed_now = True
        finally:
            if archive.exists():
                archive.unlink()
            if staging.exists():
                shutil.rmtree(staging)

    current = usable_current(base)
    if current is None:
        current = set_current(base, workspace, target, args.runtime_url, args.runtime_sha256)
    update = automatic_update(workspace, target, args.skip_update_check)
    current = usable_current(base) or current
    runtime_root = Path(current["runtime_root"])
    workspace_agent = install_workspace_agent(workspace, runtime_root)
    current.update(workspace_agent)
    atomic_json(base / "current.json", current)
    print(json.dumps({"status": "installed" if installed_now else "ready", **current, "auto_update": update}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
