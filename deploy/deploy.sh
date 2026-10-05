#!/usr/bin/env bash
# Run on the host box (atlas, 192.168.1.202), from /opt/rnk/the-gift, to
# redeploy after a git pull. One stdlib process serves the landing page, the
# listings, and the files — no build step.
set -euo pipefail

if systemctl is-active --quiet the-gift; then
  sudo systemctl restart the-gift
else
  sudo systemctl enable --now the-gift
fi

# the first landing-page hit walks the python tree to count files, so give
# the restart a few seconds rather than a single fixed sleep
for _ in $(seq 1 10); do
  if curl -sf -m 10 http://127.0.0.1:8770/ | grep -q "<h1>The Gift</h1>"; then
    echo "the-gift: landing page OK"
    exit 0
  fi
  sleep 1
done
echo "the-gift: landing page NOT answering after restart — see: journalctl -u the-gift -n 50" >&2
exit 1
