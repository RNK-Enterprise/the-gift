"""
The Gift — study notes: the library's SWORD commentaries, read in place.

The 12 commentaries under Study Guides/ (Matthew Henry, JFB, Barnes,
Clarke, Wesley, Calvin, the Treasury of Scripture Knowledge…) are SWORD
zCom/zCom4 modules. This reads them directly, with no SWORD library, and
turns their OSIS or ThML markup into plain text runs and verse links. As
with the devotional, no markup is ever passed through, so nothing in a
module can inject HTML into the app.

A zCom module stores one index entry per verse slot, per testament: slot 0
is the module heading, 1 the testament heading, then each book has a
heading slot, and each chapter a heading slot followed by its verses
(KJV versification). An entry is (block, offset, size); the block is a
zlib-compressed run of text. Commentators who wrote one note for a range
of verses store it once and point every verse in the range at it.
"""

import html.parser
import re
import struct
import threading
import zlib
from collections import OrderedDict
from pathlib import Path

import gift_library
from gift_library import NT_BOOKS, OSIS_BOOKS, OT_BOOKS

SWORD_DIR = gift_library.SWORD_DIR

# (module, display name), in the order the app offers them
COMMENTARIES = (
    ("mhcc", "Matthew Henry (Concise)"),
    ("jfb", "Jamieson, Fausset & Brown"),
    ("mhc", "Matthew Henry (Complete)"),
    ("barnes", "Barnes' Notes"),
    ("clarke", "Adam Clarke"),
    ("wesley", "John Wesley"),
    ("calvincommentaries", "John Calvin"),
    ("geneva", "Geneva Bible Notes (1599)"),
    ("scofield", "Scofield Notes (1917)"),
    ("pnt", "People's New Testament"),
    ("rwp", "Robertson's Word Pictures"),
    ("tsk", "Cross-references (TSK)"),
)

BLOCK_CACHE_BYTES = 24 * 1024 * 1024  # inflated blocks kept for neighbouring lookups

