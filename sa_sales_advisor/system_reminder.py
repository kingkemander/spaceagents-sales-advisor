#!/usr/bin/env python3
"""Create an explicit one-time reminder using macOS or Windows system services."""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import plistlib
import re
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path


def parse_trigger(date_value: str | None, time_value: str) -> datetime:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
        raise SystemExit("time must use 24-hour HH:MM format")
    current = datetime.now().astimezone()
    if date_value:
        try:
            day = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise SystemExit("date must use YYYY-MM-DD format") from exc
    else:
        day = current.date()
    hour, minute = (int(part) for part in time_value.split(":"))
    trigger = datetime.combine(day, datetime.min.time(), tzinfo=current.tzinfo).replace(hour=hour, minute=minute)
    if not date_value and trigger <= current:
        trigger += timedelta(days=1)
    if trigger <= current:
        raise SystemExit("reminder time must be in the future")
    return trigger


def macos_reminder(title: str, message: str, trigger: datetime) -> str:
    script = r'''
on run argv
  set itemTitle to item 1 of argv
  set itemBody to item 2 of argv
  set alarmDate to current date
  set year of alarmDate to (item 3 of argv as integer)
  set month of alarmDate to (item 4 of argv as integer)
  set day of alarmDate to (item 5 of argv as integer)
  set time of alarmDate to ((item 6 of argv as integer) * hours + (item 7 of argv as integer) * minutes)
  tell application "Reminders"
    set targetList to default list
    set createdItem to make new reminder at end of reminders of targetList with properties {name:itemTitle, body:itemBody, due date:alarmDate, remind me date:alarmDate}
    return id of createdItem
  end tell
end run
'''
    result = subprocess.run(
        [
            "osascript", "-", title, message,
            str(trigger.year), str(trigger.month), str(trigger.day),
            str(trigger.hour), str(trigger.minute),
        ],
        input=script,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise SystemExit(f"macOS Reminders creation failed: {result.stderr.strip()}")
    return result.stdout.strip() or "created"


def macos_voice_reminder(
    workspace: Path, reminder_id: str, title: str, message: str, trigger: datetime, repeat: int
) -> str:
    reminder_dir = workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders"
    reminder_dir.mkdir(parents=True, exist_ok=True)
    label = "com.spaceagents.salesadvisor." + reminder_id.replace("-", "")
    launch_agents = Path.home() / "Library/LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents / f"{label}.plist"
    alarm_script = Path(__file__).resolve().parents[1] / "scripts/voice-alarm/macos/alarm-reminder.sh"
    if not alarm_script.is_file():
        raise SystemExit("bundled macOS voice alarm script is missing")
    payload = {
        "Label": label,
        "ProgramArguments": [
            "/bin/bash", str(alarm_script), message, str(repeat), label, str(plist_path), title
        ],
        "StartCalendarInterval": {
            "Month": trigger.month,
            "Day": trigger.day,
            "Hour": trigger.hour,
            "Minute": trigger.minute,
        },
        "RunAtLoad": False,
        "StandardOutPath": str(reminder_dir / f"{reminder_id}.out.log"),
        "StandardErrorPath": str(reminder_dir / f"{reminder_id}.error.log"),
    }
    with plist_path.open("wb") as handle:
        plistlib.dump(payload, handle)
    result = subprocess.run(
        ["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        plist_path.unlink(missing_ok=True)
        raise SystemExit(f"macOS scheduled voice reminder failed: {result.stderr.strip()}")
    return label


def powershell_encoded(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def windows_reminder(
    workspace: Path, reminder_id: str, title: str, message: str, trigger: datetime, voice: bool = False
) -> str:
    reminder_dir = workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders"
    reminder_dir.mkdir(parents=True, exist_ok=True)
    alert_file = reminder_dir / f"{reminder_id}.ps1"
    task_name = f"SA Sales Advisor {reminder_id}"
    title64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
    message64 = base64.b64encode(message.encode("utf-8")).decode("ascii")
    voice_lines = (
        "Add-Type -AssemblyName System.Speech\n"
        "$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$speaker.Speak($message)\n"
        if voice else ""
    )
    alert_content = (
        "$title=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + title64 + "'))\n"
        "$message=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + message64 + "'))\n"
        + "$taskName='" + task_name.replace("'", "''") + "'\n"
        + "[console]::Beep(880,500)\n"
        + voice_lines
        + "Add-Type -AssemblyName PresentationFramework\n"
        + "[System.Windows.MessageBox]::Show($message,$title,'OK','Information') | Out-Null\n"
        + "Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue\n"
        + "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n"
    )
    alert_file.write_text(alert_content, encoding="utf-8-sig")
    path_literal = str(alert_file).replace("'", "''")
    task_literal = task_name.replace("'", "''")
    when = trigger.strftime("%Y-%m-%dT%H:%M:%S")
    registration = f"""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "{path_literal}"'
$trigger = New-ScheduledTaskTrigger -Once -At ([datetime]::ParseExact('{when}','yyyy-MM-ddTHH:mm:ss',[Globalization.CultureInfo]::InvariantCulture))
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName '{task_literal}' -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", powershell_encoded(registration)],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        alert_file.unlink(missing_ok=True)
        raise SystemExit(f"Windows Task Scheduler creation failed: {result.stderr.strip()}")
    return task_name


def append_index(workspace: Path, entry: dict) -> None:
    path = workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def create(args: argparse.Namespace) -> dict:
    workspace = Path(args.workspace).expanduser().resolve()
    message = Path(args.message_file).expanduser().read_text(encoding="utf-8").strip()
    if not message:
        raise SystemExit("message file is empty")
    trigger = parse_trigger(args.date, args.time)
    reminder_id = "sa-" + uuid.uuid4().hex[:12]
    system = platform.system()
    if system == "Darwin":
        if args.voice:
            native_id = macos_voice_reminder(
                workspace, reminder_id, args.title.strip(), message, trigger, args.repeat
            )
            backend = "macos-launchd-voice"
        else:
            native_id = macos_reminder(args.title.strip(), message, trigger)
            backend = "macos-reminders"
    elif system == "Windows":
        native_id = windows_reminder(workspace, reminder_id, args.title.strip(), message, trigger, args.voice)
        backend = "windows-task-scheduler-voice" if args.voice else "windows-task-scheduler"
    else:
        raise SystemExit("system reminder fallback currently supports macOS and Windows only")
    result = {
        "status": "created-system-reminder",
        "reminder_id": reminder_id,
        "native_id": native_id,
        "backend": backend,
        "title": args.title.strip(),
        "trigger_at": trigger.isoformat(timespec="minutes"),
        "voice": bool(args.voice),
        "repeat": args.repeat if args.voice else 0,
    }
    append_index(workspace, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a native one-time sales reminder")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--message-file", required=True)
    parser.add_argument("--time", required=True)
    parser.add_argument("--date")
    parser.add_argument("--voice", action="store_true", help="Play a spoken reminder at the scheduled time")
    parser.add_argument("--repeat", type=int, default=3, choices=range(1, 6))
    args = parser.parse_args()
    if not args.title.strip():
        raise SystemExit("title is required")
    print(json.dumps(create(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
