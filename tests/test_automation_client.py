from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "sa_sales_advisor/cli.py"


class AutomationApiHandler(BaseHTTPRequestHandler):
    tasks: dict[str, dict] = {}
    workspace_path = ""
    calls: list[tuple[str, str]] = []

    def log_message(self, *_):
        return

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self) -> bool:
        return self.headers.get("Authorization") == "Bearer test-secret"

    def do_GET(self):
        self.calls.append(("GET", self.path))
        if not self.authorized():
            self.send_json({"error": "unauthorized"}, 401)
        elif self.path == "/workspaces":
            self.send_json({"items": [{"id": "ws-test", "name": "测试", "path": self.workspace_path}]})
        elif self.path == "/automations/tasks":
            self.send_json({"tasks": list(self.tasks.values())})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        self.calls.append(("POST", self.path))
        if not self.authorized():
            self.send_json({"error": "unauthorized"}, 401)
            return
        payload = self.body()
        task = {"id": "task-001", **payload}
        self.tasks[task["id"]] = task
        self.send_json({"task": task}, 201)

    def do_PUT(self):
        self.calls.append(("PUT", self.path))
        task_id = self.path.rsplit("/", 1)[-1]
        self.tasks[task_id].update(self.body())
        self.send_json({"task": self.tasks[task_id]})

    def do_DELETE(self):
        self.calls.append(("DELETE", self.path))
        self.tasks.pop(self.path.rsplit("/", 1)[-1], None)
        self.send_json({"ok": True})


class AutomationClientTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "销售项目"
        self.workspace.mkdir()
        self.prompt = Path(self.temp.name) / "prompt.md"
        self.prompt.write_text("提醒我确认是否已经给吴总发消息。", encoding="utf-8")
        AutomationApiHandler.tasks = {}
        AutomationApiHandler.calls = []
        AutomationApiHandler.workspace_path = str(self.workspace)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), AutomationApiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env = {
            **os.environ,
            "OPENWORK_SERVER_URL": f"http://127.0.0.1:{self.server.server_port}",
            "OPENWORK_SERVER_TOKEN": "test-secret",
        }

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def run_cli(self, *args: str, env: Optional[dict] = None, check: bool = True):
        result = subprocess.run(
            [sys.executable, str(CLI), *args], cwd=ROOT, env=env or self.env,
            text=True, capture_output=True, check=False,
        )
        if check and result.returncode != 0:
            self.fail(f"automation CLI failed: {result.stderr}\n{result.stdout}")
        return result

    def test_creates_one_time_reminder_inside_spaceagents(self):
        result = self.run_cli(
            "automation", "create", "--workspace", str(self.workspace),
            "--name", "吴总行动确认", "--prompt-file", str(self.prompt),
            "--schedule", "once", "--time", "23:20",
        )
        output = json.loads(result.stdout)
        task = AutomationApiHandler.tasks["task-001"]
        self.assertEqual(output["status"], "created")
        self.assertEqual(output["schedule"], "once")
        self.assertEqual(task["schedule"], "daily")
        self.assertTrue(task["enabled"])
        self.assertEqual(task["workspaceId"], "ws-test")
        self.assertEqual(task["agent"], "销售军师")
        self.assertIn('automation disable --task-id "task-001"', task["prompt"])
        self.assertNotIn("test-secret", result.stdout)
        self.assertEqual([call[0] for call in AutomationApiHandler.calls], ["GET", "GET", "POST", "PUT"])

    def test_creates_recurring_reminder_without_self_disable(self):
        self.run_cli(
            "automation", "create", "--workspace", str(self.workspace),
            "--name", "每日行动", "--prompt-file", str(self.prompt),
            "--schedule", "daily", "--time", "08:45",
        )
        task = AutomationApiHandler.tasks["task-001"]
        self.assertEqual(task["schedule"], "daily")
        self.assertTrue(task["enabled"])
        self.assertNotIn("automation disable", task["prompt"])
        self.assertEqual([call[0] for call in AutomationApiHandler.calls], ["GET", "GET", "POST"])

    def test_updates_same_named_task_instead_of_creating_duplicate(self):
        AutomationApiHandler.tasks["existing"] = {
            "id": "existing", "name": "每日行动", "workspaceId": "ws-test",
            "schedule": "daily", "time": "08:00", "enabled": True,
        }
        self.run_cli(
            "automation", "create", "--workspace", str(self.workspace),
            "--name", "每日行动", "--prompt-file", str(self.prompt),
            "--schedule", "daily", "--time", "09:15",
        )
        self.assertEqual(set(AutomationApiHandler.tasks), {"existing"})
        self.assertEqual(AutomationApiHandler.tasks["existing"]["time"], "09:15")
        self.assertEqual([call[0] for call in AutomationApiHandler.calls], ["GET", "GET", "PUT"])

    def test_missing_app_credentials_is_an_explicit_failure(self):
        env = dict(os.environ)
        env.pop("OPENWORK_SERVER_URL", None)
        env.pop("OPENWORK_SERVER_TOKEN", None)
        result = self.run_cli("automation", "list", env=env, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("automation API is unavailable", result.stderr)


if __name__ == "__main__":
    unittest.main()
