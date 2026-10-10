# Study Guides

## Commentaries and Reference/

20 classic, mostly-19th-century public-domain Bible commentaries and reference works,
plus one daily devotional,
downloaded directly from the [CrossWire SWORD Project](https://www.crosswire.org/sword/)
module archive — the same source library used by free Bible-study apps like AndBible
(Android), Xiphos and BibleTime (Linux/Windows/Mac).

### What's here

| Module | Work | License |
|---|---|---|
| `mhc` | Matthew Henry's Complete Commentary on the Whole Bible | Public Domain |
| `mhcc` | Matthew Henry's Concise Commentary on the Whole Bible | Public Domain |
| `jfb` | Jamieson, Fausset & Brown — Commentary Critical and Explanatory on the Whole Bible (1871) | Public Domain |
| `barnes` | Barnes' Notes on the New Testament | Public Domain |
| `clarke` | Adam Clarke's Commentary and Critical Notes on the Bible | Public Domain |
| `calvincommentaries` | John Calvin's Collected Commentaries | Public Domain |
| `wesley` | John Wesley's Explanatory Notes on the Bible | Public Domain |
| `scofield` | Scofield Reference Notes (1917 edition) | Public Domain |
| `pnt` | The People's New Testament (B.W. Johnson) | Public Domain |
| `geneva` | Geneva Bible (1599) Translation Notes | Public domain (16th c. text; no explicit tag in module metadata) |
| `rwp` | Robertson's Word Pictures in the New Testament | **Copyrighted — free for non-commercial distribution only** (not public domain) |
| `tsk` | Treasury of Scripture Knowledge (cross-reference notes) | Public Domain |
| `nave` | Nave's Topical Bible | Public Domain |
| `torrey` | R.A. Torrey's New Topical Textbook | Public Domain |
| `easton` | Easton's Bible Dictionary | Public Domain |
| `smith` | Smith's Bible Dictionary | Public Domain |
| `hitchcock` | Hitchcock's Bible Names Dictionary | Public Domain |
| `isbe` | International Standard Bible Encyclopedia | Public Domain |
| `strongsgreek` | Strong's Greek Dictionary (from the Exhaustive Concordance) | Public Domain |
| `strongshebrew` | Strong's Hebrew Dictionary (from the Exhaustive Concordance) | Public Domain |
| `sme` | C. H. Spurgeon's *Morning and Evening: Daily Readings* (1865), a reading for every morning and evening of the year. The app's **Today** page shows it | Public Domain |

Every module's exact license text is in its own `mods.d/<name>.conf` file
(`DistributionLicense=` / `About=` fields) — that's the authoritative source, the table
above just summarizes it. **`rwp` is the one exception to "public domain"** in this set:
keep it if free-for-personal-study is fine for your purposes, delete `mods.d/rwp.conf`
and `modules/comments/.../rwp` if you want a strictly public-domain-only collection.
The repository-root `LICENSE` covers the site's own tooling, not these texts.

### Reading them in The Gift app

The app reads these modules directly: the 12 commentaries (and TSK
cross-references) open beside any verse in the Bible tab, the dictionaries
and Strong's answer look-ups, and `sme` is the Today page's devotional
(`gift_study.py`, `gift_library.py`). Matthew Henry (Concise) and TSK are
free; the rest are part of Premium. `rwp` is hidden in the Google Play app
because of its non-commercial licence.

### How to actually read these

This is **not plain text** — it's the standard SWORD module format (a `mods.d/` folder of
`.conf` metadata files + a `modules/` folder of compressed data), the same format used
across the whole CrossWire ecosystem. To read it, point a free SWORD-compatible app at
this folder as its module directory:

- **Xiphos** or **BibleTime** (free, open-source, Linux/Windows/Mac) — in either app's
  settings, add this folder (`Study Guides/Commentaries and Reference/`) as a SWORD
  install/module path, or copy its contents into `~/.sword/` (Linux/Mac default SWORD
  data path) and it'll pick them up automatically.
- **AndBible** (free, open-source, Android) — has its own module manager, but can also
  import modules placed in its SWORD data folder on-device.
- **diatheke** (CrossWire's official CLI, part of `sword-tools` on most Linux distros —
  `sudo apt install sword-tools`) lets you dump any module to plain text from the
  terminal, e.g. `SWORD_PATH="./Study\ Guides/Commentaries\ and\ Reference" diatheke -b mhcc -k "John 3:16"`.

If you'd rather have plain, no-software-required text files, the classics here (Matthew
Henry, JFB, Barnes, Clarke, Wesley, Nave's, Easton's, TSK) are also freely available as
plain-text/EPUB ebooks on [Project Gutenberg](https://www.gutenberg.org) and
[CCEL](https://www.ccel.org) — worth grabbing directly if the SWORD format is more
friction than you want.

### Want more?

CrossWire's full module list (~460 works, including many more commentaries, dictionaries,
and original-language tools like Hebrew/Greek morphology and lexicons) is browsable at
<https://www.crosswire.org/sword/modules/> — everything there follows the same
download-a-zip, extract-into-this-folder pattern.
