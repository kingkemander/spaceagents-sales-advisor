from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "sa_sales_advisor/cli.py"


class PipelineStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "SA销售工作区"
        self.run_cli("init", "--root", str(self.workspace))
        self.run_cli("customer", "create", "--workspace", str(self.workspace), "--name", "示例客户")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=check,
        )

    def patch(self, payload: dict, check: bool = True) -> subprocess.CompletedProcess[str]:
        path = Path(self.temp.name) / "patch.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return self.run_cli(
            "memory", "update", "--workspace", str(self.workspace),
            "--customer-id", "cus-000001", "--patch-file", str(path),
            check=check,
        )

    def test_pipeline_report_and_dashboard_use_customer_master_data(self):
        self.patch({
            "pipeline_stage": "报价谈判",
            "opportunity_amount": 1_000_000,
            "expected_close_date": "2026-09-01",
            "win_probability": 70,
            "next_followup_at": "2026-08-20T15:00:00+08:00",
            "next_action": "确认最终付款安排",
        })
        result = self.run_cli("pipeline", "--workspace", str(self.workspace), "--date", "2026-08-23")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["open_amount"], 1_000_000)
        self.assertEqual(payload["weighted_revenue"], 700_000)
        self.assertEqual(payload["overdue"], 1)

        report = (self.workspace / "pipeline/reports/2026-08-23.md").read_text(encoding="utf-8")
        pipeline = (self.workspace / "pipeline/pipeline.md").read_text(encoding="utf-8")
        self.assertIn("加权预计收入：700,000 CNY", report)
        self.assertIn("跟进已逾期 3 天", report)
        self.assertIn("报价谈判", pipeline)

        self.run_cli("dashboard", "--workspace", str(self.workspace), "--date", "2026-08-23")
        dashboard = (self.workspace / "dashboard/index.html").read_text(encoding="utf-8")
        self.assertIn("销售漏斗", dashboard)
        self.assertIn('"weighted_revenue": 700000.0', dashboard)

    def test_stage_change_is_audited_and_closing_sets_status(self):
        self.patch({"pipeline_stage": "赢单", "opportunity_amount": 800_000})
        index = json.loads((self.workspace / "indexes/customer-index.json").read_text(encoding="utf-8"))
        customer_path = self.workspace / index["customers"][0]["workspace_path"] / "customer.json"
        customer = json.loads(customer_path.read_text(encoding="utf-8"))
        self.assertEqual(customer["status"], "won")
        self.assertEqual(customer["win_probability"], 100)
        self.assertEqual([item["stage"] for item in customer["stage_history"]], ["初步接触", "赢单"])

    def test_rejects_invalid_pipeline_values(self):
        result = self.patch({"pipeline_stage": "随便写一个阶段", "win_probability": 120}, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pipeline_stage must be one of", result.stderr)


if __name__ == "__main__":
    unittest.main()
