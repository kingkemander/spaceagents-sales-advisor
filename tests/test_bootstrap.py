from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import bootstrap


class WorkspaceAgentInstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        (self.runtime / "agents").mkdir(parents=True)
        self.source = self.runtime / "agents/销售军师.md"

    def tearDown(self):
        self.temp.cleanup()

    def test_installs_and_updates_managed_workspace_agent(self):
        self.source.write_text(
            "---\nmode: primary\n---\n" + bootstrap.MANAGED_AGENT_MARKER + "\n第一版\n",
            encoding="utf-8",
        )
        workspace = self.root / "workspace"
        result = bootstrap.install_workspace_agent(workspace, self.runtime)
        destination = workspace / ".opencode/agents/销售军师.md"
        self.assertEqual(result["workspace_agent"], "installed")
        self.assertEqual(result["workspace_agent_path"], str(destination))
        self.assertIn("mode: primary", destination.read_text(encoding="utf-8"))

        self.source.write_text(
            "---\nmode: primary\n---\n" + bootstrap.MANAGED_AGENT_MARKER + "\n第二版\n",
            encoding="utf-8",
        )
        result = bootstrap.install_workspace_agent(workspace, self.runtime)
        self.assertEqual(result["workspace_agent"], "installed")
        self.assertIn("第二版", destination.read_text(encoding="utf-8"))

    def test_preserves_unmanaged_agent_with_same_name(self):
        self.source.write_text(
            "---\nmode: primary\n---\n" + bootstrap.MANAGED_AGENT_MARKER + "\n插件版本\n",
            encoding="utf-8",
        )
        workspace = self.root / "workspace"
        destination = workspace / ".opencode/agents/销售军师.md"
        destination.parent.mkdir(parents=True)
        destination.write_text("用户自己的智能体\n", encoding="utf-8")
        result = bootstrap.install_workspace_agent(workspace, self.runtime)
        self.assertEqual(result["workspace_agent"], "conflict-preserved")
        self.assertEqual(destination.read_text(encoding="utf-8"), "用户自己的智能体\n")


if __name__ == "__main__":
    unittest.main()
