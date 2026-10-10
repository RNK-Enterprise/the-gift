# Release checklist — deploying to atlas (192.168.1.202)

One page, top to bottom, reusable for every release. Every step has an
expected result; stop at the first red one. Total time: ~10 minutes plus
the monitoring wait.

## 0. What's shipping

`main` must be clean and pushed before you start. Decide the version, then
see what changed since the last tag:

```bash
PREV=$(git describe --tags --abbrev=0)   # e.g. v1.1.0 — also the rollback target
NEW=v1.2.0                               # the version you're about to tag
git status --short                       # → empty (nothing uncommitted)
git log --oneline "$PREV"..HEAD          # → the release notes, in commit form
git diff --stat "$PREV"..HEAD -- deploy/ # → any box config to reinstall (§2)
git diff --stat "$PREV"..HEAD -- Bibles 'Study Guides' | tail -1   # → content changes, if any
```

Write the short visitor-facing summary into the README's **Changelog**
section now, and commit it, so it ships with the release.

## 1. Pre-flight (from your checkout)

```bash
python3 -m unittest test_server test_deploy_scripts test_app test_features   # → Ran 103 tests ... OK
git push origin main                                  # → pushed
```

Then check that GitHub Actions (the `test` workflow: the three suites,
`shellcheck`, and the app's JavaScript syntax check) is green on the push.

## 2. Deploy on the box

As `rnk`. The checkout is rnk-owned, so git needs no sudo (see HOSTING.md §1).

```bash
ssh rnk@192.168.1.202
cd /opt/rnk/the-gift
PREV=$(git describe --tags --abbrev=0)    # note it for the rollback
git pull --ff-only origin main            # → Fast-forward, no conflicts
git log --oneline -3                      # → same SHAs as your checkout
```

If §0 showed changes under `deploy/`, reinstall what changed:

```bash
sudo cp deploy/the-gift.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo cp deploy/gift.logrotate /etc/logrotate.d/the-gift
# deploy/gift.cron changes go through rnk-sovereign (atlas's crontab owner)
```

Then restart:

```bash
./deploy/deploy.sh                 # → "the-gift: landing page OK"
systemctl is-active the-gift       # → active
```

`deploy.sh` restarts the service and waits up to 10 s for the landing page.
If it prints anything else, go to the rollback (§6) before debugging live.

## 3. Verify on the box (LAN door)

```bash
curl -s http://127.0.0.1:8770/healthz
# → {"ok": true}

curl -s http://127.0.0.1:8770/ | grep -oE '139 translations|228 folders|15,672|21 SWORD modules'
# → all four lines (counts are computed from disk, so this also proves the
#   library tree is intact after the pull)

curl -sI http://127.0.0.1:8770/app/ | grep -iE '^HTTP|script-src'
# → 200, and a CSP with script-src 'self'

curl -s 'http://127.0.0.1:8770/api/chapter?t=KJV&b=John&c=3' | grep -o 'For God so loved the world'
curl -s 'http://127.0.0.1:8770/api/devotional?date=01-01' | grep -o 'Morning, January 1'
curl -s 'http://127.0.0.1:8770/api/search?t=KJV&q=love+one+another' | grep -o '"total":19'
# → each prints its match: the reader, the devotional and search all work

curl -s -o /dev/null -w '%{http_code}\n' -H 'Range: bytes=0-99' http://127.0.0.1:8770/Music/Hymns/audio/amazing-grace.mp3
# → 206 (audio seeks with ranges)

ss -ltnp | grep 8770
# → 127.0.0.1:8770 only: the tunnel is the one door

sudo ls -l /var/lib/the-gift/
# → owned by www-data (community.sqlite3 appears after the first sign-up)

curl -s -o /dev/null -w '%{http_code} %{size_download}\n' \
  http://127.0.0.1:8770/Bibles/formats/text/BurJudson.txt
# → 200 11965562  (a 12 MB file through the chunked path)

curl -sI http://127.0.0.1:8770/LICENSE | grep -iE 'content-type|nosniff'
# → text/plain; charset=utf-8  and  X-Content-Type-Options: nosniff

curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8770/favicon.ico
# → 200

systemctl show the-gift -p MemoryCurrent
# → low tens of MB — nowhere near the 512M ceiling

journalctl -u the-gift --since "10 min ago" --no-pager | tail -5
# → the start line, no tracebacks
```

## 4. Verify from outside (public door, through the tunnel)

From any machine **not** on the LAN:

```bash
curl -s https://gift.rnkstudios.uk/healthz
# → {"ok": true}

curl -sI https://gift.rnkstudios.uk/ | head -3
# → HTTP/2 200, server: cloudflare

curl -s -o /dev/null -w '%{http_code} %{size_download}\n' \
  https://gift.rnkstudios.uk/Bibles/formats/text/BurJudson.txt
# → 200 11965562

curl -sI https://gift.rnkstudios.uk/LICENSE | grep -i content-type
# → text/plain; charset=utf-8
```

Browser pass: open <https://gift.rnkstudios.uk/>, check the favicon in
the tab, walk one door (Bibles → text → any file), confirm it renders as
text in-browser rather than downloading. Then open
<https://gift.rnkstudios.uk/app/>: Today shows the devotional, a chapter
reads, and on a phone the browser offers to install it. Sign in with a
test account, open a group, send a message, and check it arrives.

## 5. Monitoring stays quiet, then tag

The atlas cron hits the public door every 5 minutes. Within ~10 minutes
of the restart:

```bash
# on atlas:
tail -3 /home/rnk/gift-health.log   # → "ok" lines, no DOWN after the restart
tail -3 /home/rnk/deadman.log       # → nothing new (no STALE)
```

At most one `DOWN`→`recovered` pair around the restart window is expected;
anything still down 10 minutes later is a real problem.

Once everything is green, tag and publish from your checkout. Pin the
GitHub identity per command, and never run `gh auth switch` (see
`Rnk Studios/AGENTS.md`):

```bash
T="$(gh auth token -u RNK-Enterprise)"
git tag -a "$NEW" -m "$NEW"
git push "https://x-access-token:${T}@github.com/RNK-Enterprise/the-gift.git" "$NEW"
GH_TOKEN="$T" gh release create "$NEW" \
  --repo RNK-Enterprise/the-gift --title "$NEW" --notes-from-tag
```

## 6. Rollback

Roll back to the previous tag noted in §2. That tag is a complete known-good
state, content included, and resetting to it is a local operation on the box:

```bash
cd /opt/rnk/the-gift
git reset --hard "$PREV"           # as rnk — no sudo
./deploy/deploy.sh
curl -s http://127.0.0.1:8770/healthz   # → {"ok": true}
```

If the release also reinstalled files from `deploy/` (§2), reinstall them
from the rolled-back checkout the same way. Rolling back never touches
`/var/lib/the-gift/`: accounts and groups survive, and the schema is only
ever added to, so a later release picks them up again. This leaves the box behind
origin. When you're ready to try again, `git pull --ff-only origin main`
re-advances it (it will fast-forward, not conflict).

## Sign-off

- [ ] CI green on the pushed commit (tests + shellcheck)
- [ ] Changed `deploy/` config reinstalled (or none changed)
- [ ] LAN door: healthz, counts, 12 MB file, LICENSE headers, favicon, clean journal
- [ ] Public door: healthz, 200 through the edge, big file, LICENSE
- [ ] Browser: favicon renders, .txt displays in-browser
- [ ] App: /app/ loads, devotional + chapter + search work, test group chat round-trips
- [ ] Music plays, study notes open, Plans page shows (payments configured, or "not set up yet")
- [ ] Listening on 127.0.0.1 only; HSTS present on the public door
- [ ] gift-health.log shows `ok`, deadman quiet
- [ ] Tag pushed, GitHub release published, README changelog updated
