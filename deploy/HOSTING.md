# Hosting The Gift on atlas (192.168.1.202)

The Gift is a **static library** — no build step, no packages, no database.
One stdlib-only Python process serves everything: a landing page with real
library counts, browsable listings, and the files themselves. "atlas" and
"192.168.1.202" are the same box throughout these docs: the service, the
Cloudflare tunnel connector, and the monitoring cron jobs all run there.

The server never exposes `.git`/`.claude`/`.freebuff`, the private `model/`
folder, `deploy/`, or anything outside the library root (symlinks included).

Everything installed on the box lives in `deploy/` as a real file, so the box
can be rebuilt from the repo and nothing drifts silently:

| File | Installed as |
|---|---|
| `the-gift.service` | `/etc/systemd/system/the-gift.service` |
| `gift.cron` | rnk's crontab lines (installed via rnk-sovereign) |
| `gift.logrotate` | `/etc/logrotate.d/the-gift` |

## 1. Layout and ownership

```bash
sudo mkdir -p /opt/rnk && sudo chown rnk:rnk /opt/rnk
# as rnk: clone the repo — git clone carries the whole library (Bibles/formats is tracked)
git clone https://github.com/lisasdungeon/the-gift.git /opt/rnk/the-gift
```

The checkout is **owned by `rnk`**, the same user that runs the cron jobs.
Every git command in these docs (`pull`, `reset`) runs as `rnk`, without
sudo. The service runs as `www-data` and only needs read access, which a
default clone (world-readable files) already gives it. Only `systemctl`
needs sudo.

## 2. systemd service

```bash
sudo cp deploy/the-gift.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now the-gift
curl -s http://127.0.0.1:8770/ | grep -o '<h1>[^<]*</h1>'   # → <h1>The Gift</h1>
```

After editing `deploy/the-gift.service`, repeat the `cp` and `daemon-reload`
steps. Logs go to the journal (`journalctl -u the-gift`): errors always,
a summary line whenever requests are refused with 503, and per-request
lines only if `GIFT_ACCESS_LOG=1` is set in the unit.

## 3. Verify from another machine

```bash
curl -s http://192.168.1.202:8770/healthz               # → {"ok": true}
curl -sI http://192.168.1.202:8770/Bibles/formats/text/AKJV.txt | head -3
# browser: http://192.168.1.202:8770/ — landing page, browse into any folder
```

If the box has a firewall, open 8770 (e.g. `sudo ufw allow 8770`).

## 4. Redeploy

```bash
./deploy/deploy.sh    # restart the service, then smoke-check the landing page
```

For a real release (full verification, public-door checks, rollback plan)
follow the checklist in [deploy/RELEASE.md](RELEASE.md).

## 5. Public name (live)

The hub links `https://gift.rnkstudios.uk` — this is live via the
`rnkstudios-web` Cloudflare tunnel whose connector runs on atlas under pm2
(`rnkstudios-web-tunnel`, config `~/.cloudflared/rnkstudios-web.yml`). Its
ingress already maps the hostname to this service:

```yaml
  - hostname: gift.rnkstudios.uk
    service: http://localhost:8770
```

TLS terminates at Cloudflare's edge (public cert, auto-renewed) and the
connector dials out, so there is nothing to forward or install on the box —
no Caddy needed. To change the mapping, edit `rnkstudios-web.yml` and
`pm2 restart rnkstudios-web-tunnel`.

Verify:

```bash
curl -s https://gift.rnkstudios.uk/healthz          # → {"ok": true}
curl -sI https://gift.rnkstudios.uk/ | head -3      # HTTP/2 200, server: cloudflare
```

Both doors serve the same library: the LAN address for local use, the
public name for the world. Bulk/programmatic access (the per-book
files, the 1.2 GB python tree) should `git clone` the repo. The HTTP
server streams files in chunks but has no range/resume support, by
design.

## 6. Monitoring

Two cron jobs on atlas, both scoped to this project only. The exact lines are
in `deploy/gift.cron`, and they run the scripts straight from the checkout,
so a `git pull` updates them:

- `deploy/gift-healthcheck.sh` runs every 5 minutes. It hits the public
  `/healthz` door, which catches service, tunnel, DNS and edge failures
  alike. It emails on the transition to down, once an hour while still down,
  and once on recovery. It also emails if the deadman switch's heartbeat
  (`/home/rnk/.deadman.last-run`) goes stale for more than 15 minutes.
  Logs to `/home/rnk/gift-health.log`.
- `deploy/deadman.sh` watches the healthcheck's log for staleness, which
  would mean cron itself has stopped running it. It logs and emails
  `STALE`/`RECOVERED` transitions to `/home/rnk/deadman.log`. The two
  scripts watch each other, so neither can die silently.

Both logs are rotated weekly by `deploy/gift.logrotate`.

`/healthz` is deliberately **exempt from the concurrency cap**. It answers
"is the process up?", and a server that is busy refusing requests with 503
is still up. Saturation shows up in the journal instead, as a
`refused N request(s) with 503` line at most once a minute.

Neither script is a general atlas monitoring tool. If other projects on
atlas need the same deadman-switch pattern, that belongs in a shared ops
repo, not copied into each project's `deploy/`.

**Known divergence (since v1.1.0):** the copy actually running as
`~/deadman.sh` on atlas is older. It additionally watches atlas-wide
`sysstat` daily stats (`sa$(date +%d)`, 25-min limit) alongside
gift-health, and it does not email. That sysstat watch is an atlas
concern, and atlas's crontab is managed by rnk-sovereign, so it should
move to that layer rather than grow inside this repo. Until then,
**do not sync deploy/deadman.sh over ~/deadman.sh**, and leave the
commented-out deadman line in `deploy/gift.cron` inactive; either would
silently drop the sysstat watch. gift-health itself is watched
identically by both copies. If the old copy does not touch
`/home/rnk/.deadman.last-run`, the healthcheck will send one
`[WARN] gift deadman switch not running` email. That is the cross-watch
correctly reporting that the repo's deadman isn't the one running.


## 7. Bible chat (Domain + grounded adapter)

Private stack on atlas (not in the public git tree — lives under `~/gift-model/`
and `~/bible-train/`):

| Piece | Where |
|---|---|
| llama-server (CPU, `-ngl 0`) | pm2 `gift-bible-llama` → `127.0.0.1:8081` |
| Grounded FastAPI adapter | pm2 `gift-bible-adapter` → `127.0.0.1:8000` |
| Verse index | `~/gift-model/data/verses-pd.db` |
| GGUF | `~/gift-model/gguf/bible-1.7b-q4_k_m.gguf` (falls back to base Qwen3-1.7B until fine-tune finishes) |
| Domain model id | `bible-1.7b` in `~/curator-runtime/server/data/models.json` |

Chat UI is the existing Domain API on `:4000`. Pick **The Gift — Bible Study**.
Public doors:

- `https://alpha.rnk-enterprise.us/` (API under `/api`, already tunneled)
- `gift-chat.rnkstudios.uk` is configured in `~/.cloudflared/rnkstudios-web.yml`
  → `:4000`; create the Cloudflare public-hostname/DNS for that name in the
  `rnkstudios.uk` zone (atlas `cloudflared` is logged into a different zone
  and cannot create it automatically).

Fine-tune / retrain: `~/bible-train/launch_train.sh` then
`~/bible-train/finish_pipeline.sh` (detached). When the pipeline completes it
copies the GGUF into `gift-model`, restarts `gift-bible-llama`, and brings
`ld-lore-llm` back (training borrows that GPU).
