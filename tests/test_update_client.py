from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sa_sales_advisor import update_client


class AutomaticUpdateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.base = self.workspace / ".spaceagents/plugins/sa-sales-advisor"
        self.current_root = self.base / "runtime-v0.12.0"
        self._make_runtime(self.current_root, "0.12.0", "当前智能体")
        update_client.atomic_json(
            self.base / "current.json",
            {
                "version": "0.12.0",
                "runtime_root": str(self.current_root),
                "cli": str(self.current_root / "sa_sales_advisor/cli.py"),
            },
        )
        customer_file = self.workspace / "SA销售工作区/customers/cus-1/customer.json"
        customer_file.parent.mkdir(parents=True)
        customer_file.write_text('{"name":"保留客户"}\n', encoding="utf-8")
        self.customer_file = customer_file

    def tearDown(self):
        self.temp.cleanup()

    def _make_runtime(self, root: Path, version: str, agent_text: str) -> None:
        for relative in update_client.REQUIRED_RUNTIME_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative == "VERSION":
                path.write_text(version + "\n", encoding="utf-8")
            elif relative == "sa_sales_advisor/templates/sales-advisor-agent.md":
                path.write_text(
                    "---\nmode: all\n---\n" + update_client.MANAGED_AGENT_MARKER + "\n" + agent_text + "\n",
                    encoding="utf-8",
                )
            else:
                path.write_text("# test\n", encoding="utf-8")

    def _runtime_archive(self, version: str = "0.12.1") -> bytes:
        root = self.workspace / "archive-source"
        self._make_runtime(root, version, "新版智能体")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as bundle:
            for file in root.rglob("*"):
                if file.is_file():
                    bundle.write(file, file.relative_to(root))
        return stream.getvalue()

    def _manifest(self, archive: bytes, checksum: str | None = None) -> dict:
        return {
            "schema_version": 1,
            "channel": "stable",
            "version": "0.12.1",
            "runtime_url": update_client.OFFICIAL_RELEASE_PREFIX
            + "v0.12.1/spaceagents-sales-advisor-runtime-v0.12.1.zip",
            "runtime_sha256": checksum or hashlib.sha256(archive).hexdigest(),
        }

    def test_updates_atomically_and_preserves_sales_data_and_old_runtime(self):
        archive = self._runtime_archive()
        manifest = self._manifest(archive)

        def fake_fetch(url: str, timeout: int = 60) -> bytes:
            del timeout
            return json.dumps(manifest).encode() if url == update_client.MANIFEST_URL else archive

        with patch.object(update_client, "fetch_bytes", side_effect=fake_fetch):
            result = update_client.check(self.workspace, 24, True, update_client.MANIFEST_URL)

        self.assertEqual(result["status"], "updated")
        current = json.loads((self.base / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["version"], "0.12.1")
        self.assertTrue((self.base / "runtime-v0.12.1/sa_sales_advisor/cli.py").is_file())
        self.assertTrue(self.current_root.is_dir())
        self.assertEqual(self.customer_file.read_text(encoding="utf-8"), '{"name":"保留客户"}\n')
        agent = self.workspace / ".opencode/agents/销售军师.md"
        self.assertIn("新版智能体", agent.read_text(encoding="utf-8"))

    def test_checksum_failure_keeps_current_runtime(self):
        archive = self._runtime_archive()
        manifest = self._manifest(archive, "0" * 64)

        def fake_fetch(url: str, timeout: int = 60) -> bytes:
            del timeout
            return json.dumps(manifest).encode() if url == update_client.MANIFEST_URL else archive

        with patch.object(update_client, "fetch_bytes", side_effect=fake_fetch):
            result = update_client.check(self.workspace, 24, True, update_client.MANIFEST_URL)

        self.assertEqual(result["status"], "update_failed")
        current = json.loads((self.base / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["version"], "0.12.0")
        self.assertFalse((self.base / "runtime-v0.12.1").exists())

    def test_check_interval_avoids_network_call(self):
        update_client.atomic_json(
            self.base / "update-state.json",
            {
                "last_checked_at": update_client.now().isoformat(timespec="seconds"),
                "last_result": "current",
            },
        )
        with patch.object(update_client, "fetch_bytes") as fetch:
            result = update_client.check(self.workspace, 24, False, update_client.MANIFEST_URL)
        self.assertEqual(result["status"], "skipped")
        fetch.assert_not_called()

    def test_preserves_unmanaged_same_name_agent(self):
        agent = self.workspace / ".opencode/agents/销售军师.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("用户自定义智能体\n", encoding="utf-8")
        archive = self._runtime_archive()
        manifest = self._manifest(archive)

        def fake_fetch(url: str, timeout: int = 60) -> bytes:
            del timeout
            return json.dumps(manifest).encode() if url == update_client.MANIFEST_URL else archive

        with patch.object(update_client, "fetch_bytes", side_effect=fake_fetch):
            result = update_client.check(self.workspace, 24, True, update_client.MANIFEST_URL)
        self.assertEqual(result["workspace_agent"], "conflict-preserved")
        self.assertEqual(agent.read_text(encoding="utf-8"), "用户自定义智能体\n")


if __name__ == "__main__":
    unittest.main()
