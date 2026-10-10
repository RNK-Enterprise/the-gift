"""
The Gift — library engine behind the app's read-only API.

Reads the library straight off disk: the plain-text Bibles under
Bibles/formats/text/, the licence table in Bibles/README.md, and the
SWORD devotional (Spurgeon's Morning and Evening) under Study Guides/.
Python 3 stdlib only. What it keeps in memory is small: per translation
the byte range of every chapter that has text (a few KB in arrays), plus
an accent-folded copy of the last few translations someone searched.

Every lookup re-stats the source file, so a `git pull` that changes a
translation is picked up without serving stale offsets.
"""

import html.parser
import os
import re
import struct
import sys
import threading
import unicodedata
import zlib
from array import array
from collections import OrderedDict
from pathlib import Path

TEXT_DIR = Path("Bibles/formats/text")
LICENCE_TABLE = Path("Bibles/README.md")
SWORD_DIR = Path("Study Guides/Commentaries and Reference")
DEVOTIONAL = "sme"  # mods.d/sme.conf — C. H. Spurgeon, Morning and Evening

ID_RE = re.compile(r"[A-Za-z0-9_]{1,40}")
HEADER_RE = re.compile(rb"== (.+) (\d+) ==")
RTL_LANGS = {"he", "hbo", "syr", "ar", "arc", "fa", "ur", "yi"}

SEARCH_LIMIT = 200       # hits returned; the total is always counted
SEARCH_CACHED = 4        # folded translations kept for repeat searches
QUERY_MAX = 120          # characters

OT_BOOKS = (
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "I Samuel", "II Samuel", "I Kings", "II Kings",
    "I Chronicles", "II Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai",
    "Zechariah", "Malachi",
)
NT_BOOKS = (
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "I Corinthians",
    "II Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians",
    "I Thessalonians", "II Thessalonians", "I Timothy", "II Timothy", "Titus",
    "Philemon", "Hebrews", "James", "I Peter", "II Peter", "I John", "II John",
    "III John", "Jude", "Revelation of John",
)
_OT, _NT = frozenset(OT_BOOKS), frozenset(NT_BOOKS)

# OSIS book IDs (used by SWORD modules' references) → this library's names
OSIS_BOOKS = dict(zip(
    ("Gen Exod Lev Num Deut Josh Judg Ruth 1Sam 2Sam 1Kgs 2Kgs 1Chr 2Chr "
     "Ezra Neh Esth Job Ps Prov Eccl Song Isa Jer Lam Ezek Dan Hos Joel Amos "
     "Obad Jonah Mic Nah Hab Zeph Hag Zech Mal Matt Mark Luke John Acts Rom "
     "1Cor 2Cor Gal Eph Phil Col 1Thess 2Thess 1Tim 2Tim Titus Phlm Heb Jas "
     "1Pet 2Pet 1John 2John 3John Jude Rev").split(),
    OT_BOOKS + NT_BOOKS))

# Reading plans: (id, title, summary, days, streams). Each stream is read
# in order and spread over the days by length, so every day is about the
# same amount of reading; a day can hold several streams (Old + New).
PLANS = (
    ("bible-year", "Bible in a Year",
     "Genesis to Revelation, in order, about 15 minutes a day.",
     365, (OT_BOOKS + NT_BOOKS,)),
    ("old-new-year", "Old & New Together",
     "The Old Testament once and the New Testament twice, a passage from "
     "each every day.", 365, (OT_BOOKS, NT_BOOKS + NT_BOOKS)),
    ("nt-90", "New Testament in 90 Days",
     "Matthew to Revelation in three months.", 90, (NT_BOOKS,)),
    ("gospels-30", "The Gospels in 30 Days",
     "The life of Jesus through Matthew, Mark, Luke and John.",
     30, (NT_BOOKS[:4],)),
    ("psalms-30", "Psalms in 30 Days",
     "All 150 psalms in a month: prayer, lament and praise.",
     30, (("Psalms",),)),
    ("proverbs-31", "Proverbs in a Month",
     "One chapter of wisdom for each day of the month.",
     31, (("Proverbs",),)),
)
PLAN_BASE = "KJV"  # chapter lengths (for even days) come from this translation


# ---------------------------------------------------------------- folding

