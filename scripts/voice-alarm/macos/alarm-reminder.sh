#!/bin/bash
# SA 销售军师语音闹钟：提示音 + 系统 TTS + 通知横幅 + 一次性任务自清理。

set -u

MESSAGE="${1:-该做今天安排的销售动作了，你完成了吗？}"
REPEAT="${2:-3}"
LABEL="${3:-}"
PLIST_PATH="${4:-}"
TITLE="${5:-销售闹钟}"

case "$REPEAT" in
  ''|*[!0-9]*) REPEAT=3 ;;
esac
if [ "$REPEAT" -lt 1 ]; then REPEAT=1; fi
if [ "$REPEAT" -gt 5 ]; then REPEAT=5; fi

i=1
while [ "$i" -le "$REPEAT" ]; do
  /usr/bin/afplay /System/Library/Sounds/Glass.aiff 2>/dev/null || true
  /usr/bin/say "$MESSAGE"
  /bin/sleep 1
  i=$((i + 1))
done

/usr/bin/osascript - "$TITLE" "$MESSAGE" <<'APPLESCRIPT' 2>/dev/null || true
on run argv
  display notification (item 2 of argv) with title (item 1 of argv)
end run
APPLESCRIPT

if [ -n "$PLIST_PATH" ]; then
  /bin/rm -f "$PLIST_PATH" 2>/dev/null || true
fi
if [ -n "$LABEL" ]; then
  /bin/launchctl bootout "gui/$(/usr/bin/id -u)/$LABEL" 2>/dev/null || true
fi
