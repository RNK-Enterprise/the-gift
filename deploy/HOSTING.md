# Hosting The Gift on atlas (192.168.1.202)

The Gift is a **library plus an app**: no build step and no packages.
One stdlib-only Python process serves everything: a landing page with real
library counts, browsable listings, the files themselves, and the app at
`/app/` with its JSON API under `/api/`. The app's accounts and study
groups, uploads and plans are the only state, in `/var/lib/the-gift` (§7). "atlas" and
"192.168.1.202" are the same box throughout these docs: the service, the
Cloudflare tunnel connector, and the monitoring cron jobs all run there.

The server never exposes `.git`/`.claude`/`.freebuff`/`.data`, the private
`model/` folder, `deploy/`, or anything outside the library root (symlinks
included). It listens on 127.0.0.1 only; the Cloudflare tunnel is the
one way in (§3, §8).

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
git clone https://github.com/RNK-Enterprise/the-gift.git /opt/rnk/the-gift
```

The repository moved from `lisasdungeon/the-gift` to `RNK-Enterprise/the-gift`
(the old name redirects). On a checkout cloned before the move, point it at
the new home once, as `rnk`:
`git -C /opt/rnk/the-gift remote set-url origin https://github.com/RNK-Enterprise/the-gift.git`

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
steps, then `sudo systemctl restart the-gift`. Logs go to the journal (`journalctl -u the-gift`): errors always,
a summary line whenever requests are refused with 503, and per-request
lines only if `GIFT_ACCESS_LOG=1` is set in the unit.

## 3. Only one door: zero trust