_MARKS = None
_KEEP_MARKS = {0x3099, 0x309A}  # kana voicing marks are letters, not accents


def fold(s):
    """Case- and accent-insensitive form used by search: θεός → θεος,
    Jêsus → jesus, pointed Hebrew → bare consonants. Recomposed afterwards,
    so Hangul syllables and voiced kana survive intact."""
    global _MARKS
    if _MARKS is None:
        _MARKS = {cp: None for cp in range(sys.maxunicode + 1)
                  if cp not in _KEEP_MARKS
                  and unicodedata.category(chr(cp)) == "Mn"}
    return unicodedata.normalize(
        "NFC", unicodedata.normalize("NFD", s).translate(_MARKS)).casefold()


# scripts that put spaces between words: there a term must start a word, so
# "love" finds loved/lovest but not beloved. Elsewhere (Chinese, Japanese,
# Thai, …; Hebrew and Syriac, which glue on prefixes like "and"/"the") any
# substring matches.
_WORD_SCRIPTS = {"LATIN", "GREEK", "CYRILLIC", "ARMENIAN", "GEORGIAN",
                 "COPTIC", "GOTHIC", "CHEROKEE", "DIGIT"}


def _word_start(term):
    return unicodedata.name(term[0], "").split(" ")[0] in _WORD_SCRIPTS


def _contains(line, term, start, word):
    i = line.find(term, start)
    while i >= 0:
        if not word or i == start or not line[i - 1].isalnum():
            return True
        i = line.find(term, i + 1)
    return False


def parse_query(q):
    """Words to find (all of them, any order), or one phrase if the query is
    wrapped in quotes. Longest first: the rarest word rejects lines soonest."""
    q = q.strip()[:QUERY_MAX]
    if len(q) >= 2 and q[0] in "\"“”" and q[-1] in "\"“”":
        terms = [fold(q[1:-1]).strip()]
    else:
        terms = fold(q).split()
    terms = sorted({t for t in terms if t}, key=len, reverse=True)
    return terms[:8]


# --------------------------------------------------------------- the index

class Translation:
    """Where each chapter that has any text lives in one translation's .txt.

    The upstream files pad books a translation doesn't cover with blank
    verses (an NT-only text still has 929 empty OT chapters), so empty
    chapters are dropped here and never offered to readers."""

    __slots__ = ("id", "title", "stamp", "books", "spans",
                 "book_of", "chapter", "start", "end")

    def find(self, book, number):
        try:
            b = self.books.index(book)
        except ValueError:
            return -1
        lo, hi = self.spans[b]
        for i in range(lo, hi):
            if self.chapter[i] == number:
                return i
        return -1

    def ref(self, i):
        if 0 <= i < len(self.chapter):
            return [self.books[self.book_of[i]], self.chapter[i]]
        return None

    def book_chapters(self):
        return [{"name": name, "chapters": list(self.chapter[lo:hi])}
                for name, (lo, hi) in zip(self.books, self.spans)]


def _index(tid, path, stamp):
    t = Translation()
    t.id, t.stamp = tid, stamp
    t.books, t.spans = [], []
    t.book_of, t.chapter = array("H"), array("H")
    t.start, t.end = array("L"), array("L")

    def close(cur, has_text, stop):
        if cur is None or not has_text:
            return
        name, number, begin = cur
        if not t.books or t.books[-1] != name:
            t.books.append(sys.intern(name))
            t.spans.append([len(t.chapter), len(t.chapter)])
        t.book_of.append(len(t.books) - 1)
        t.chapter.append(number)
        t.start.append(begin)
        t.end.append(stop)
        t.spans[-1][1] += 1

    with open(path, "rb") as f:
        first = f.readline()
        title = first.decode("utf-8", "replace").strip()
        t.title = title.partition(": ")[2] or title
        off = len(first)
        cur, has_text = None, False
        for line in f:
            if line.startswith(b"== "):
                m = HEADER_RE.fullmatch(line.rstrip(b"\r\n"))
                if m:
                    close(cur, has_text, off)
                    cur = (m[1].decode("utf-8", "replace"), int(m[2]), off + len(line))
                    has_text = False
                    off += len(line)
                    continue
            if cur is not None and not has_text:
                num, sep, text = line.partition(b". ")
                has_text = bool(sep and num.isdigit() and text.strip())
            off += len(line)
        close(cur, has_text, off)
    t.spans = [tuple(s) for s in t.spans]
    return t


