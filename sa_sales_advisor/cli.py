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
    "memory": "memory_store.py",
    "dashboard": "render_dashboard.py",
}


def usage() -> str:
    return """SA Sales Advisor runtime

Usage:
  cli.py init --root <SA销售工作区>
  cli.py customer <create|register-material|hash|validate> [options]
  cli.py images <scan|prepare|ocr|record|finalize|status> [options]
  cli.py memory <update|validate> [options]
  cli.py dashboard --workspace <SA销售工作区> [--date YYYY-MM-DD]
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
