from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PluginContractTest(unittest.TestCase):
    def test_registration_is_workspace_primary_and_has_command_fallback(self):
        manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["commands"], ["./commands/generate-sales-advisor.md"])
        self.assertNotIn("agents", manifest)

        template = (ROOT / "sa_sales_advisor/templates/sales-advisor-agent.md").read_text(encoding="utf-8")
        self.assertIn("mode: all", template)
        self.assertNotIn("mode: subagent", template)

        skill = (ROOT / "skills/sa-sales-advisor/SKILL.md").read_text(encoding="utf-8")
        self.assertIn(".opencode/agents/销售军师.md", skill)
        self.assertIn("严禁写入单数目录", skill)
        self.assertTrue((ROOT / "playbooks/manage-sales-pipeline/PLAYBOOK.md").is_file())
        cli = (ROOT / "sa_sales_advisor/cli.py").read_text(encoding="utf-8")
        self.assertIn('"pipeline": "pipeline_store.py"', cli)
        self.assertIn('"update": "update_client.py"', cli)
        self.assertIn('"system-reminder": "system_reminder.py"', cli)
        self.assertTrue((ROOT / "scripts/voice-alarm/macos/alarm-reminder.sh").is_file())

    def test_skill_uses_dynamic_runtime_pointer_and_auto_update(self):
        skill = (ROOT / "skills/sa-sales-advisor/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("current.json", skill)
        self.assertIn("每 24 小时", skill)
        self.assertIn("绝不修改 `<销售数据>`", skill)


if __name__ == "__main__":
    unittest.main()
