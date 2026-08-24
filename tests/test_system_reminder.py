from __future__ import annotations

import argparse
import json
import plistlib
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
            repeat=3,
            schedule="once",
        )
        with patch.object(system_reminder.platform, "system", return_value="Darwin"), patch.object(
            system_reminder, "macos_voice_reminder", return_value="native-test-id"
        ):
            result = system_reminder.create(args)
        self.assertEqual(result["status"], "created-system-reminder")
        self.assertEqual(result["backend"], "macos-launchd-live-voice")
        self.assertFalse(result["audio_pre_generated"])
        self.assertTrue(result["synthesis_at_trigger"])
        index = self.workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders.jsonl"
        stored = json.loads(index.read_text(encoding="utf-8").strip())
        self.assertEqual(stored["title"], "吴总行动提醒")
        self.assertFalse((self.workspace / "SA销售工作区").exists())

    def test_macos_daily_voice_uses_launchd_without_self_cleanup(self):
        trigger = datetime.now().astimezone() + timedelta(days=1)
        fake_result = argparse.Namespace(returncode=0, stdout="", stderr="")
        with patch.object(system_reminder.Path, "home", return_value=self.workspace), patch.object(
            system_reminder.subprocess, "run", return_value=fake_result
        ):
            label = system_reminder.macos_voice_reminder(
                self.workspace, "sa-testdaily", "每日提醒", "该回客户消息了", trigger, 3, "daily"
            )
        plist_path = self.workspace / "Library/LaunchAgents" / f"{label}.plist"
        with plist_path.open("rb") as handle:
            payload = plistlib.load(handle)
        self.assertEqual(payload["StartCalendarInterval"], {"Hour": trigger.hour, "Minute": trigger.minute})
        self.assertEqual(payload["ProgramArguments"][2], "该回客户消息了")
        self.assertEqual(payload["ProgramArguments"][4:6], ["", ""])
        self.assertIn("Library/Application Support/SalesVoiceAlarm", payload["ProgramArguments"][1])
        self.assertNotIn(".spaceagents", " ".join(payload["ProgramArguments"]))
        deployed = self.workspace / "Library/Application Support/SalesVoiceAlarm/alarm-reminder.sh"
        self.assertTrue(deployed.is_file())
        self.assertIn('/usr/bin/say "$MESSAGE"', deployed.read_text(encoding="utf-8"))
        self.assertFalse(list(self.workspace.rglob("*.aiff")))

    def test_windows_pre_generates_audio_and_repeats_without_popup(self):
        trigger = datetime.now().astimezone() + timedelta(days=1)
        fake_result = argparse.Namespace(returncode=0, stdout="", stderr="")
        audio_path = self.workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders/sa-win.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"RIFF-test")
        with patch.object(system_reminder.subprocess, "run", return_value=fake_result):
            system_reminder.windows_reminder(
                self.workspace, "sa-win", "行动提醒", "该回客户消息了", trigger, 3, "once"
            )
        script = self.workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders/sa-win.ps1"
        content = script.read_text(encoding="utf-8-sig")
        self.assertIn("1..3 | ForEach-Object", content)
        self.assertIn("SoundPlayer", content)
        self.assertNotIn("NotifyIcon", content)
        self.assertNotIn("MessageBox", content)


if __name__ == "__main__":
    unittest.main()