The service listens on **127.0.0.1 only** (`GIFT_HOST=127.0.0.1` in the
unit). The single way in is the Cloudflare tunnel (§5), whose connector
runs on this box: every visitor arrives over TLS, and nothing on the LAN
is trusted or even reachable. (Before v1.3 the LAN door
`http://192.168.1.202:8770/` was open; it is now closed on purpose. For a
temporary LAN door, set `GIFT_HOST=0.0.0.0`; but sessions on plain http
are a risk, so don't leave it that way.)

Check on the box:

```bash
curl -s http://127.0.0.1:8770/healthz               # → {"ok": true}
ss -ltnp | grep 8770                                # → 127.0.0.1:8770 only
```

If `~/.cloudflared/rnkstudios-web.yml` points at `http://localhost:8770`,
prefer `http://127.0.0.1:8770` so the connector never tries IPv6 `::1`.

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

The public name is the only door (see §3). Bulk/programmatic access (the
per-book files, the 1.2 GB python tree) should `git clone` the repo. The
HTTP server streams files in chunks and has no range/resume support for
library files, by design; audio (hymns, songs) is the exception, because
players seek with ranges.

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


## 7. The app's data

The unit sets `StateDirectory=the-gift`, so systemd creates
`/var/lib/the-gift/` owned by `www-data`, and `GIFT_DATA_DIR` points the
server there. It is the service's only writable path. Inside:

- `community.sqlite3` (WAL mode, so also `-wal`/`-shm`): accounts
  (username, name, scrypt password hash, bio, picture, favourite verse),
  sessions (hashed tokens, device type, last used), groups, roles,
  messages, friends, blocks, reports, chapters read, plan ticks, sync
  backups (journal entries are **ciphertext**: encrypted on the device),
  subscriptions, artists, songs, church enquiries and the audit log. No
  email addresses (except church enquiries, which people type in), no
  locations, no card details.
- `media/`: uploaded pictures and songs, named by random ids.

**Back up** both; the database with SQLite's online backup, safe while
the service runs:

```bash
sudo -u www-data python3 -c "import sqlite3; s=sqlite3.connect('/var/lib/the-gift/community.sqlite3'); \
  d=sqlite3.connect('/var/lib/the-gift/backup.sqlite3'); s.backup(d); d.close()"
sudo tar czf ~/gift-data-$(date +%F).tgz -C /var/lib/the-gift backup.sqlite3 media
```

**Admin commands** (run on the box, as the service user):

```bash
cd /opt/rnk/the-gift
alias gift='sudo -u www-data GIFT_DATA_DIR=/var/lib/the-gift python3 gift_community.py'
gift reset-password <username>        # temporary password; ends every session
gift make-admin <username>            # can review artists/songs/reports in the app
gift remove-admin <username>
gift grant <username> premium 365     # comp a plan: plus | premium | church, for N days
```

There's no email, so nobody can reset their own password: check who's
asking (e.g. via their group leader) first. A reset makes their encrypted
journal backup unreadable; their own device still has the journal.

**Church plans** are "contact us": enquiries from the Plans page land in
the database (Admin page → enquiries) and, if `GIFT_CONTACT_EMAIL` is set,
are emailed through the box's `sendmail`. Once agreed, `grant` the
church's people `church` (Premium) for the agreed time.

**Outbound requests.** The server, never the visitor's browser, calls:
OpenStreetMap (Overpass and Nominatim) for "Find a church", with
locations rounded to ~1 km, one request at a time, cached for a day
(`GIFT_PLACES=0` turns it off); Stripe and Google Play's API to confirm
payments (§9).

**Memory.** Indexes for all 139 translations take a few MB; search keeps
an accent-folded copy of the last 4 searched translations (~25 MB);
commentary blocks are cached up to 24 MB; scrypt runs at most two at a
time (16 MB each). Uploads stream to disk. All well under the 512M
ceiling.

## 8. Zero trust, in practice

- **One door** (§3): localhost only, TLS from Cloudflare's edge. HSTS is
  sent on https responses.
- **Every request is verified**: the session token (random, HttpOnly,
  SameSite cookie; only its hash is stored) is checked on each call, and
  every group, song, profile and admin action is authorised against the
  database. The app's own checks are only for display. Sessions end after
  30 days, or 14 idle; people can see and end their sessions under
  Me → Devices & security.
- **Step-up for admin**: admin work needs the password typed within the
  last 30 minutes.
- **No trust in the client**: chat verse quotes come from the library,
  rewards are computed from records, plans are confirmed with Stripe or
  Google, uploads are identified by their bytes (no SVG/HTML) and served
  with a sandbox CSP, and POSTs must be same-origin JSON.
- **Least privilege**: the service runs as `www-data`, can write only
  `/var/lib/the-gift`; payment secrets come from a root-only file and
  systemd credentials (§9), never from the checkout.
- **Everything recorded**: sign-ins (and failures), password changes,
  role changes, removals, reports, admin reviews and plan changes go to
  the audit log (Admin page; kept 180 days).

## 9. Payments and Google Play

Payments stay off until configured. Put secrets in a root-only file the
unit loads (systemd reads it as root before dropping to `www-data`):

```bash
sudo install -d -m 700 /etc/the-gift
sudo tee /etc/the-gift/secrets.env >/dev/null <<'EOF'
GIFT_STRIPE_SECRET_KEY=sk_live_…
GIFT_STRIPE_WEBHOOK_SECRET=whsec_…
GIFT_STRIPE_PRICES={"plus_month":"price_…","plus_year":"price_…","premium_month":"price_…","premium_year":"price_…"}
GIFT_CONTACT_EMAIL=you@example.org
EOF
sudo chmod 600 /etc/the-gift/secrets.env
```

**Stripe**: create the four prices (Plus/Premium × month/year), enable the
customer portal, and add a webhook endpoint
`https://gift.rnkstudios.uk/api/billing/stripe/webhook` for
`checkout.session.completed` and `customer.subscription.*`.

**Google Play**: see `android/README.md`. It covers building the app,
`GIFT_ANDROID_PACKAGE` / `GIFT_ANDROID_CERT_SHA256` (served as
`/.well-known/assetlinks.json`), the four subscription products, and the
service account key (`LoadCredential=` + `GIFT_PLAY_SERVICE_ACCOUNT`).

After changing either, `sudo systemctl restart the-gift`.

## 10. Bible chat (Domain + grounded adapter)

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
