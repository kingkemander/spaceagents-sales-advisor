#!/usr/bin/env python3
"""Install the pinned SA Sales Advisor runtime into the current workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


VERSION = "0.10.2"
RUNTIME_URL = (
    "https://github.com/kingkemander/spaceagents-sales-advisor/releases/download/"
    "v0.10.2/spaceagents-sales-advisor-runtime-v0.10.2.zip"
)
RUNTIME_SHA256 = "918422a8df71b8a998441703a1b4b03b7a4615f009eae167d921da3256b590cb"
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
        path / "sa_sales_advisor/templates/sales-advisor-agent.md",
        path / "VERSION",
    ]
    return all(item.is_file() for item in required) and (path / "VERSION").read_text(encoding="utf-8").strip() == VERSION


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "SpaceAgents-Sales-Advisor/0.10.2"})
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=".", help="Current Space Agents workspace")
    parser.add_argument("--runtime-url", default=RUNTIME_URL, help=argparse.SUPPRESS)
    parser.add_argument("--runtime-sha256", default=RUNTIME_SHA256, help=argparse.SUPPRESS)
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    base = workspace / ".spaceagents/plugins/sa-sales-advisor"
    target = base / f"runtime-v{VERSION}"
    cli = target / "sa_sales_advisor/cli.py"
    base.mkdir(parents=True, exist_ok=True)

    if valid_runtime(target):
        workspace_agent = install_workspace_agent(workspace, target)
        print(json.dumps({"status": "ready", "version": VERSION, "runtime_root": str(target), "cli": str(cli), **workspace_agent}, ensure_ascii=False, indent=2))
        return 0

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
        workspace_agent = install_workspace_agent(workspace, target)
        atomic_json(
            base / "current.json",
            {
                "version": VERSION,
                "runtime_root": str(target),
                "cli": str(cli),
                "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "source": args.runtime_url,
                "sha256": args.runtime_sha256,
                **workspace_agent,
            },
        )
    finally:
        if archive.exists():
            archive.unlink()
        if staging.exists():
            shutil.rmtree(staging)

    print(json.dumps({"status": "installed", "version": VERSION, "runtime_root": str(target), "cli": str(cli), **workspace_agent}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
