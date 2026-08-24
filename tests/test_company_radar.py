from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "sa_sales_advisor/cli.py"


class CompanyRadarTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "SA销售工作区"
        subprocess.run([sys.executable, str(CLI), "init", "--root", str(self.workspace)], check=True, capture_output=True)
        self.run_cli(
            "company-radar", "register", "--workspace", str(self.workspace),
            "--customer-id", "cus-000001", "--legal-name", "华新智造有限公司",
            "--credit-code", "91310000MA12345678", "--region", "上海市",
        )

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args: str) -> dict:
        result = subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_plan_covers_business_and_risk_topics(self):
        output = self.run_cli("company-radar", "plan", "--workspace", str(self.workspace), "--customer-id", "cus-000001")
        topics = {item["topic"] for item in output["queries"]}
        self.assertTrue({"招投标", "项目建设", "经营变化", "资本动态", "人才需求", "司法风险", "创新动态"} <= topics)
        self.assertEqual(output["max_results"], 100)

    def test_import_separates_verified_pending_and_rejected(self):
        payload = {
            "records": [
                {
                    "title": "华新智造设备采购中标公告", "event_type": "中标",
                    "company_name": "华新智造有限公司", "credit_code": "91310000MA12345678",
                    "region": "上海市", "published_at": "2026-08-23", "source_name": "全国公共资源交易平台",
                    "source_url": "https://data.ggzy.gov.cn/example/1", "original_accessible": True,
                    "summary": "企业作为中标人。",
                },
                {
                    "title": "搜索摘要线索", "event_type": "招聘", "company_name": "华新智造有限公司",
                    "published_at": "2026-08-22", "source_url": "https://example.com/search-result",
                    "source_level": "search_lead", "original_accessible": False,
                },
                {
                    "title": "同名企业公告", "event_type": "处罚", "company_name": "华新智造有限公司",
                    "credit_code": "91310000MA87654321", "region": "上海市", "published_at": "2026-08-21",
                    "source_url": "https://creditchina.gov.cn/example/2", "original_accessible": True,
                },
            ]
        }
        source = Path(self.temp.name) / "records.json"
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        output = self.run_cli(
            "company-radar", "import", "--workspace", str(self.workspace),
            "--customer-id", "cus-000001", "--input-file", str(source),
        )
        self.assertEqual(output["counts"], {"verified": 1, "pending": 1, "rejected": 1})
        repeated = self.run_cli(
            "company-radar", "import", "--workspace", str(self.workspace),
            "--customer-id", "cus-000001", "--input-file", str(source),
        )
        self.assertEqual(repeated["saved"], 0)
        verified = self.run_cli(
            "company-radar", "list", "--workspace", str(self.workspace),
            "--customer-id", "cus-000001", "--status", "verified",
        )
        self.assertEqual(len(verified["records"]), 1)
        self.assertIn("统一社会信用代码精确匹配", verified["records"][0]["verification_reason"])

    def test_only_verified_record_can_be_confirmed_into_timeline(self):
        self.run_cli(
            "customer", "create", "--workspace", str(self.workspace),
            "--name", "李总",
        )
        index = json.loads((self.workspace / "indexes/customer-index.json").read_text(encoding="utf-8"))
        created_id = index["customers"][0]["customer_id"]
        self.run_cli(
            "company-radar", "register", "--workspace", str(self.workspace),
            "--customer-id", created_id, "--legal-name", "华新智造有限公司",
            "--credit-code", "91310000MA12345678", "--region", "上海市",
        )
        payload = {"records": [{
            "title": "华新智造新项目备案", "event_type": "项目备案",
            "credit_code": "91310000MA12345678", "published_at": "2026-08-24",
            "source_name": "政府公开平台", "source_url": "https://example.gov.cn/project/88",
            "original_accessible": True, "summary": "企业新增生产项目备案。",
        }]}
        source = Path(self.temp.name) / "confirm.json"
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        imported = self.run_cli(
            "company-radar", "import", "--workspace", str(self.workspace),
            "--customer-id", created_id, "--input-file", str(source),
        )
        evidence_id = imported["records"][0]["evidence_id"]
        confirmed = self.run_cli(
            "company-radar", "confirm", "--workspace", str(self.workspace),
            "--customer-id", created_id, "--evidence-id", evidence_id,
        )
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertTrue(Path(confirmed["customer_file"]).is_file())
        self.assertTrue(Path(confirmed["timeline_file"]).is_file())
        self.assertIn("新增生产项目备案", Path(confirmed["customer_file"]).read_text(encoding="utf-8"))
        dashboard = self.run_cli("dashboard", "--workspace", str(self.workspace), "--date", "2026-08-24")
        page = Path(dashboard["dashboard"]).read_text(encoding="utf-8")
        self.assertIn("企业最新动态", page)
        self.assertIn("华新智造新项目备案", page)
        self.assertIn("查看原文", page)


if __name__ == "__main__":
    unittest.main()