# verses per chapter, KJV versification, Genesis to Revelation
KJV_VERSES = (
    "31,25,24,26,32,22,24,22,29,32,32,20,18,24,21,16,27,33,38,18,34,24,20,67,34,"
    "35,46,22,35,43,55,32,20,31,29,43,36,30,23,23,57,38,34,34,28,34,31,22,33,26|"
    "22,25,22,31,23,30,25,32,35,29,10,51,22,31,27,36,16,27,25,26,36,31,33,18,40,"
    "37,21,43,46,38,18,35,23,35,35,38,29,31,43,38|"
    "17,16,17,35,19,30,38,36,24,20,47,8,59,57,33,34,16,30,37,27,24,33,44,23,55,"
    "46,34|"
    "54,34,51,49,31,27,89,26,23,36,35,16,33,45,41,50,13,32,22,29,35,41,30,25,18,"
    "65,23,31,40,16,54,42,56,29,34,13|"
    "46,37,29,49,33,25,26,20,29,22,32,32,18,29,23,22,20,22,21,20,23,30,25,22,19,"
    "19,26,68,29,20,30,52,29,12|"
    "18,24,17,24,15,27,26,35,27,43,23,24,33,15,63,10,18,28,51,9,45,34,16,33|"
    "36,23,31,24,31,40,25,35,57,18,40,15,25,20,20,31,13,31,30,48,25|"
    "22,23,18,22|"
    "28,36,21,22,12,21,17,22,27,27,15,25,23,52,35,23,58,30,24,42,15,23,29,22,44,"
    "25,12,25,11,31,13|"
    "27,32,39,12,25,23,29,18,13,19,27,31,39,33,37,23,29,33,43,26,22,51,39,25|"
    "53,46,28,34,18,38,51,66,28,29,43,33,34,31,34,34,24,46,21,43,29,53|"
    "18,25,27,44,27,33,20,29,37,36,21,21,25,29,38,20,41,37,37,21,26,20,37,20,30|"
    "54,55,24,43,26,81,40,40,44,14,47,40,14,17,29,43,27,17,19,8,30,19,32,31,31,"
    "32,34,21,30|"
    "17,18,17,22,14,42,22,18,31,19,23,16,22,15,19,14,19,34,11,37,20,12,21,27,28,"
    "23,9,27,36,27,21,33,25,33,27,23|"
    "11,70,13,24,17,22,28,36,15,44|"
    "11,20,32,23,19,19,73,18,38,39,36,47,31|"
    "22,23,15,17,14,14,10,17,32,3|"
    "22,13,26,21,27,30,21,22,35,22,20,25,28,22,35,22,16,21,29,29,34,30,17,25,6,"
    "14,23,28,25,31,40,22,33,37,16,33,24,41,30,24,34,17|"
    "6,12,8,8,12,10,17,9,20,18,7,8,6,7,5,11,15,50,14,9,13,31,6,10,22,12,14,9,11,"
    "12,24,11,22,22,28,12,40,22,13,17,13,11,5,26,17,11,9,14,20,23,19,9,6,7,23,13,"
    "11,11,17,12,8,12,11,10,13,20,7,35,36,5,24,20,28,23,10,12,20,72,13,19,16,8,"
    "18,12,13,17,7,18,52,17,16,15,5,23,11,13,12,9,9,5,8,28,22,35,45,48,43,13,31,"
    "7,10,10,9,8,18,19,2,29,176,7,8,9,4,8,5,6,5,6,8,8,3,18,3,3,21,26,9,8,24,13,"
    "10,7,12,15,21,10,20,14,9,6|"
    "33,22,35,27,23,35,27,36,18,32,31,28,25,35,33,33,28,24,29,30,31,29,35,34,28,"
    "28,27,28,27,33,31|"
    "18,26,22,16,20,12,29,17,18,20,10,14|"
    "17,17,11,16,16,13,13,14|"
    "31,22,26,6,30,13,25,22,21,34,16,6,22,32,9,14,14,7,25,6,17,25,18,23,12,21,13,"
    "29,24,33,9,20,24,17,10,22,38,22,8,31,29,25,28,28,25,13,15,22,26,11,23,15,12,"
    "17,13,12,21,14,21,22,11,12,19,12,25,24|"
    "19,37,25,31,31,30,34,22,26,25,23,17,27,22,21,21,27,23,15,18,14,30,40,10,38,"
    "24,22,17,32,24,40,44,26,22,19,32,21,28,18,16,18,22,13,30,5,28,7,47,39,46,64,"
    "34|"
    "22,22,66,22,22|"
    "28,10,27,17,17,14,27,18,11,22,25,28,23,23,8,63,24,32,14,49,32,31,49,27,17,"
    "21,36,26,21,26,18,32,33,31,15,38,28,23,29,49,26,20,27,31,25,24,23,35|"
    "21,49,30,37,31,28,28,27,27,21,45,13|"
    "11,23,5,19,15,11,16,14,17,15,12,14,16,9|"
    "20,32,21|"
    "15,16,15,13,27,14,17,14,15|"
    "21|"
    "17,10,10,11|"
    "16,13,12,13,15,16,20|"
    "15,13,19|"
    "17,20,19|"
    "18,15,20|"
    "15,23|"
    "21,13,10,14,11,15,14,23,17,12,17,14,9,21|"
    "14,17,18,6|"
    "25,23,17,25,48,34,29,34,38,42,30,50,58,36,39,28,27,35,30,34,46,46,39,51,46,"
    "75,66,20|"
    "45,28,35,41,43,56,37,38,50,52,33,44,37,72,47,20|"
    "80,52,38,44,39,49,50,56,62,42,54,59,35,35,32,31,37,43,48,47,38,71,56,53|"
    "51,25,36,54,47,71,53,59,41,42,57,50,38,31,27,33,26,40,42,31,25|"
    "26,47,26,37,42,15,60,40,43,48,30,25,52,28,41,40,34,28,41,38,40,30,35,27,27,"
    "32,44,31|"
    "32,29,31,25,21,23,25,39,33,21,36,21,14,23,33,27|"
    "31,16,23,21,13,20,40,13,27,33,34,31,13,40,58,24|"
    "24,17,18,18,21,18,16,24,15,18,33,21,14|"
    "24,21,29,31,26,18|"
    "23,22,21,32,33,24|"
    "30,30,21,23|"
    "29,23,25,18|"
    "10,20,13,18,28|"
    "12,17,18|"
    "20,15,16,16,25,21|"
    "18,26,17,22|"
    "16,15,15|"
    "25|"
    "14,18,19,16,14,20,28,13,28,39,40,29,25|"
    "27,26,18,17,20|"
    "25,25,22,19,14|"
    "21,22,18|"
    "10,29,24,21,21|"
    "13|"
    "14|"
    "25|"
    "20,29,22,11,14,17,17,13,21,11,19,17,18,20,8,21,18,24,21,15,27,21"
)

