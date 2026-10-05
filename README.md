# The Gift

[![test](https://github.com/lisasdungeon/the-gift/actions/workflows/test.yml/badge.svg)](https://github.com/lisasdungeon/the-gift/actions/workflows/test.yml)

A personal library of free-to-read Bible translations and study resources, most of them
public domain, pulled together from established open-data projects rather than built from
scratch. Nothing here is paywalled, DRM'd, or account-gated.

## Structure

```
Bibles/                                  140 Bible translations, three formats under Bibles/formats/
                                         (per-translation licences: Bibles/README.md)
Study Guides/
  Commentaries and Reference/            20 classic commentaries & reference works (SWORD format)
```

## Bibles/

140 translations across 56 languages, compiled by the [scrollmapper/bible_databases](https://github.com/scrollmapper/bible_databases)
project, mostly from CrossWire SWORD modules. Three formats ship under `Bibles/formats/`:
plain text (one UTF-8 `.txt` per translation, the readable copy), the same text as
Python data files per book and per translation, and small Node.js word-concordance
scripts (`correlate/`) that read the Python files. See
[Bibles/README.md](Bibles/README.md) for the formats, **every translation's licence**,
and the repairs made to damaged upstream text.

## Study Guides/Commentaries and Reference/

20 classic, public-domain Bible commentaries, topical references, and dictionaries
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
python3 server.py          # 0.0.0.0:8770 — LAN-visible
```

Never exposes `.git`, the private `model/` folder, `deploy/`, or dotfiles. For hosting
on the RNK box (192.168.1.202) see [deploy/HOSTING.md](deploy/HOSTING.md);
for a full release walkthrough see [deploy/RELEASE.md](deploy/RELEASE.md).
Bulk/programmatic access should clone the repo
(`git clone https://github.com/lisasdungeon/the-gift.git`), not crawl HTTP.

## Contributing / verifying changes

The server and its tests are stdlib-only Python 3 — no packages to install:

```bash
python3 -m unittest test_server test_deploy_scripts -v   # what CI runs (~5s)
python3 server.py                    # then poke http://127.0.0.1:8770/
```

Tests run against a tiny fixture tree, not the real library, so the suite
is fast and hermetic. `test_deploy_scripts` runs the monitoring scripts in
`deploy/` for real, with a fake `sendmail` and simulated outages. CI also
runs `shellcheck deploy/*.sh`. When changing `server.py`, keep the security
tests passing (traversal guard, hidden paths, symlinks) and add a
regression test for any behavior you touch. The existing tests are meant
to be copied as templates. Docs that should stay truthful: `deploy/HOSTING.md` (hosting),
`deploy/RELEASE.md` (release checklist), and the per-folder READMEs
(`Bibles/README.md` holds the licence table).

## Changelog

Releases are mostly about the server that serves the library. Details in the
[GitHub releases](https://github.com/lisasdungeon/the-gift/releases).

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
- Most texts are genuinely **public domain**: 103 of the 140 translations and 19 of
  the 20 study modules.
- 13 translations carry open licences (CC BY / BY-SA / BY-ND, GPL), 18 are
  non-commercial only, and 6 are either restricted to CrossWire's use or of unknown
  status. All are listed in [Bibles/README.md](Bibles/README.md).
- One study module (`rwp`) is copyrighted but free for non-commercial distribution;
  see `Study Guides/README.md`.
- Always check the specific translation's or module's licence before redistributing.
  For the study modules, each `mods.d/<name>.conf` carries the authoritative text.
