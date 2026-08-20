#!/usr/bin/env python3
"""Initialize a local SA sales workspace without overwriting user data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Target SA销售工作区 directory")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    created_dirs = []
    for rel in [
        "config",
        "inbox/pending",
        "inbox/confirmed",
        "inbox/rejected",
        "indexes",
        "customers",
        "dashboard",
        "growth/reviews",
        "logs",
    ]:
        path = root / rel
        if not path.exists():
            created_dirs.append(rel)
        path.mkdir(parents=True, exist_ok=True)

    created_files = []
    files = {
        "config/company-profile.md": "# 企业销售知识配置\n\n## 企业名称\n\n## 销售业务\n\n## 产品与项目资料位置\n\n## 价格与承诺边界\n\n## 待确认\n",
        "config/sales-soul.md": "---\nschema_version: 1\nstatus: provisional\nsample_messages: 0\nsample_meetings: 0\nupdated_at: \"\"\n---\n\n# 销售表达灵魂\n\n## 整体气质\n\n## 称呼习惯\n\n## 语言特征\n\n## 跟进习惯\n\n## 异议处理\n\n## 禁止表达\n\n## 已确认示例\n\n## 待确认\n",
        "config/sales-method-library.md": "# 企业销售方法库\n\n## 已采用方法\n\n- 价值前置\n- 异议拆解\n- 双路径推进\n- 决策链地图\n- 承诺闭环\n- 沉默唤醒\n\n## 企业自定义案例\n\n仅添加已脱敏、已获授权的真实案例。\n\n## 禁止方法\n\n- 虚假稀缺\n- 隐瞒条件\n- 威胁或高压成交\n- 未经授权的承诺\n",
        "growth/strategy-notes.md": "# 我的策略笔记\n\n按需记录真正有效的销售判断、案例与表达。这里不设课程、进度、打卡或评分。\n\n## 值得保留的方法\n\n## 适用场景\n\n## 不适用条件\n",
        "config/reminder-settings.json": json.dumps(
            {
                "schema_version": 1,
                "enabled": False,
                "time": "08:45",
                "weekdays_only": True,
                "timezone": "local",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "indexes/customer-index.json": json.dumps(
            {"schema_version": 1, "updated_at": now_iso(), "customers": []},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "indexes/material-index.json": json.dumps(
            {"schema_version": 1, "updated_at": now_iso(), "materials": []},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "indexes/ingestion-ledger.jsonl": "",
        "dashboard/dashboard-data.json": json.dumps(
            {"schema_version": 1, "generated_at": None, "date": None, "customers": []},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "logs/automation-runs.jsonl": "",
    }
    for rel, content in files.items():
        if write_if_missing(root / rel, content):
            created_files.append(rel)

    print(
        json.dumps(
            {
                "workspace": str(root),
                "created_directories": created_dirs,
                "created_files": created_files,
                "status": "initialized",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