_VERSES = [list(map(int, b.split(","))) for b in KJV_VERSES.split("|")]


def _chapter_slots():
    """(book, chapter) → (testament file, index of the chapter's heading slot)."""
    slots = {}
    for testament, books, first in (("ot", OT_BOOKS, 0), ("nt", NT_BOOKS, 39)):
        i = 1                      # 0 module heading, 1 testament heading
        for n, book in enumerate(books):
            i += 1                 # book heading
            for c, verses in enumerate(_VERSES[first + n], 1):
                i += 1             # chapter heading
                slots[(book, c)] = (testament, i, verses)
                i += verses
    return slots


SLOTS = _chapter_slots()

# ---------------------------------------------------------- references

# SWORD/ThML abbreviations that aren't just the start of a book's name
_ALIASES = {"mt": "Matthew", "mr": "Mark", "mk": "Mark", "lk": "Luke", "jn": "John", "jhn": "John",
            "php": "Philippians", "phm": "Philemon", "phlm": "Philemon", "jas": "James", "jg": "Judges",
            "jdg": "Judges", "jud": "Jude", "re": "Revelation of John", "rev": "Revelation of John",
            "ps": "Psalms", "psa": "Psalms", "song": "Song of Solomon", "so": "Song of Solomon",
            "sos": "Song of Solomon", "is": "Isaiah", "ec": "Ecclesiastes", "qoh": "Ecclesiastes"}
_BOOKS = OT_BOOKS + NT_BOOKS
_NUMBERED = {"1": "I", "2": "II", "3": "III", "i": "I", "ii": "II", "iii": "III"}


def resolve_book(abbr):
    """'Joh', '1Co', 'Lu', 'Isa', 'Ge' … → the library's book name, or None."""
    # a digit may touch the name ("1Co"); a Roman numeral must be its own
    # word, or "Isa" would read as "I Sa(muel)"
    m = re.fullmatch(r"\s*(?:([1-3])\s*|(iii|ii|i)\s+)?([A-Za-z]+)\.?\s*", abbr or "", re.I)
    if not m:
        return None
    num = _NUMBERED.get((m[1] or m[2] or "").lower(), "")
    word = m[3].lower()
    if not num and word in _ALIASES:
        return _ALIASES[word]
    for book in _BOOKS:
        prefix, _, rest = book.partition(" ")
        if num:
            if prefix == num and rest.lower().replace(" ", "").startswith(word):
                return book
        elif prefix not in ("I", "II", "III") and book.lower().replace(" ", "").startswith(word):
            return book
    return None


_REF_PART = re.compile(r"\s*(?P<book>(?:[1-3]\s?)?[A-Za-z]+\.?)?\s*(?P<c>\d+)(?:\s*[:.]\s*(?P<v>\d+))?")


def ref_runs(text, book, chapter):
    """Split a reference list such as '5:45; 8:15,16; Lu 9:56' into text
    runs, each part linked to where it points. A part without a book means
    the current book; a bare number after a comma is another verse."""
    runs = []
    for i, part in enumerate(re.split(r"(;\s*)", text)):
        if i % 2 or not part.strip():
            if part:
                runs.append({"t": part})
            continue
        m = _REF_PART.match(part)
        ref = None
        if m:
            b = resolve_book(m["book"]) if m["book"] else book
            if b:
                book = b
                if m["v"]:
                    chapter = int(m["c"])
                    ref = {"b": b, "c": chapter, "v": int(m["v"])}
                elif m["book"]:
                    ref = {"b": b, "c": int(m["c"])}
                else:  # "16" alone: a verse in the current chapter
                    ref = {"b": b, "c": chapter, "v": int(m["c"])}
        runs.append({"t": part, "ref": ref} if ref else {"t": part})
    return runs, book, chapter


def osis_ref(value, book, chapter):
    """osisRef="John.3.19" (or "Bible:Gen.1.1", or SWORD-style "joh 3:18")."""
    value = (value or "").strip()
    if value.startswith("Bible:"):
        value = value[6:]
    elif ":" in value.split(" ")[0] and not re.match(r"^[0-9A-Za-z]+ \d", value):
        return None  # a link into another module (e.g. "Scofield:Mt 4:8")
    first = value.split(" ")[0] if "." in value.split(" ")[0] else value
    if "." in first:
        parts = first.split("-")[0].split(".")
        b = OSIS_BOOKS.get(parts[0])
        if b and len(parts) > 1 and parts[1].isdigit():
            r = {"b": b, "c": int(parts[1])}
            if len(parts) > 2 and parts[2].isdigit():
                r["v"] = int(parts[2])
            return r
        return None
    runs, _, _ = ref_runs(value, book, chapter)
    return next((r["ref"] for r in runs if "ref" in r), None)


