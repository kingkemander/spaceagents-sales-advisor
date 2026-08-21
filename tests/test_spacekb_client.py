from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sa_sales_advisor import activity_store, spacekb_client


class Handler(BaseHTTPRequestHandler):
    uploads = []

    def log_message(self, format, *args):
        return

    def send_json(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.endswith("/chunks"):
            self.send_json([{"id": "chunk-1", "content": "园区付款方案与交付安排", "page_num": 1}])
        elif "/documents" in self.path:
            self.send_json([{"id": "doc-1", "filename": "项目资料.md"}])
        else:
            self.send_json({"id": "kb-test", "name": "测试知识库"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.uploads.append(body)
        self.send_json({"id": "doc-uploaded", "status": "pending"})


class SpaceKBClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def configure(self):
        args = argparse.Namespace(
            workspace=str(self.workspace),
            base_url=self.base_url,
            knowledge_base_id="kb-test",
            default_domain="__private__",
            api_key_stdin=True,
            api_key_env=None,
            allow_insecure_http=False,
            skip_test=False,
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            original = spacekb_client.sys.stdin
            spacekb_client.sys.stdin = io.StringIO("sk-local-test\n")
            try:
                self.assertEqual(spacekb_client.configure(args), 0)
            finally:
                spacekb_client.sys.stdin = original

    def test_configuration_keeps_secret_out_of_config(self):
        self.configure()
        config = spacekb_client.config_path(self.workspace).read_text(encoding="utf-8")
        self.assertNotIn("sk-local-test", config)
        self.assertEqual(
            spacekb_client.secret_path(self.workspace).read_text(encoding="utf-8").strip(),
            "sk-local-test",
        )
        self.assertIn("*", (spacekb_client.secret_path(self.workspace).parent / ".gitignore").read_text())

    def test_public_http_is_rejected_by_default(self):
        with self.assertRaises(spacekb_client.SpaceKBError):
            spacekb_client.ensure_safe_url("http://123.56.18.172:30000", False)

    def test_daily_private_sync_contains_completed_work(self):
        self.configure()
        sales_root = self.workspace / "SA销售工作区"
        event_args = argparse.Namespace(
            root=str(sales_root),
            event_type="completed",
            title="发送付款方案",
            customer_id="cus-1",
            customer_name="吴总",
            details="客户已收到",
            occurred_at=datetime.now().astimezone().isoformat(),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            activity_store.append_event(event_args)
        args = argparse.Namespace(
            workspace=str(self.workspace),
            sales_root=str(sales_root),
            date=None,
            domain="__private__",
            force=False,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(spacekb_client.sync_daily(args), 0)
        files = list((sales_root / "exports/spacekb").glob("SA销售日报-*.md"))
        self.assertEqual(len(files), 1)
        self.assertIn("发送付款方案", files[0].read_text(encoding="utf-8"))
        self.assertTrue(Handler.uploads)


if __name__ == "__main__":
    unittest.main()
