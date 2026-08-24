#!/bin/bash
# SA 销售军师语音闹钟：到点使用系统语音播报，并清理一次性任务。

set -u

MESSAGE="${1:-}"
REPEAT="${2:-3}"
LABEL="${3:-}"
PLIST_PATH="${4:-}"

case "$REPEAT" in
  ''|*[!0-9]*) REPEAT=3 ;;
esac
if [ "$REPEAT" -lt 1 ]; then REPEAT=1; fi
if [ "$REPEAT" -gt 5 ]; then REPEAT=5; fi

if [ -z "$MESSAGE" ]; then
  exit 1
fi

i=1
while [ "$i" -le "$REPEAT" ]; do
  /usr/bin/say "$MESSAGE"
  /bin/sleep 1
  i=$((i + 1))
done

if [ -n "$PLIST_PATH" ]; then
  /bin/rm -f "$PLIST_PATH" 2>/dev/null || true
fi
if [ -n "$LABEL" ]; then
  /bin/launchctl bootout "gui/$(/usr/bin/id -u)/$LABEL" 2>/dev/null || true
fi
