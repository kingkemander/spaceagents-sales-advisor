from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "sa_sales_advisor/cli.py"


class ProactiveCoachTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "SA销售工作区"
        self.run_cli("init", "--root", str(self.workspace))

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args: str) -> dict:
        result = subprocess.run([sys.executable, str(CLI), *args], text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def create_customer(self) -> str:
        result = self.run_cli("customer", "create", "--workspace", str(self.workspace), "--name", "王总")
        return result["customer_id"]

    def test_profile_is_incremental_and_can_be_skipped(self):
        initial = self.run_cli("coach", "profile", "status", "--workspace", str(self.workspace))
        self.assertEqual(initial["next"]["field"], "business")
        self.run_cli("coach", "profile", "update", "--workspace", str(self.workspace), "--field", "business", "--value", "产业园区招商")
        after = self.run_cli("coach", "profile", "status", "--workspace", str(self.workspace))
        self.assertEqual(after["next"]["field"], "target_customer")
        self.run_cli("coach", "profile", "skip", "--workspace", str(self.workspace), "--field", "target_customer")
        skipped = self.run_cli("coach", "profile", "status", "--workspace", str(self.workspace))
        self.assertEqual(skipped["next"]["field"], "product")

    def test_casual_note_requires_confirmation_before_customer_update(self):
        customer_id = self.create_customer()
        patch = self.workspace / "patch.json"
        patch.write_text(json.dumps({"latest_update": "客户提出预算压力，需要重新比较付款安排", "objections": ["预算压力"]}, ensure_ascii=False), encoding="utf-8")
        note = self.run_cli("coach", "note", "capture", "--workspace", str(self.workspace), "--customer", "王总", "--text", "王总昨天说预算紧", "--facts", "客户明确表达预算压力", "--recommended-action", "确认可接受投入区间", "--patch-file", str(patch))
        self.assertEqual(note["status"], "pending_confirmation")
        customer_file = next((self.workspace / "customers").glob("*/customer.json"))
        self.assertNotIn("预算压力", customer_file.read_text(encoding="utf-8"))
        self.run_cli("coach", "note", "confirm", "--workspace", str(self.workspace), "--event-id", note["event"]["event_id"], "--customer-id", customer_id)
        self.assertIn("预算压力", customer_file.read_text(encoding="utf-8"))

    def test_suggestions_and_prospects_stay_separate_from_customers(self):
        self.create_customer()
        suggestions = self.run_cli("coach", "suggestions", "generate", "--workspace", str(self.workspace))
        self.assertTrue(suggestions["suggestions"])
        candidate = self.workspace / "candidate.json"
        candidate.write_text(json.dumps({"company_name": "华北智造有限公司", "source_url": "https://example.com/public", "match_reason": "符合区域与行业目标", "opening_angle": "围绕扩产项目了解空间需求"}, ensure_ascii=False), encoding="utf-8")
        imported = self.run_cli("coach", "prospects", "import", "--workspace", str(self.workspace), "--candidate-file", str(candidate))
        self.assertEqual(imported["status"], "pending_confirmation")
        self.assertEqual(len(list((self.workspace / "customers").glob("*/customer.json"))), 1)
        self.run_cli("coach", "prospects", "confirm", "--workspace", str(self.workspace), "--prospect-id", imported["candidate"]["prospect_id"])
        self.assertEqual(len(list((self.workspace / "customers").glob("*/customer.json"))), 2)


if __name__ == "__main__":
    unittest.main()
