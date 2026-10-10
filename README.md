# The Gift

[![test](https://github.com/RNK-Enterprise/the-gift/actions/workflows/test.yml/badge.svg)](https://github.com/RNK-Enterprise/the-gift/actions/workflows/test.yml)

A personal library of free-to-read Bible translations and study resources, most of them
public domain, pulled together from established open-data projects rather than built from
scratch. Nothing here is paywalled, DRM'd, or account-gated.

## Structure

```
Bibles/                                  139 Bible translations, three formats under Bibles/formats/
                                         (per-translation licences: Bibles/README.md)
Study Guides/
  Commentaries and Reference/            20 classic commentaries & reference works, plus
                                         Spurgeon's Morning and Evening (SWORD format)
app/                                     the app at /app/ (plain HTML/CSS/JS, no build step)
Music/Hymns/                             22 public-domain hymns and recordings (sources: Music/README.md)
android/                                 the Google Play app (Trusted Web Activity) and store listing
design/                                  the logo and everything drawn from it
```

## Bibles/

139 translations across 56 languages, compiled by the [scrollmapper/bible_databases](https://github.com/scrollmapper/bible_databases)
project, mostly from CrossWire SWORD modules. Three formats ship under `Bibles/formats/`:
plain text (one UTF-8 `.txt` per translation, the readable copy), the same text as
Python data files per book and per translation, and small Node.js word-concordance
scripts (`correlate/`) that read the Python files. See
[Bibles/README.md](Bibles/README.md) for the formats, **every translation's licence**,
and the repairs made to damaged upstream text.

## Study Guides/Commentaries and Reference/

20 classic, public-domain Bible commentaries, topical references, and dictionaries, plus
one daily devotional (C. H. Spurgeon's *Morning and Evening*)
(Matthew Henry, Jamieson-Fausset-Brown, Barnes' Notes, Adam Clarke, Calvin, Strong's
Greek/Hebrew Dictionaries, Nave's Topical Bible, and more), in the standard **SWORD
module format** used by CrossWire and its downstream apps. See
[Study Guides/README.md](Study%20Guides/README.md) for what's included, licensing per
module, and how to actually read them (they're not plain text — see below).

## A note on "solid, not 1:1"

This is a curated slice of much larger open datasets, not an exhaustive mirror. If you
want more (more languages, more commentaries, Hebrew/Greek interlinear/tagged texts,
etc.), the source projects have a lot more available — see the per-folder READMEs for
where to go back and pull additional material.

## Serving it

`server.py` (Python 3 stdlib only) serves the whole library with a landing
page and browsable listings:

```bash
python3 server.py          # 127.0.0.1:8770 (GIFT_HOST=0.0.0.0 opens it to the LAN)
```

Never exposes `.git`, the private `model/` folder, `deploy/`, or dotfiles (the
app's `.data/` included). For hosting
on the RNK box (192.168.1.202) see [deploy/HOSTING.md](deploy/HOSTING.md);
for a full release walkthrough see [deploy/RELEASE.md](deploy/RELEASE.md).
Bulk/programmatic access should clone the repo
(`git clone https://github.com/RNK-Enterprise/the-gift.git`), not crawl HTTP.

## The app

*Read it. Study it. Grow together.* `/app/` is an installable web app (a
PWA) and, wrapped as a Trusted Web Activity, the Google Play app
(`android/`). It's built mobile-first and also works on desktop.

- **Today**: Spurgeon's *Morning and Evening*, today's reading-plan passage,
  and a way back to where you were.
- **Bible**: 139 translations, two side by side, search in any language
  (accents and vowel points don't matter). Tap verses to highlight,
  bookmark, copy, journal, share to a group, or open **study notes**: the
  library's 12 commentaries and the Treasury of Scripture Knowledge, plus
  the Bible dictionaries and Strong's, read straight from the SWORD modules.
  "Mark as read" at the end of each chapter tracks **progress** through all
  1,189 chapters.
- **Music**: 22 public-domain hymns with recordings (`Music/`), and Christian
  artists who apply, are approved by an admin, and upload songs that are
  each reviewed before they play. A player keeps going while you browse.
- **Groups**: private online study groups joined by invite link, with chat,
  a shared reading plan, and roles (leader, moderator, member, plus a title
  such as "Prayer lead"). Report and block are always one tap away.
- **Me**: a profile (picture, bio, favourite verse), friends, Bible progress,
  **rewards** (28 badges, points and levels, computed by the server from
  what you've done), plans, journal, the artist studio, and signed-in
  devices.
- **Churches**: Christian churches near you, from OpenStreetMap.

**Plans.** Reading, the devotional, plans, the journal and groups are
free. **Plus** adds sync & backup (the journal is encrypted on the device
before upload) and offline Bibles; **Premium** adds every commentary, the
dictionaries, bigger groups and artist tools; **Church** plans are
arranged on request. Every limit is enforced by the server. Payments go
through Stripe on the web and Google Play Billing in the Android app, and
each is confirmed with the provider (`gift_billing.py`). The Play app leaves
out the 23 translations (and one commentary) whose licences don't allow use
in a paid product; they stay free on the web.

**What's stored where.** Without Plus, the journal, highlights, bookmarks
and personal plan stay in the browser. Accounts, profiles, groups,
chat, progress, uploads and plans live on the server under
`GIFT_DATA_DIR` (default `.data/`). Privacy, terms, account deletion and
child-safety pages are in `app/legal/`.

**Zero trust.** The server listens on localhost only behind the
Cloudflare tunnel. It verifies every request's session and checks
permission against the database. Admin work needs a recently typed
password, uploads are identified by their bytes and sandboxed, and
security events are audit-logged. See `deploy/HOSTING.md` §8.

**Code.** Plain ES modules with no framework, bundler or build step. The
server is still stdlib-only Python: `server.py` (HTTP), `gift_api.py`
(routes), `gift_library.py` (Bibles, search, plans, devotional),
`gift_study.py` (commentaries, dictionaries), `gift_community.py`
(accounts, profiles, friends, groups, roles, chat, safety, sync, audit),
`gift_rewards.py`, `gift_music.py`, `gift_media.py`, `gift_billing.py` and
`gift_places.py`. Brand images come from `design/` (the logo is
`design/the-gift-logo.png`).

## Contributing / verifying changes

The server and its tests are stdlib-only Python 3 — no packages to install:

```bash
python3 -m unittest test_server test_deploy_scripts test_app test_features -v   # what CI runs (~15s)
python3 server.py                    # then poke http://127.0.0.1:8770/ and /app/
```

Tests run against a tiny fixture tree, not the real library, so the suite
is fast and hermetic. `test_deploy_scripts` runs the monitoring scripts in
`deploy/` for real, with a fake `sendmail` and simulated outages. CI also
runs `shellcheck deploy/*.sh` and checks that every app JavaScript file
parses. When changing `server.py`, keep the security
tests passing (traversal guard, hidden paths, symlinks) and add a
regression test for any behavior you touch. The existing tests are meant
to be copied as templates. Docs that should stay truthful: `deploy/HOSTING.md` (hosting),
`deploy/RELEASE.md` (release checklist), and the per-folder READMEs
(`Bibles/README.md` holds the licence table).

## Changelog

Releases are mostly about the server that serves the library. Details in the
[GitHub releases](https://github.com/RNK-Enterprise/the-gift/releases).

- **v1.2.0** (Oct 2026) — text repairs to 7 translations (Albanian, Modern Hebrew
  and Croatian each had another Bible's file header glued onto their last
  verse; garbled characters were fixed in Vietnamese, Gothic, French and
  Chinese). The correlate scripts now work for non-English texts. Before,
  their word-splitting only understood a–z. Every translation's licence is now listed in
  [Bibles/README.md](Bibles/README.md). Listings handle odd file names,
  pages send basic security headers, and the site links the git repo for
  bulk downloads. Deploy units (`the-gift.service`, cron, logrotate) and
  deploy-script tests ship in-repo.

- **v1.1.0** (Sep 2026) — server hardening: a busy server can no longer
  be wedged by idle connections, large files stream in chunks instead of
  loading whole into memory, and `LICENSE` displays in-browser instead
  of downloading. Nothing about the texts changed.

## Licensing

Everything here is free to use, but "free" isn't monolithic:
- Most texts are genuinely **public domain**: 103 of the 139 translations and 20 of
  the 21 study modules.
- 13 translations carry open licences (CC BY / BY-SA / BY-ND, GPL), 17 are
  non-commercial only, and 6 are either restricted to CrossWire's use or of unknown
  status. All are listed in [Bibles/README.md](Bibles/README.md).
- One study module (`rwp`) is copyrighted but free for non-commercial distribution;
  see `Study Guides/README.md`.
- Always check the specific translation's or module's licence before redistributing.
  For the study modules, each `mods.d/<name>.conf` carries the authoritative text.
