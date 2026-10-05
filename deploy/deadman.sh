#!/bin/bash
# deadman — logs when gift-healthcheck.sh's output goes stale on atlas.
#
# Generic by design (name|path|max_age_minutes watch entries, space-separated
# for more than one), but the default here only watches this project's own
# health-check writer — it is not a general atlas monitoring script. If atlas
# ends up needing a shared deadman switch across multiple projects, that
# belongs in a shared ops repo, not vendored into each project that uses it.
#
# Cron runs it a couple minutes offset from the writers it watches. For each
# watch entry it checks the file's mtime; entering or leaving staleness is
# logged once to deadman.log. Touches a heartbeat file every pass — if
# deadman itself dies, that file goes stale and a human (or a future
# watcher) can tell.
#
# Every STALE/RECOVERED event is also emailed (same sendmail path and
# recipient as gift-healthcheck.sh). DEADMAN_NOTIFY="some-command" replaces
# the email with a command that receives the event line on argv;
# DEADMAN_NOTIFY=none keeps it log-only.
#
# Override for testing: DEADMAN_WATCH, DEADMAN_STATE, DEADMAN_LOG, DEADMAN_BEAT,
# DEADMAN_EMAIL, DEADMAN_SENDMAIL.

WATCH="${DEADMAN_WATCH:-gift-health|/home/rnk/gift-health.log|11}"
STATE="${DEADMAN_STATE:-/home/rnk/.deadman.state}"
LOG="${DEADMAN_LOG:-/home/rnk/deadman.log}"
BEAT="${DEADMAN_BEAT:-/home/rnk/.deadman.last-run}"
EMAIL="${DEADMAN_EMAIL:-bd@rnk-enterprise.us}"
SENDMAIL="${DEADMAN_SENDMAIL:-sendmail}"

now=$(date +%s)
touch "$BEAT" 2>/dev/null || true
[ -f "$STATE" ] || : > "$STATE"

state_has() { grep -qFx "$1 stale" "$STATE" 2>/dev/null; }
state_del() {
    local tmp
    tmp=$(mktemp) && grep -vFx "$1 stale" "$STATE" > "$tmp" 2>/dev/null && mv "$tmp" "$STATE"
}
notify_email() {
    if ! command -v "${SENDMAIL%% *}" >/dev/null 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: mailer '$SENDMAIL' not found — alert NOT sent" >> "$LOG"
        return 1
    fi
    ${SENDMAIL} -t <<EOF
From: The Gift <gift@rnkstudios.uk>
To: ${EMAIL}
Subject: [deadman] ${1%% — *}
Content-Type: text/plain; charset=utf-8

${1}

-- 
deadman on $(hostname)
EOF
}
emit() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
    case "${DEADMAN_NOTIFY:-}" in
        none) ;;
        "")   notify_email "$1" ;;
        *)    "$DEADMAN_NOTIFY" "$1" >/dev/null 2>&1 ;;
    esac
}

for entry in $WATCH; do
    IFS='|' read -r name path maxage <<<"$entry"
    if [ -f "$path" ]; then
        age=$(( (now - $(stat -c %Y "$path" 2>/dev/null || echo "$now")) / 60 ))
    else
        age=999999  # missing file is maximally stale
    fi
    if [ "$age" -gt "$maxage" ]; then
        state_has "$name" || {
            echo "$name stale" >> "$STATE"
            emit "STALE: $name — $path not written for ${age} min (limit ${maxage} min)"
        }
    else
        if state_has "$name"; then
            state_del "$name"
            emit "RECOVERED: $name — $path fresh again (last write ${age} min ago)"
        fi
    fi
done