def _verses(raw):
    out = []
    for line in raw.split("\n"):
        num, sep, text = line.partition(". ")
        text = text.strip()
        if sep and num.isdigit() and text:
            out.append([int(num), text])
    return out


def split_days(weights, days):
    """Cut a sequence of chapter lengths into `days` contiguous runs of
    roughly equal total length, each holding at least one chapter.
    Returns the exclusive end index of each day's run."""
    n = len(weights)
    if n < days or days < 1:
        raise ValueError("fewer chapters than days")
    cum = [0]
    for w in weights:
        cum.append(cum[-1] + w)
    total = cum[-1]
    cuts, prev = [], 0
    for d in range(1, days):
        target = total * d / days
        lo, hi = prev + 1, n - (days - d)  # leave a chapter for every later day
        k = min(range(lo, hi + 1), key=lambda j: (abs(cum[j] - target), j)) \
            if hi - lo < 64 else _nearest(cum, target, lo, hi)
        cuts.append(k)
        prev = k
    cuts.append(n)
    return cuts


def _nearest(cum, target, lo, hi):
    a, b = lo, hi
    while a < b:  # first j with cum[j] >= target
        m = (a + b) // 2
        if cum[m] < target:
            a = m + 1
        else:
            b = m
    best = min((j for j in (a - 1, a) if lo <= j <= hi),
               key=lambda j: abs(cum[j] - target), default=lo)
    return best


# ------------------------------------------------------- devotional (zLD)

