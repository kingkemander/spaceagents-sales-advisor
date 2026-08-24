#!/usr/bin/env python3
"""Single local entry point for the SA Sales Advisor runtime tools."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TOOLS = {
    "init": "init_workspace.py",
    "customer": "ingest_store.py",
    "images": "image_batch.py",
    "vision": "vision_client.py",
    "memory": "memory_store.py",
    "dashboard": "render_dashboard.py",
    "activity": "activity_store.py",
    "knowledge": "spacekb_client.py",
    "pipeline": "pipeline_store.py",
    "automation": "automation_client.py",
    "update": "update_client.py",
    "system-reminder": "system_reminder.py",
}


def usage() -> str:
    return """SA Sales Advisor runtime

Usage:
  cli.py init --root <SA销售工作区>
  cli.py customer <create|register-material|hash|validate> [options]
  cli.py images <scan|prepare|ocr|record|finalize|status> [options]
  cli.py vision <models|analyze> [options]
  cli.py memory <update|validate> [options]
  cli.py dashboard --workspace <SA销售工作区> [--date YYYY-MM-DD]
  cli.py activity <add|list> [options]
  cli.py knowledge <configure|status|list|chunks|search|upload|sync-daily> [options]
  cli.py pipeline --workspace <SA销售工作区> [--date YYYY-MM-DD]
  cli.py automation <create|disable|list> [options]
  cli.py update <check|status> [options]
  cli.py system-reminder --workspace <项目根目录> --title <标题> --message-file <文件> --time HH:MM [--date YYYY-MM-DD] [--repeat 1-5]
"""


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help", "help"}:
        print(usage())
        return 0
    command = sys.argv[1]
    script = TOOLS.get(command)
    if script is None:
        print(f"Unknown command: {command}\n\n{usage()}", file=sys.stderr)
        return 2
    target = Path(__file__).resolve().parent / script
    return subprocess.run([sys.executable, str(target), *sys.argv[2:]], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
