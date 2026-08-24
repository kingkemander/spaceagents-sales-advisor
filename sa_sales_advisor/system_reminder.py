#!/usr/bin/env python3
"""Pre-generate audio reminders and schedule local playback on macOS or Windows."""

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


def macos_voice_reminder(
    workspace: Path,
    reminder_id: str,
    title: str,
    message: str,
    trigger: datetime,
    repeat: int,
    schedule: str,
) -> str:
    reminder_dir = workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders"
    reminder_dir.mkdir(parents=True, exist_ok=True)
    label = "com.spaceagents.salesadvisor." + reminder_id.replace("-", "")
    launch_agents = Path.home() / "Library/LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents / f"{label}.plist"
    audio_path = reminder_dir / f"{reminder_id}.aiff"
    alarm_script = Path(__file__).resolve().parents[1] / "scripts/voice-alarm/macos/alarm-reminder.sh"
    if not alarm_script.is_file():
        raise SystemExit("bundled macOS voice alarm script is missing")
    synthesis = subprocess.run(
        ["/usr/bin/say", "-o", str(audio_path), message],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if synthesis.returncode != 0 or not audio_path.is_file():
        audio_path.unlink(missing_ok=True)
        raise SystemExit(f"macOS reminder audio generation failed: {synthesis.stderr.strip()}")
    calendar: dict[str, int] = {"Hour": trigger.hour, "Minute": trigger.minute}
    if schedule == "once":
        calendar.update({"Month": trigger.month, "Day": trigger.day})
    elif schedule == "weekly":
        calendar["Weekday"] = (trigger.weekday() + 1) % 7
    cleanup_label = label if schedule == "once" else ""
    cleanup_plist = str(plist_path) if schedule == "once" else ""
    payload = {
        "Label": label,
        "ProgramArguments": [
            "/bin/bash",
            str(alarm_script),
            str(audio_path),
            str(repeat),
            cleanup_label,
            cleanup_plist,
            str(audio_path) if schedule == "once" else "",
        ],
        "StartCalendarInterval": calendar,
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
        audio_path.unlink(missing_ok=True)
        raise SystemExit(f"macOS scheduled voice reminder failed: {result.stderr.strip()}")
    return label


def powershell_encoded(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def windows_reminder(
    workspace: Path,
    reminder_id: str,
    title: str,
    message: str,
    trigger: datetime,
    repeat: int = 3,
    schedule: str = "once",
) -> str:
    reminder_dir = workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders"
    reminder_dir.mkdir(parents=True, exist_ok=True)
    alert_file = reminder_dir / f"{reminder_id}.ps1"
    audio_file = reminder_dir / f"{reminder_id}.wav"
    task_name = f"SA Sales Advisor {reminder_id}"
    message64 = base64.b64encode(message.encode("utf-8")).decode("ascii")
    cleanup_lines = (
        "Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue\n"
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n"
        "Remove-Item -LiteralPath $audioPath -Force -ErrorAction SilentlyContinue\n"
        if schedule == "once" else ""
    )
    audio_literal = str(audio_file).replace("'", "''")
    alert_content = (
        "$taskName='" + task_name.replace("'", "''") + "'\n"
        + "$audioPath='" + audio_literal + "'\n"
        + "$player=New-Object System.Media.SoundPlayer $audioPath\n"
        + "1.." + str(repeat) + " | ForEach-Object { $player.PlaySync() }\n"
        + cleanup_lines
    )
    alert_file.write_text(alert_content, encoding="utf-8-sig")
    synthesis_script = (
        "Add-Type -AssemblyName System.Speech\n"
        "$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$message=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + message64 + "'))\n"
        "$speaker.SetOutputToWaveFile('" + audio_literal + "')\n"
        "$speaker.Speak($message)\n"
        "$speaker.Dispose()\n"
    )
    synthesis = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", powershell_encoded(synthesis_script)],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if synthesis.returncode != 0 or not audio_file.is_file():
        alert_file.unlink(missing_ok=True)
        audio_file.unlink(missing_ok=True)
        raise SystemExit(f"Windows reminder audio generation failed: {synthesis.stderr.strip()}")
    path_literal = str(alert_file).replace("'", "''")
    task_literal = task_name.replace("'", "''")
    when = trigger.strftime("%Y-%m-%dT%H:%M:%S")
    if schedule == "once":
        trigger_command = f"New-ScheduledTaskTrigger -Once -At ([datetime]::ParseExact('{when}','yyyy-MM-ddTHH:mm:ss',[Globalization.CultureInfo]::InvariantCulture))"
    elif schedule == "daily":
        trigger_command = f"New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact('{when}','yyyy-MM-ddTHH:mm:ss',[Globalization.CultureInfo]::InvariantCulture))"
    else:
        weekday = trigger.strftime("%A")
        trigger_command = f"New-ScheduledTaskTrigger -Weekly -DaysOfWeek {weekday} -At ([datetime]::ParseExact('{when}','yyyy-MM-ddTHH:mm:ss',[Globalization.CultureInfo]::InvariantCulture))"
    registration = f"""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "{path_literal}"'
$trigger = {trigger_command}
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
        audio_file.unlink(missing_ok=True)
        raise SystemExit(f"Windows Task Scheduler creation failed: {result.stderr.strip()}")
    return task_name


def append_index(workspace: Path, entry: dict) -> None:
    path = workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_index(workspace: Path) -> list[dict]:
    path = workspace / ".spaceagents/plugins/sa-sales-advisor/system-reminders.jsonl"
    if not path.is_file():
        return []
    latest: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        reminder_id = str(item.get("reminder_id", ""))
        if reminder_id:
            latest[reminder_id] = item
    return sorted(latest.values(), key=lambda item: str(item.get("trigger_at", "")))


def create(args: argparse.Namespace) -> dict:
    workspace = Path(args.workspace).expanduser().resolve()
    message = Path(args.message_file).expanduser().read_text(encoding="utf-8").strip()
    if not message:
        raise SystemExit("message file is empty")
    if len(message) > 300:
        raise SystemExit("desktop reminder message must be 300 characters or fewer")
    trigger = parse_trigger(args.date, args.time)
    reminder_id = "sa-" + uuid.uuid4().hex[:12]
    system = platform.system()
    if system == "Darwin":
        native_id = macos_voice_reminder(
            workspace,
            reminder_id,
            args.title.strip(),
            message,
            trigger,
            args.repeat,
            args.schedule,
        )
        backend = "macos-launchd-audio"
    elif system == "Windows":
        native_id = windows_reminder(
            workspace,
            reminder_id,
            args.title.strip(),
            message,
            trigger,
            args.repeat,
            args.schedule,
        )
        backend = "windows-task-scheduler-audio"
    else:
        raise SystemExit("system reminder fallback currently supports macOS and Windows only")
    result = {
        "status": "created-system-reminder",
        "reminder_id": reminder_id,
        "native_id": native_id,
        "backend": backend,
        "title": args.title.strip(),
        "trigger_at": trigger.isoformat(timespec="minutes"),
        "voice": True,
        "audio_pre_generated": True,
        "repeat": args.repeat,
        "schedule": args.schedule,
    }
    append_index(workspace, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an audible desktop sales reminder")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--title")
    parser.add_argument("--message-file")
    parser.add_argument("--time")
    parser.add_argument("--date")
    parser.add_argument("--schedule", choices=["once", "daily", "weekly"], default="once")
    parser.add_argument("--repeat", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if args.list:
        print(json.dumps({"status": "ok", "reminders": list_index(workspace)}, ensure_ascii=False, indent=2))
        return 0
    if not args.title or not args.title.strip():
        raise SystemExit("title is required")
    if not args.message_file or not args.time:
        raise SystemExit("message-file and time are required")
    print(json.dumps(create(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
