#!/bin/bash
# Compatibility entry for the standalone SalesVoiceAlarm Skill.
# Preferred plugin entry: cli.py system-reminder ... --voice

set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo '用法: schedule-alarm.sh "播报内容" "MM-DD HH:MM" [重复次数]' >&2
  exit 2
fi

MESSAGE="$1"
TIME_STR="$2"
REPEAT="${3:-3}"
RUNTIME_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
MESSAGE_FILE="$(mktemp -t sa-sales-alarm-message).txt"
trap '/bin/rm -f "$MESSAGE_FILE"' EXIT
/usr/bin/printf '%s\n' "$MESSAGE" > "$MESSAGE_FILE"

TARGET_DATE="$(/usr/bin/python3 - "$TIME_STR" <<'PY'
from datetime import datetime
import sys
now = datetime.now().astimezone()
candidate = datetime.strptime(f"{now.year}-{sys.argv[1]}", "%Y-%m-%d %H:%M").replace(tzinfo=now.tzinfo)
if candidate <= now:
    candidate = candidate.replace(year=now.year + 1)
print(candidate.strftime("%Y-%m-%d"))
PY
)"
TIME_ONLY="${TIME_STR##* }"

/usr/bin/python3 "$RUNTIME_ROOT/sa_sales_advisor/cli.py" system-reminder \
  --workspace "${SA_WORKSPACE_ROOT:-$PWD}" \
  --title "销售闹钟" \
  --message-file "$MESSAGE_FILE" \
  --date "$TARGET_DATE" \
  --time "$TIME_ONLY" \
  --voice \
  --repeat "$REPEAT"