# -------------------------------------------------------------- markup

class _Markup(html.parser.HTMLParser):
    """OSIS, ThML or TEI → [{"h": heading} | {"p": [runs]}]. Runs are
    {"t": text} with optional "i" (italic), "b" (bold), "s" (superscript),
    "ref" ({b, c, v}); {"br": 1} is a line break. Unknown tags are
    transparent; notes are dropped."""

    BLOCK = {"p", "lg", "list", "item", "li", "entryfree", "def", "table", "tr"}
    HEAD = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "head"}
    SKIP = {"note", "rdg", "script", "style", "sync"}

    def __init__(self, book=None, chapter=None):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.runs = []
        self.book, self.chapter = book, chapter
        self.style = []
        self.skip = 0
        self.head = None
        self.ref = None  # (attrs, collected text)

    # block handling
    def flush(self):
        runs = self.runs
        self.runs = []
        while runs and ("br" in runs[0] or not runs[0].get("t", "").strip() and "ref" not in runs[0]):
            runs.pop(0)
        while runs and ("br" in runs[-1] or not runs[-1].get("t", "").strip() and "ref" not in runs[-1]):
            runs.pop()
        if not runs:
            return
        if "ref" not in runs[0]:
            runs[0]["t"] = runs[0]["t"].lstrip()
        if "ref" not in runs[-1]:
            runs[-1]["t"] = runs[-1]["t"].rstrip()
        self.blocks.append({"p": [r for r in runs if r.get("t") or "br" in r]})

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip or tag in self.SKIP:
            if tag in self.SKIP and not tag == "sync":
                self.skip += 1
            return
        if tag in self.HEAD:
            self.flush()
            self.head = []
        elif tag in self.BLOCK or (tag == "div" and (a.get("type") in ("x-p", "paragraph") or not a)):
            self.flush()
        elif tag in ("lb", "br", "l"):
            self.add({"br": 1})
        elif tag in ("reference", "scripref", "ref"):
            self.ref = (a, [])
        else:
            kind = a.get("type", "") if tag == "hi" else tag
            self.style.append({"italic": "i", "i": "i", "em": "i", "bold": "b", "b": "b", "strong": "b",
                               "super": "s", "sup": "s"}.get(kind, ""))

    def handle_startendtag(self, tag, attrs):
        if tag in ("lb", "br") and not self.skip:
            self.add({"br": 1})
        elif tag == "div" and not self.skip and dict(attrs).get("type") == "x-p":
            self.flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP and tag != "sync":
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in self.HEAD and self.head is not None:
            # some modules escape markup inside titles: drop it, keep the words
            text = " ".join(re.sub(r"<[^>]*>", "", "".join(self.head)).split())
            if text:
                self.blocks.append({"h": text})
            self.head = None
        elif tag in self.BLOCK or tag == "div":
            self.flush()
        elif tag in ("reference", "scripref", "ref") and self.ref is not None:
            a, parts = self.ref
            self.ref = None
            text = "".join(parts)
            target = a.get("osisref") or a.get("target")
            if target:
                r = osis_ref(target, self.book, self.chapter)
                self.add({"t": text, "ref": r} if r else {"t": text})
            else:
                passage = a.get("passage")
                if passage:
                    _, self.book, self.chapter = ref_runs(passage, self.book, self.chapter)
                    r = osis_ref(passage, self.book, self.chapter)
                    self.add({"t": text, "ref": r} if r else {"t": text})
                else:
                    runs, self.book, self.chapter = ref_runs(text, self.book, self.chapter)
                    for run in runs:
                        self.add(run)
        elif tag not in ("lb", "br", "l") and self.style:
            self.style.pop()

    def handle_data(self, data):
        if self.skip:
            return
        data = re.sub(r"\s+", " ", data)
        if self.head is not None:
            self.head.append(data)
        elif self.ref is not None:
            self.ref[1].append(data)
        elif data:
            run = {"t": data}
            for flag in set(self.style) - {""}:
                run[flag] = 1
            self.add(run)

    def add(self, run):
        if "br" in run:  # one line break at a time, never a blank line
            while self.runs and "t" in self.runs[-1] and "ref" not in self.runs[-1] \
                    and not self.runs[-1]["t"].strip():
                self.runs.pop()
            if not self.runs or "br" in self.runs[-1]:
                return
        last = self.runs[-1] if self.runs else None
        if ("t" in run and last and "t" in last and "ref" not in run and "ref" not in last
                and all(run.get(k) == last.get(k) for k in "ibs")):
            last["t"] += run["t"]
        else:
            self.runs.append(run)

    def result(self):
        self.close()
        self.flush()
        return self.blocks