class _OsisToBlocks(html.parser.HTMLParser):
    """OSIS markup of one devotional entry → plain JSON-able blocks.

    Output never carries markup: runs of text with flags, so the browser
    renders it with textContent and nothing in the module can inject HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []
        self._block = None      # current paragraph runs, or poem lines
        self._poem = None
        self._italic = 0
        self._ref = None        # (osisRef, collected text)
        self._title = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and a.get("type") == "section":
            sid = a.get("osisid", "")
            self.sections.append({"slot": "evening" if sid.endswith(".pm") else "morning",
                                  "title": "", "blocks": []})
        elif tag == "title":
            self._title = []
        elif tag == "p":
            self._block = []
        elif tag == "lg":
            self._poem = []
        elif tag == "l":
            self._block = []
        elif tag == "hi":
            self._italic += 1
        elif tag == "reference":
            self._ref = (a.get("osisref", ""), [])
        elif tag == "lb":
            self._run({"br": 1})

    def handle_startendtag(self, tag, attrs):
        if tag == "lb":
            self._run({"br": 1})

    def handle_endtag(self, tag):
        if not self.sections:
            return
        sec = self.sections[-1]
        if tag == "title" and self._title is not None:
            sec["title"] = " ".join("".join(self._title).split())
            self._title = None
        elif tag == "p" and self._block is not None:
            if self._block:
                sec["blocks"].append({"p": self._block})
            self._block = None
        elif tag == "l" and self._block is not None and self._poem is not None:
            self._poem.append(self._block)
            self._block = None
        elif tag == "lg" and self._poem is not None:
            if self._poem:
                sec["blocks"].append({"poem": self._poem})
            self._poem = None
        elif tag == "hi":
            self._italic = max(0, self._italic - 1)
        elif tag == "reference" and self._ref is not None:
            osis, parts = self._ref
            self._ref = None
            run = {"t": "".join(parts)}
            r = _osis_ref(osis)
            if r:
                run["ref"] = r
            self._run(run)

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)
        elif self._ref is not None:
            self._ref[1].append(data)
        elif self._block is not None:
            if not data.strip() and not self._block:
                return
            self._run({"t": data, "i": 1} if self._italic else {"t": data})

    def _run(self, run):
        if self._block is None:
            return
        last = self._block[-1] if self._block else None
        if ("t" in run and last and "t" in last and "ref" not in last and "ref" not in run
                and last.get("i") == run.get("i")):
            last["t"] += run["t"]
        else:
            self._block.append(run)


def _osis_ref(osis):
    """"Bible:Josh.5.12" or "Bible:Ps.23.1-Ps.23.3" → {"b","c","v"} (start)."""
    first = osis.rpartition(":")[2].split("-")[0]
    parts = first.split(".")
    if len(parts) < 2 or parts[0] not in OSIS_BOOKS or not parts[1].isdigit():
        return None
    out = {"b": OSIS_BOOKS[parts[0]], "c": int(parts[1])}
    if len(parts) > 2 and parts[2].isdigit():
        out["v"] = int(parts[2])
    return out


def _devotional_section(sec):
    """Pull the opening key verse (italic quote + reference) out of the body."""
    blocks = sec["blocks"]
    if blocks and "p" in blocks[0]:
        runs = blocks[0]["p"]
        refs = [r for r in runs if "ref" in r]
        quote = "".join(r["t"] for r in runs if r.get("i")).strip()
        if refs and quote:
            sec["verse"] = {"text": quote, "label": refs[0]["t"], "ref": refs[0]["ref"]}
            del blocks[0]
    return sec


class Devotional:
    """Reader for a SWORD zLD lexicon/daily-devotion module.

    Layout: <name>.idx holds (offset, size) into <name>.dat, where each
    record is the key, a newline, then (block, entry) numbers; <name>.zdx
    holds (offset, size) of zlib blocks in <name>.zdt, and each inflated
    block starts with an entry count and (offset, size) per entry."""

    def __init__(self, base, stamp, description):
        self.stamp = stamp
        self.description = description
        self._zdx = (base.with_suffix(".zdx")).read_bytes()
        self._zdt = base.with_suffix(".zdt")
        self._blocks = {}
        self.keys = {}
        idx = base.with_suffix(".idx").read_bytes()
        dat = base.with_suffix(".dat").read_bytes()
        for i in range(len(idx) // 8):
            off, size = struct.unpack_from("<II", idx, i * 8)
            rec = dat[off:off + size]
            nl = rec.find(b"\n")
            if nl < 0 or len(rec) < nl + 9:
                continue
            key = rec[:nl].rstrip(b"\r").decode("utf-8", "replace")
            self.keys[key] = struct.unpack_from("<II", rec, nl + 1)

    def _block(self, n):
        if n not in self._blocks:
            off, size = struct.unpack_from("<II", self._zdx, n * 8)
            with open(self._zdt, "rb") as f:
                f.seek(off)
                raw = zlib.decompress(f.read(size))
            count = struct.unpack_from("<I", raw, 0)[0]
            entries = [struct.unpack_from("<II", raw, 4 + i * 8) for i in range(count)]
            self._blocks[n] = (raw, entries)
        return self._blocks[n]

    def raw(self, key):
        loc = self.keys.get(key)
        if loc is None:
            return None
        raw, entries = self._block(loc[0])
        if loc[1] >= len(entries):
            return None
        off, size = entries[loc[1]]
        return raw[off:off + size].rstrip(b"\0").decode("utf-8", "replace")

    def entry(self, key):
        text = self.raw(key)
        if text is None:
            return None
        p = _OsisToBlocks()
        p.feed(text)
        p.close()
        out = {"key": key, "source": self.description}
        for sec in p.sections:
            out.setdefault(sec.pop("slot"), _devotional_section(sec))
        return out


def _read_conf(path):
    conf = {}
    for line in path.read_text("utf-8", errors="replace").splitlines():
        k, sep, v = line.partition("=")
        if sep and k and not k.startswith(("[", "#")):
            conf.setdefault(k.strip(), v.strip())
    return conf


# ---------------------------------------------------------------- library

class Library:
    def __init__(self, root):
        self.root = Path(root)
        self._lock = threading.Lock()
        self._translations = {}
        self._licences = (None, {})
        self._folded = OrderedDict()
        self._fold_lock = threading.Lock()
        self._plans = (None, {})
        self._devotional = None
        self._entries = {}

    # -- translations

    def _path(self, tid):
        if not ID_RE.fullmatch(tid or ""):
            return None
        d = self.root / TEXT_DIR
        p = d / f"{tid}.txt"
        try:
            real = p.resolve()
            if real.parent != d.resolve() or not real.is_file():
                return None  # a symlink can't point a translation elsewhere
        except OSError:
            return None
        return p

    def ids(self):
        try:
            names = [e.name[:-4] for e in os.scandir(self.root / TEXT_DIR)
                     if e.name.endswith(".txt") and ID_RE.fullmatch(e.name[:-4])]
        except OSError:
            return []
        return sorted(names, key=str.lower)

    def get(self, tid):
        path = self._path(tid)
        if path is None:
            return None
        try:
            st = path.stat()
        except OSError:
            return None
        stamp = (st.st_mtime_ns, st.st_size)
        t = self._translations.get(tid)
        if t is not None and t.stamp == stamp:
            return t
        with self._lock:
            t = self._translations.get(tid)
            if t is None or t.stamp != stamp:
                t = _index(tid, path, stamp)
                self._translations[tid] = t
        return t

    def licences(self):
        p = self.root / LICENCE_TABLE
        try:
            st = p.stat()
        except OSError:
            return {}
        stamp = (st.st_mtime_ns, st.st_size)
        if self._licences[0] == stamp:
            return self._licences[1]
        rows = {}
        for line in p.read_text("utf-8", errors="replace").splitlines():
            if not line.startswith("| `"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 5:
                continue
            rows[cells[0].strip("`")] = {
                "lang": cells[1], "licence": cells[3],
                "class": cells[4].split(" — ")[0].strip()}
        self._licences = (stamp, rows)
        return rows

    def _meta(self, t):
        lic = self.licences().get(t.id, {})
        lang = lic.get("lang", "")
        return {"id": t.id, "title": t.title, "lang": lang,
                "dir": "rtl" if lang.split("-")[0] in RTL_LANGS else "ltr",
                "licence": lic.get("licence", ""), "class": lic.get("class", "")}

    def catalogue(self):
        out = []
        for tid in self.ids():
            t = self.get(tid)
            if t is None:
                continue
            m = self._meta(t)
            m["ot"] = sum(1 for b in t.books if b in _OT)
            m["nt"] = sum(1 for b in t.books if b in _NT)
            m["other"] = len(t.books) - m["ot"] - m["nt"]
            out.append(m)
        return out

    def books(self, tid):
        t = self.get(tid)
        if t is None:
            return None
        m = self._meta(t)
        m["books"] = t.book_chapters()
        return m

    def chapter(self, tid, book, number):
        t = self.get(tid)
        if t is None:
            return None
        i = t.find(book, number)
        if i < 0:
            return None
        with open(self._path(tid), "rb") as f:
            f.seek(t.start[i])
            raw = f.read(t.end[i] - t.start[i]).decode("utf-8", "replace")
        return {"t": t.id, "book": book, "chapter": number, "verses": _verses(raw),
                "prev": t.ref(i - 1), "next": t.ref(i + 1)}

    def download(self, tid):
        """A whole translation in the /api/chapter shape, for offline use:
        {"t", "title", "chapters": [chapter, …]}, read in one pass."""
        t = self.get(tid)
        if t is None:
            return None
        data = self._path(tid).read_bytes()
        chapters = []
        for i in range(len(t.chapter)):
            raw = data[t.start[i]:t.end[i]].decode("utf-8", "replace")
            chapters.append({"t": t.id, "book": t.books[t.book_of[i]], "chapter": t.chapter[i],
                             "verses": _verses(raw), "prev": t.ref(i - 1), "next": t.ref(i + 1)})
        return {"t": t.id, "title": t.title, "chapters": chapters}

    def verses(self, tid, book, number, first, last):
        ch = self.chapter(tid, book, number)
        if ch is None:
            return None
        return [v for v in ch["verses"] if first <= v[0] <= last]

    # -- search

    def _folded_copy(self, t):
        """Accent-folded lines of one translation plus each chapter's line
        range, LRU-cached: folding is the slow part of a search."""
        with self._fold_lock:
            hit = self._folded.get(t.id)
            if hit is not None and hit[0] == t.stamp:
                self._folded.move_to_end(t.id)
                return hit[1], hit[2]
            data = self._path(t.id).read_text("utf-8", errors="replace")
            lines = data.split("\n")
            folded = fold(data).split("\n")
            if len(folded) != len(lines):
                folded = [fold(x) for x in lines]
            chapters, cur = [], None
            for i, line in enumerate(lines):
                if line.startswith("== "):
                    m = HEADER_RE.fullmatch(line.encode("utf-8"))
                    if m:
                        if cur:
                            chapters.append((cur[0], cur[1], cur[2], i))
                        cur = (sys.intern(m[1].decode("utf-8")), int(m[2]), i + 1)
            if cur:
                chapters.append((cur[0], cur[1], cur[2], len(lines)))
            self._folded[t.id] = (t.stamp, folded, chapters)
            while len(self._folded) > SEARCH_CACHED:
                self._folded.popitem(last=False)
            return folded, chapters

    def search(self, tid, query, book=None, limit=SEARCH_LIMIT):
        t = self.get(tid)
        if t is None:
            return None
        terms = parse_query(query)
        out = {"t": t.id, "q": query, "total": 0, "limit": limit, "hits": []}
        if not terms:
            return out
        folded, chapters = self._folded_copy(t)
        terms = [(x, _word_start(x)) for x in terms]
        lead = terms[0][0]
        found = []
        total = 0
        for b, c, lo, hi in chapters:
            if book and b != book:
                continue
            for i in range(lo, hi):
                line = folded[i]
                if lead not in line:
                    continue
                p = line.find(". ")
                if p > 0 and all(_contains(line, x, p + 2, w) for x, w in terms):
                    total += 1
                    if len(found) < limit:
                        found.append((b, c, i))
        out["total"] = total
        if found:
            lines = self._path(t.id).read_text("utf-8", errors="replace").split("\n")
            for b, c, i in found:
                num, _, text = lines[i].partition(". ")
                out["hits"].append([b, c, int(num), text.strip()])
        return out

    # -- reading plans

    def plans(self):
        """All plans this library can build, keyed by id. Chapter lengths
        come from PLAN_BASE, or the first translation holding every book."""
        base = self.get(PLAN_BASE)
        stamp = base.stamp if base else None
        if self._plans[0] == stamp and stamp is not None:
            return self._plans[1]
        built = {}
        for pid, title, summary, days, streams in PLANS:
            t = base if base and _has_all(base, streams) else None
            if t is None:
                t = next((x for x in map(self.get, self.ids())
                          if x and _has_all(x, streams)), None)
            if t is None:
                continue
            try:
                built[pid] = _build_plan(t, pid, title, summary, days, streams)
            except ValueError:
                continue
        self._plans = (stamp, built)
        return built

    # -- devotional

    def devotional(self):
        conf_path = self.root / SWORD_DIR / "mods.d" / f"{DEVOTIONAL}.conf"
        try:
            st = conf_path.stat()
        except OSError:
            return None
        stamp = (st.st_mtime_ns, st.st_size)
        d = self._devotional
        if d is not None and d.stamp == stamp:
            return d
        with self._lock:
            conf = _read_conf(conf_path)
            module_root = (self.root / SWORD_DIR).resolve()
            base = (module_root / conf.get("DataPath", "")).resolve()
            if module_root not in base.parents:
                return None
            try:
                self._devotional = Devotional(base, stamp, conf.get("Description", ""))
            except (OSError, struct.error):
                return None
            self._entries = {}
        return self._devotional

    def devotional_entry(self, month, day):
        d = self.devotional()
        if d is None:
            return None
        key = f"{month:02d}.{day:02d}"
        if key not in self._entries:
            entry = d.entry(key)
            if entry is None:
                return None
            self._entries[key] = entry
        return self._entries[key]


def _has_all(t, streams):
    return all(b in t.books for s in streams for b in set(s))


def _build_plan(t, pid, title, summary, days, streams):
    per_day = [[] for _ in range(days)]
    for stream in streams:
        chapters = []
        for book in stream:
            b = t.books.index(book)
            lo, hi = t.spans[b]
            chapters.extend((book, t.chapter[i], t.end[i] - t.start[i]) for i in range(lo, hi))
        cuts = split_days([w for _, _, w in chapters], days)
        prev = 0
        for d, cut in enumerate(cuts):
            for book, number, _ in chapters[prev:cut]:
                segs = per_day[d]
                if segs and segs[-1][0] == book and segs[-1][2] == number - 1:
                    segs[-1][2] = number
                else:
                    segs.append([book, number, number])
            prev = cut
    return {"id": pid, "title": title, "summary": summary, "length": days,
            "chapters": sum(s[2] - s[1] + 1 for day in per_day for s in day),
            "days": per_day}
