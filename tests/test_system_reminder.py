from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sa_sales_advisor import system_reminder


class SystemReminderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.message = self.workspace / "message.md"
        self.message.write_text("给吴总发送看楼时间确认。", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_time_without_date_rolls_to_future(self):
        current = datetime.now().astimezone()
        trigger = system_reminder.parse_trigger(None, current.strftime("%H:%M"))
        self.assertGreater(trigger, current)
        self.assertLess(trigger, current + timedelta(days=2))

    def test_macos_creation_is_recorded_without_touching_sales_data(self):
        tomorrow = (datetime.now().astimezone() + timedelta(days=1)).strftime("%Y-%m-%d")
        args = argparse.Namespace(
            workspace=str(self.workspace),
            title="吴总行动提醒",
            message_file=str(self.message),
            time="15:00",
            date=tomorrow,
            voice=False,
            repeat=3,
        )
        with patch.object(system_reminder.platform, "system", return_value="Darwin"), patch.object(
            system_reminder, "macos_reminder", return_value="native-test-id"
        ):
            result = system_reminder.create(args)
        self.assertEqual(result["status"], "created-system-reminder")
        self.assertEqual(result["backend"], "macos-reminders")
        index = self.workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders.jsonl"
        stored = json.loads(index.read_text(encoding="utf-8").strip())
        self.assertEqual(stored["title"], "吴总行动提醒")
        self.assertFalse((self.workspace / "SA销售工作区").exists())


if __name__ == "__main__":
    unittest.main()