def to_blocks(markup, book=None, chapter=None):
    p = _Markup(book, chapter)
    p.feed(markup)
    return p.result()


# ------------------------------------------------------------- modules

class ZCom:
    """One zCom/zCom4 commentary module on disk."""

    def __init__(self, path, size4):
        self.path = path
        self.entry = 12 if size4 else 10
        self.files = {}
        for t in ("ot", "nt"):
            for kind in "bcv":  # blocks per book, chapter or verse
                if (path / f"{t}.{kind}zv").is_file():
                    self.files[t] = (path / f"{t}.{kind}zs", path / f"{t}.{kind}zv", path / f"{t}.{kind}zz")

    def entries(self, testament, first, count):
        """(block, offset, size) for `count` consecutive slots."""
        with open(self.files[testament][1], "rb") as f:
            f.seek(first * self.entry)
            raw = f.read(count * self.entry)
        fmt = "<III" if self.entry == 12 else "<IIH"
        return [struct.unpack_from(fmt, raw, k * self.entry) for k in range(len(raw) // self.entry)]


class Study:
    def __init__(self, root):
        self.root = Path(root)
        self._modules = None
        self._lock = threading.Lock()
        self._blocks = OrderedDict()
        self._block_bytes = 0

    def modules(self):
        """{id: (ZCom, meta)} for every commentary present in the library."""
        if self._modules is None:
            with self._lock:
                if self._modules is None:
                    found = {}
                    base = self.root / SWORD_DIR
                    for mid, name in COMMENTARIES:
                        conf = base / "mods.d" / f"{mid}.conf"
                        if not conf.is_file():
                            continue
                        c = gift_library._read_conf(conf)
                        path = (base / c.get("DataPath", "")).resolve()
                        if base.resolve() not in path.parents or not path.is_dir():
                            continue
                        z = ZCom(path, c.get("ModDrv", "").lower() == "zcom4")
                        if not z.files:
                            continue
                        licence = c.get("DistributionLicense", "")
                        found[mid] = (z, {
                            "id": mid, "name": name, "licence": licence,
                            "free": licence.lower().startswith("public domain") or not licence,
                            "ot": "ot" in z.files, "nt": "nt" in z.files,
                            "kind": "crossrefs" if mid == "tsk" else "commentary"})
                    self._modules = found
        return self._modules

    def catalogue(self):
        return [meta for _, meta in self.modules().values()]

    def _text(self, z, testament, block, offset, size):
        key = (z.path, testament, block)
        raw = self._blocks.get(key)
        if raw is None:
            bzs, _, bzz = z.files[testament]
            with open(bzs, "rb") as f:
                f.seek(block * 12)
                boff, bsize, _ = struct.unpack("<III", f.read(12))
            with open(bzz, "rb") as f:
                f.seek(boff)
                raw = zlib.decompress(f.read(bsize))
            with self._lock:
                self._blocks[key] = raw
                self._block_bytes += len(raw)
                while self._block_bytes > BLOCK_CACHE_BYTES and len(self._blocks) > 1:
                    _, old = self._blocks.popitem(last=False)
                    self._block_bytes -= len(old)
        else:
            with self._lock:
                if key in self._blocks:
                    self._blocks.move_to_end(key)
        return raw[offset:offset + size].decode("utf-8", "replace")

    def note(self, mid, book, chapter, verse):
        """The note covering one verse: {module, name, from, to, nearest, blocks}.
        A verse with no note of its own gets the nearest note before it in
        the chapter (commentators often write one note per paragraph)."""
        entry = self.modules().get(mid)
        slot = SLOTS.get((book, chapter))
        if entry is None or slot is None:
            return None
        z, meta = entry
        testament, head, count = slot
        if testament not in z.files or not 1 <= verse <= count:
            return None
        rows = z.entries(testament, head + 1, count)  # verses 1..count
        if len(rows) < verse:
            return None
        v, nearest = verse, False
        while v >= 1 and rows[v - 1][2] == 0:
            v, nearest = v - 1, True
        if v < 1:
            return None
        loc = rows[v - 1]
        first = v
        while first > 1 and rows[first - 2] == loc:
            first -= 1
        last = v
        while last < count and rows[last] == loc:
            last += 1
        text = self._text(z, testament, *loc)
        blocks = to_blocks(text, book, chapter)
        if not blocks:
            return None
        return {"module": mid, "name": meta["name"], "licence": meta["licence"],
                "b": book, "c": chapter, "from": first, "to": last, "nearest": nearest,
                "blocks": blocks}


# ---------------------------------------------------------- dictionaries

DICTIONARIES = (
    ("easton", "Easton's Bible Dictionary"),
    ("smith", "Smith's Bible Dictionary"),
    ("isbe", "International Standard Bible Encyclopedia"),
    ("nave", "Nave's Topical Bible"),
    ("torrey", "Torrey's Topical Textbook"),
    ("hitchcock", "Hitchcock's Bible Names"),
    ("strongsgreek", "Strong's Greek"),
    ("strongshebrew", "Strong's Hebrew"),
)


class RawLD:
    """SWORD RawLD: .idx is (offset uint32, size uint16) into .dat, where
    each record is the key, a newline, then the entry."""

    def __init__(self, base):
        self.idx = base.with_suffix(".idx").read_bytes()
        self.dat_path = base.with_suffix(".dat")
        self.keys = {}
        with open(self.dat_path, "rb") as dat:
            for i in range(len(self.idx) // 6):
                off, size = struct.unpack_from("<IH", self.idx, i * 6)
                dat.seek(off)
                head = dat.read(min(size, 120))
                nl = head.find(b"\n")
                if nl > 0:
                    key = head[:nl].decode("utf-8", "replace").strip().rstrip("\\")
                    self.keys[key] = (off, size, nl)

    def raw(self, key):
        loc = self.keys.get(key)
        if loc is None:
            return None
        off, size, nl = loc
        with open(self.dat_path, "rb") as dat:
            dat.seek(off + nl + 1)
            return dat.read(size - nl - 1).decode("utf-8", "replace")


class Dictionaries:
    def __init__(self, root):
        self.root = Path(root)
        self._mods = None
        self._lock = threading.Lock()

    def modules(self):
        if self._mods is None:
            with self._lock:
                if self._mods is None:
                    found = {}
                    base = self.root / SWORD_DIR
                    for mid, name in DICTIONARIES:
                        conf = base / "mods.d" / f"{mid}.conf"
                        if not conf.is_file():
                            continue
                        c = gift_library._read_conf(conf)
                        path = (base / c.get("DataPath", "")).resolve()
                        if base.resolve() not in path.parents:
                            continue
                        try:
                            if c.get("ModDrv") == "zLD":
                                reader = gift_library.Devotional(path, None, name)
                            elif c.get("ModDrv") == "RawLD":
                                reader = RawLD(path)
                            else:
                                continue
                        except OSError:
                            continue
                        upper = {}
                        for k in reader.keys:
                            upper.setdefault(k.upper(), k)
                        found[mid] = (reader, name, upper, sorted(upper))
                    self._mods = found
        return self._mods

    def lookup(self, word, limit=12):
        """Entries for a word or topic in every dictionary, or a Strong's
        number ('G26', 'H430'); plus nearby headwords to try next."""
        q = " ".join(str(word or "").split()).upper()[:60]
        if not q:
            return {"q": "", "entries": [], "suggest": []}
        strongs = re.fullmatch(r"([GH])\s*0*(\d{1,5})", q)
        entries, suggest = [], set()
        for mid, (reader, name, upper, ordered) in self.modules().items():
            if strongs:
                if (strongs[1] == "G") != (mid == "strongsgreek") or mid not in ("strongsgreek", "strongshebrew"):
                    continue
                key = upper.get(strongs[2].zfill(5))
            else:
                if mid.startswith("strongs"):
                    continue
                key = upper.get(q)
                import bisect
                i = bisect.bisect_left(ordered, q)
                for k in ordered[i:i + 6]:
                    if k.startswith(q[:3]):
                        suggest.add(upper[k].title() if k.isupper() else upper[k])
            if key:
                text = reader.raw(key)
                if text:
                    blocks = to_blocks(text)
                    if blocks:
                        entries.append({"dict": mid, "name": name, "key": key, "blocks": blocks})
            if len(entries) >= limit:
                break
        suggest.discard(q.title())
        return {"q": q, "entries": entries, "suggest": sorted(suggest)[:12]}
