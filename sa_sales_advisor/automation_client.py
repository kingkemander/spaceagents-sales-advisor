#!/usr/bin/env python3
"""Create and manage SpaceAgents automations through its authenticated local API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


def api_settings() -> tuple[str, str]:
    base_url = os.environ.get("OPENWORK_SERVER_URL", "").strip().rstrip("/")
    token = os.environ.get("OPENWORK_SERVER_TOKEN", "").strip()
    if not base_url or not token:
        raise SystemExit(
            "SpaceAgents automation API is unavailable in this process: "
            "OPENWORK_SERVER_URL or OPENWORK_SERVER_TOKEN is missing"
        )
    if not base_url.startswith(("http://127.0.0.1:", "http://localhost:", "https://127.0.0.1:", "https://localhost:")):
        raise SystemExit("refusing non-local OPENWORK_SERVER_URL")
    return base_url, token


def request_json(method: str, path: str, payload: Optional[dict] = None) -> dict:
    base_url, token = api_settings()
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base_url + path, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"SpaceAgents automation API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"SpaceAgents automation API is unreachable: {exc.reason}") from exc


def validate_time(value: str) -> str:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise SystemExit("time must use 24-hour HH:MM format")
    return value


def resolve_workspace_id(workspace: str) -> str:
    target = Path(workspace).expanduser().resolve()
    response = request_json("GET", "/workspaces")
    for item in response.get("items", []):
        raw_path = item.get("path")
        if not raw_path:
            continue
        try:
            if Path(raw_path).expanduser().resolve() == target:
                return str(item["id"])
        except (OSError, KeyError):
            continue
    known = [str(item.get("path")) for item in response.get("items", []) if item.get("path")]
    raise SystemExit(f"current workspace is not registered in SpaceAgents: {target}; known={known}")


def selected_model(args: argparse.Namespace) -> Optional[dict]:
    if not args.model:
        return None
    if "/" not in args.model:
        raise SystemExit("model must use providerID/modelID")
    provider_id, model_id = args.model.split("/", 1)
    return {"providerID": provider_id, "modelID": model_id}


def disable_command(task_id: str) -> str:
    cli = Path(__file__).resolve().parent / "cli.py"
    return f'{sys.executable} "{cli}" automation disable --task-id "{task_id}"'


def one_time_prompt(original: str, task_id: str) -> str:
    return f"""这是一次只执行一次的销售提醒。

先读取当前工作区中的最新客户资料，完成下面的提醒要求：

{original.strip()}

在生成最终提醒前，必须先使用终端执行下面的命令，将本任务停用，避免第二天重复提醒：

{disable_command(task_id)}

命令成功后再输出最终提醒。不要自动联系客户，不要再次创建同名任务。
"""


def create(args: argparse.Namespace) -> None:
    workspace_id = resolve_workspace_id(args.workspace)
    prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8").strip()
    if not prompt:
        raise SystemExit("prompt file is empty")
    time_value = validate_time(args.time)
    payload = {
        "name": args.name.strip(),
        "prompt": prompt,
        "workspaceId": workspace_id,
        "schedule": "daily" if args.schedule == "once" else args.schedule,
        "time": time_value,
        "enabled": args.schedule != "once",
        "agent": args.agent,
        "templateId": "sa-sales-advisor",
    }
    model = selected_model(args)
    if model:
        payload["model"] = model
    if not payload["name"]:
        raise SystemExit("name is required")

    existing = next(
        (
            item for item in request_json("GET", "/automations/tasks").get("tasks", [])
            if item.get("name") == payload["name"] and item.get("workspaceId") == workspace_id
        ),
        None,
    )
    if existing:
        task_id = str(existing["id"])
        if args.schedule == "once":
            payload["prompt"] = one_time_prompt(prompt, task_id)
            payload["enabled"] = True
        updated = request_json("PUT", f"/automations/tasks/{task_id}", payload).get("task", existing)
        result_status = "updated"
    else:
        created = request_json("POST", "/automations/tasks", payload).get("task", {})
        task_id = str(created.get("id") or "")
        if not task_id:
            raise SystemExit("SpaceAgents did not return a task id")

        if args.schedule == "once":
            try:
                updated = request_json(
                    "PUT",
                    f"/automations/tasks/{task_id}",
                    {"prompt": one_time_prompt(prompt, task_id), "enabled": True},
                ).get("task", created)
            except BaseException:
                try:
                    request_json("DELETE", f"/automations/tasks/{task_id}")
                finally:
                    raise
        else:
            updated = created
        result_status = "created"

    print(json.dumps({
        "status": result_status,
        "task_id": task_id,
        "name": updated.get("name", payload["name"]),
        "schedule": args.schedule,
        "time": time_value,
        "workspace_id": workspace_id,
        "agent": args.agent,
    }, ensure_ascii=False, indent=2))


def disable(args: argparse.Namespace) -> None:
    task = request_json("PUT", f"/automations/tasks/{args.task_id}", {"enabled": False}).get("task", {})
    print(json.dumps({"status": "disabled", "task_id": args.task_id, "name": task.get("name", "")}, ensure_ascii=False, indent=2))


def list_tasks(_: argparse.Namespace) -> None:
    tasks = request_json("GET", "/automations/tasks").get("tasks", [])
    public = [
        {key: item.get(key) for key in ["id", "name", "schedule", "time", "workspaceId", "enabled"]}
        for item in tasks
    ]
    print(json.dumps({"status": "ok", "tasks": public}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create_cmd = sub.add_parser("create")
    create_cmd.add_argument("--workspace", required=True, help="Current SpaceAgents project root")
    create_cmd.add_argument("--name", required=True)
    create_cmd.add_argument("--prompt-file", required=True)
    create_cmd.add_argument("--schedule", choices=["once", "daily", "weekly"], default="once")
    create_cmd.add_argument("--time", required=True)
    create_cmd.add_argument("--agent", default="销售军师")
    create_cmd.add_argument("--model", help="Optional providerID/modelID; defaults to the agent model")
    create_cmd.set_defaults(func=create)

    disable_cmd = sub.add_parser("disable")
    disable_cmd.add_argument("--task-id", required=True)
    disable_cmd.set_defaults(func=disable)

    list_cmd = sub.add_parser("list")
    list_cmd.set_defaults(func=list_tasks)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
