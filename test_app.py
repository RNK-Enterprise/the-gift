"""Tests for the app: the library engine (gift_library), accounts and study
groups (gift_community), the church finder (gift_places) and the HTTP API
as served by server.py.

Like test_server, everything runs against a tiny fixture library, so the
suite is fast and independent of the real 1.8GB tree.

Run with: python3 -m unittest test_app
"""

import os

os.environ.setdefault("GIFT_MAX_CONCURRENT", "8")

import http.client
import json
import struct
import tempfile
import threading
import time
import unittest
import zlib
from pathlib import Path

import gift_api
import gift_community
import gift_library
import gift_places
import server as gift

TST = """TST: Test Version
== Genesis 1 ==
1. In the beginning God created the heaven and the earth.
2. And the earth was without form, and void.
== Genesis 2 ==
1. Thus the heavens and the earth were finished.
== Genesis 3 ==
1.
2.
== Exodus 1 ==
1.
== John 1 ==
1. In the beginning was the Word.
2. The same was in the beginning with God.
== John 2 ==
1. And the third day there was a marriage in Cana.
== John 3 ==
1. There was a man of the Pharisees, named Nicodemus.
16. For God so loved the world, that he gave his only begotten Son.
17. Beloved, let us love one another.
"""

GRK = """GRK: Greek Test
== John 1 ==
1. Ἐν ἀρχῇ ἦν ὁ λόγος, καὶ ὁ λόγος ἦν πρὸς τὸν θεόν.
2. οὗτος ἦν ἐν ἀρχῇ πρὸς τὸν θεόν.
"""

EMPTY = """EMPTY: Nothing Here
== Genesis 1 ==
1.
2.
"""

LICENCES = """# Bibles

| ID | Lang | Title | Licence | Class |
|---|---|---|---|---|
| `TST` | en | Test Version | Public Domain | Public domain |
| `GRK` | grc | Greek Test | CC BY-NC-SA 4.0 | Non-commercial — upstream says otherwise |
"""

DEVO_CONF = """[SME]
DataPath=./modules/lexdict/zld/devotionals/sme/sme
ModDrv=zLD
Description=Test Morning and Evening
"""

ENTRY = (
    '<div type="entry" osisID="01.01"><div type="section" osisID="01.01.am">'
    '<title>Morning, January 1</title><p><hi type="italic">“They did eat.”</hi><lb/>'
    '<reference osisRef="Bible:Josh.5.12">Joshua 5:12</reference></p>'
    '<p>Israel’s wanderings &amp; rest. <script>alert(1)</script></p></div>'
    '<div type="section" osisID="01.01.pm"><title>Evening, January 1</title>'
    '<p><hi type="italic">“We will rejoice.”</hi><lb/><reference osisRef="Bible:Song.1.4">Song 1:4</reference></p>'
    '<lg><l>Line one,</l><l>line two.</l></lg></div></div>')


def write_zld(base, entries):
    """A minimal SWORD zLD module: one zlib block holding every entry."""
    texts = [t.encode("utf-8") for _, t in entries]
    table, body = b"", b""
    start = 4 + 8 * len(texts)
    for t in texts:
        table += struct.pack("<II", start + len(body), len(t))
        body += t
    z = zlib.compress(struct.pack("<I", len(texts)) + table + body)
    idx, dat = b"", b""
    for i, (key, _) in enumerate(entries):
        rec = key.encode() + b"\n" + struct.pack("<II", 0, i)
        idx += struct.pack("<II", len(dat), len(rec))
        dat += rec
    base.parent.mkdir(parents=True, exist_ok=True)
    for ext, data in ((".idx", idx), (".dat", dat), (".zdx", struct.pack("<II", 0, len(z))), (".zdt", z)):
        base.with_suffix(ext).write_bytes(data)


def make_library(root):
    text = root / "Bibles/formats/text"
    text.mkdir(parents=True)
    (text / "TST.txt").write_text(TST, encoding="utf-8")
    (text / "GRK.txt").write_text(GRK, encoding="utf-8")
    (text / "EMPTY.txt").write_text(EMPTY, encoding="utf-8")
    (root / "Bibles/README.md").write_text(LICENCES, encoding="utf-8")
    sword = root / "Study Guides/Commentaries and Reference"
    (sword / "mods.d").mkdir(parents=True)
    (sword / "mods.d/sme.conf").write_text(DEVO_CONF, encoding="utf-8")
    write_zld(sword / "modules/lexdict/zld/devotionals/sme/sme", [("01.01", ENTRY)])


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        make_library(cls.root)
        cls.lib = gift_library.Library(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_blank_chapters_and_books_are_dropped(self):
        books = self.lib.books("TST")["books"]
        self.assertEqual([b["name"] for b in books], ["Genesis", "John"])  # Exodus is all blank
        self.assertEqual(books[0]["chapters"], [1, 2])                     # Genesis 3 is blank
        self.assertEqual(self.lib.books("EMPTY")["books"], [])

    def test_catalogue(self):
        cat = {t["id"]: t for t in self.lib.catalogue()}
        self.assertEqual(set(cat), {"TST", "GRK", "EMPTY"})
        self.assertEqual((cat["TST"]["ot"], cat["TST"]["nt"]), (1, 1))
        self.assertEqual(cat["TST"]["title"], "Test Version")
        self.assertEqual(cat["GRK"]["lang"], "grc")
        self.assertEqual(cat["GRK"]["class"], "Non-commercial")  # note after the dash dropped
        self.assertEqual(cat["EMPTY"]["ot"] + cat["EMPTY"]["nt"] + cat["EMPTY"]["other"], 0)

    def test_chapter_and_neighbours(self):
        ch = self.lib.chapter("TST", "John", 1)
        self.assertEqual(ch["verses"][0], [1, "In the beginning was the Word."])
        self.assertEqual(ch["prev"], ["Genesis", 2])  # across books, skipping blank Genesis 3
        self.assertEqual(ch["next"], ["John", 2])
        self.assertIsNone(self.lib.chapter("TST", "Genesis", 1)["prev"])
        self.assertIsNone(self.lib.chapter("TST", "John", 3)["next"])
        self.assertEqual([v[0] for v in self.lib.chapter("TST", "John", 3)["verses"]], [1, 16, 17])

    def test_missing_things_are_none(self):
        self.assertIsNone(self.lib.chapter("TST", "Genesis", 3))
        self.assertIsNone(self.lib.chapter("TST", "Revelation of John", 1))
        self.assertIsNone(self.lib.chapter("NOPE", "John", 1))

    def test_translation_ids_cannot_escape(self):
        for bad in ("../README", "TST/..", "..", "", "a" * 41, "TST.txt"):
            self.assertIsNone(self.lib.get(bad), bad)

    def test_symlinked_translation_outside_is_refused(self):
        outside = Path(self.tmp.name).parent / f"outside-{os.getpid()}.txt"
        outside.write_text(TST, encoding="utf-8")
        link = self.root / "Bibles/formats/text/LINK.txt"
        link.symlink_to(outside)
        try:
            self.assertIsNone(self.lib.get("LINK"))
        finally:
            link.unlink()
            outside.unlink()

    def test_changed_file_is_reindexed(self):
        path = self.root / "Bibles/formats/text/CHG.txt"
        path.write_text("CHG: Change\n== John 1 ==\n1. old text\n", encoding="utf-8")
        try:
            self.assertEqual(self.lib.chapter("CHG", "John", 1)["verses"], [[1, "old text"]])
            path.write_text("CHG: Change\n== John 1 ==\n1. a much longer new text\n", encoding="utf-8")
            self.assertEqual(self.lib.chapter("CHG", "John", 1)["verses"], [[1, "a much longer new text"]])
        finally:
            path.unlink()

    def test_search_folds_accents_and_case(self):
        r = self.lib.search("GRK", "ΘΕΟΝ")  # matches θεόν
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["hits"][0][:3], ["John", 1, 1])
        self.assertEqual(self.lib.search("GRK", "αρχη")["total"], 2)

    def test_search_words_start_at_word_boundaries(self):
        hits = self.lib.search("TST", "love")["hits"]
        self.assertEqual([h[2] for h in hits], [16, 17])  # loved, love — not "Beloved"
        self.assertEqual(self.lib.search("TST", "eloved")["total"], 0)

    def test_search_all_words_and_phrases(self):
        self.assertEqual(self.lib.search("TST", "earth heaven")["total"], 2)
        self.assertEqual(self.lib.search("TST", '"the heaven and"')["total"], 1)
        self.assertEqual(self.lib.search("TST", "“so loved”")["total"], 1)

    def test_search_scope_limit_and_numbers(self):
        self.assertEqual(self.lib.search("TST", "beginning", book="John")["total"], 2)
        r = self.lib.search("TST", "the", limit=2)
        self.assertGreater(r["total"], 2)
        self.assertEqual(len(r["hits"]), 2)
        self.assertEqual(self.lib.search("TST", "16")["total"], 0)  # verse numbers aren't text
        self.assertEqual(self.lib.search("TST", "   ")["total"], 0)

    def test_split_days(self):
        weights = [5, 1, 1, 1, 9, 2, 2, 3, 3, 1]
        cuts = gift_library.split_days(weights, 4)
        self.assertEqual(len(cuts), 4)
        self.assertEqual(cuts[-1], len(weights))
        self.assertEqual(cuts, sorted(set(cuts)))  # every day has at least one chapter
        with self.assertRaises(ValueError):
            gift_library.split_days([1, 2], 3)
        big = gift_library.split_days([1] * 1189, 365)
        sizes = [b - a for a, b in zip([0] + big, big)]
        self.assertLessEqual(max(sizes) - min(sizes), 1)

    def test_plans_need_their_books(self):
        self.assertEqual(self.lib.plans(), {})  # the fixture has no full Bible
        orig = gift_library.PLANS
        gift_library.PLANS = (("tiny", "Tiny", "Test plan", 2, (("Genesis", "John"),)),)
        try:
            lib = gift_library.Library(self.root)
            p = lib.plans()["tiny"]
            self.assertEqual(p["length"], 2)
            self.assertEqual(p["chapters"], 5)
            flat = [seg for day in p["days"] for seg in day]
            self.assertEqual(flat[0][0], "Genesis")
            self.assertEqual(flat[-1], ["John", flat[-1][1], 3])
        finally:
            gift_library.PLANS = orig

    def test_devotional(self):
        e = self.lib.devotional_entry(1, 1)
        self.assertEqual(e["morning"]["title"], "Morning, January 1")
        self.assertEqual(e["morning"]["verse"], {"text": "“They did eat.”", "label": "Joshua 5:12",
                                                 "ref": {"b": "Joshua", "c": 5, "v": 12}})
        self.assertEqual(e["evening"]["verse"]["ref"], {"b": "Song of Solomon", "c": 1, "v": 4})
        self.assertEqual(e["evening"]["blocks"], [{"poem": [[{"t": "Line one,"}], [{"t": "line two."}]]}])
        body = json.dumps(e["morning"]["blocks"], ensure_ascii=False)
        self.assertIn("wanderings & rest", body)
        self.assertNotIn("<script", body)  # markup never survives: only text runs
        self.assertIsNone(self.lib.devotional_entry(2, 2))


class FakeFetch:
    def __init__(self):
        self.calls = []

    def __call__(self, url, data=None, timeout=25):
        self.calls.append(url)
        if "nominatim" in url or "search" in url:
            return [{"display_name": "Leeds, West Yorkshire, England", "lat": "53.7974", "lon": "-1.5438"}]
        return {"elements": [
            {"type": "node", "id": 1, "lat": 53.80, "lon": -1.55,
             "tags": {"name": "St Anne's", "denomination": "roman_catholic", "website": "javascript:alert(1)",
                      "addr:street": "Cookridge Street", "addr:city": "Leeds"}},
            {"type": "way", "id": 2, "center": {"lat": 53.7975, "lon": -1.5440},
             "tags": {"name": "Leeds Minster", "website": "leedsminster.org", "service_times": "Su 10:30"}},
            {"type": "node", "id": 3, "lat": 53.7976, "lon": -1.5439, "tags": {}},
            {"type": "relation", "id": 4, "tags": {"name": "No position"}},
        ]}


class PlacesTests(unittest.TestCase):
    def test_churches_parsed_sorted_and_sanitised(self):
        fake = FakeFetch()
        places = gift_places.Places(fetch=fake)
        out = places.churches(53.79741, -1.54382, 5000)
        self.assertEqual([p["name"] for p in out], ["Leeds Minster", "St Anne's", ""])  # named first, nearest first
        self.assertEqual(out[0]["website"], "https://leedsminster.org")
        self.assertEqual(out[1]["website"], "")  # javascript: links are dropped
        self.assertEqual(out[1]["denomination"], "roman catholic")
        self.assertEqual(out[1]["address"], "Cookridge Street, Leeds")
        places.churches(53.80, -1.54, 5000)  # same rounded square: cached
        self.assertEqual(len(fake.calls), 1)

    def test_location_is_rounded_before_leaving(self):
        seen = []

        def fetch(url, data=None, timeout=25):
            seen.append(data.decode())
            return {"elements": []}
        gift_places.Places(fetch=fetch).churches(51.507351, -0.127758, 2000)
        self.assertIn("51.51", seen[0])
        self.assertNotIn("51.507", seen[0])

    def test_geocode(self):
        out = gift_places.Places(fetch=FakeFetch()).geocode("Leeds")
        self.assertEqual(out, [{"name": "Leeds, West Yorkshire, England", "lat": 53.7974, "lon": -1.5438}])

    def test_busy_upstream_is_retried_once(self):
        import urllib.error
        calls = []

        def flaky(url, data=None, timeout=25):
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(url, 504, "Gateway Timeout", {}, None)
            return {"elements": []}
        self.assertEqual(gift_places.Places(fetch=flaky, retry_after=0).churches(1, 1, 2000), [])
        self.assertEqual(len(calls), 2)

        def refused(url, data=None, timeout=25):
            calls.append(url)
            raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)
        calls.clear()
        with self.assertRaises(gift_places.PlacesError):
            gift_places.Places(fetch=refused, retry_after=0).churches(2, 2, 2000)
        self.assertEqual(len(calls), 1)  # a real error isn't retried

    def test_upstream_failure_is_a_places_error(self):
        def broken(*a, **k):
            raise OSError("down")
        with self.assertRaises(gift_places.PlacesError):
            gift_places.Places(fetch=broken).churches(1, 1, 2000)


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        plans = {"tiny": {"id": "tiny", "length": 3}}
        verses = lambda t, b, c, v1, v2: [[n, f"verse {n}"] for n in range(v1, v2 + 1)] if b == "John" else None
        self.c = gift_community.Community(Path(self.tmp.name) / "c.sqlite3", plans=lambda: plans, verses=verses)
        self.ann = self.c.signup("ann", "Ann", "password-ann", "1.1.1.1")[1]
        self.ben = self.c.signup("ben", "Ben", "password-ben", "1.1.1.1")[1]

    def tearDown(self):
        self.tmp.cleanup()

    def group(self):
        g = self.c.create_group(self.ann, {"name": "Home group"})
        self.c.join(self.ben, g["invite"], "1.1.1.1")
        return g

    def test_leaving_leader_hands_over_and_last_one_out_deletes(self):
        g = self.group()
        self.c.leave(self.ann, g["id"])
        self.assertEqual(self.c.group(self.ben, g["id"])["role"], "leader")
        self.c.leave(self.ben, g["id"])
        with self.c._db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM study_groups WHERE id=?", (g["id"],)).fetchone())

    def test_reset_invite_kills_old_link(self):
        g = self.group()
        new = self.c.reset_invite(self.ann, g["id"])["invite"]
        self.assertNotEqual(new, g["invite"])
        with self.assertRaises(gift_community.Problem):
            self.c.preview_invite(g["invite"])

    def test_progress_needs_a_plan_and_a_real_day(self):
        g = self.group()
        with self.assertRaises(gift_community.Problem):
            self.c.set_progress(self.ben, g["id"], 1, True)
        self.c.update_group(self.ann, g["id"], {"plan": "tiny", "plan_start": "2026-10-01"})
        out = self.c.set_progress(self.ben, g["id"], 2, True)
        self.assertEqual(out["my_days"], [2])
        with self.assertRaises(gift_community.Problem):
            self.c.set_progress(self.ben, g["id"], 4, True)
        # changing the plan clears progress
        self.c.update_group(self.ann, g["id"], {"plan": "tiny", "plan_start": "2026-11-01"})
        self.assertEqual(self.c.group(self.ben, g["id"])["my_days"], [])

    def test_shared_verses_are_quoted_by_the_server(self):
        g = self.group()
        m = self.c.post(self.ben, g["id"], "look", {"t": "KJV", "b": "John", "c": 3, "v": 16, "v2": 17, "text": "forged"})
        self.assertEqual(m["ref"]["text"], "verse 16 verse 17")
        with self.assertRaises(gift_community.Problem):
            self.c.post(self.ben, g["id"], "", {"t": "KJV", "b": "Nope", "c": 1, "v": 1})
        with self.assertRaises(gift_community.Problem):
            self.c.post(self.ben, g["id"], "", {"t": "KJV", "b": "John", "c": 1, "v": 1, "v2": 30})

    def test_message_cleaning_and_unread(self):
        g = self.group()
        m = self.c.post(self.ben, g["id"], "  hi\x00 there\n\n\n\n\nbye  ", None)
        self.assertEqual(m["body"], "hi there\n\nbye")
        self.assertEqual(self.c.groups(self.ann)[0]["unread"], 1)
        self.c.messages(self.ann, g["id"])
        self.assertEqual(self.c.groups(self.ann)[0]["unread"], 0)

    def test_delete_account_removes_messages_and_membership(self):
        g = self.group()
        self.c.post(self.ben, g["id"], "bye", None)
        with self.assertRaises(gift_community.Problem):
            self.c.delete_account(self.ben, "wrong password")
        self.c.delete_account(self.ben, "password-ben")
        self.assertEqual(self.c.messages(self.ann, g["id"]), [])
        self.assertEqual([m["username"] for m in self.c.group(self.ann, g["id"])["members"]], ["ann"])
        with self.assertRaises(gift_community.Problem):
            self.c.login("ben", "password-ben", "2.2.2.2")

    def test_failed_logins_are_limited_per_account(self):
        for _ in range(10):
            with self.assertRaises(gift_community.Problem) as e:
                self.c.login("ann", "nope-nope", "3.3.3.3")
            self.assertEqual(e.exception.status, 401)
        with self.assertRaises(gift_community.Problem) as e:
            self.c.login("ann", "password-ann", "4.4.4.4")  # even the right password, for now
        self.assertEqual(e.exception.status, 429)
        # successful sign-ins never count: a whole room can sign in at once
        token, _ = self.c.login("ben", "password-ben", "3.3.3.3")
        self.assertTrue(token)

    def test_change_and_reset_password(self):
        old_token, _ = self.c.login("ann", "password-ann", "6.6.6.6")
        with self.assertRaises(gift_community.Problem):
            self.c.change_password(self.ann, "wrong", "new-password-1")
        token = self.c.change_password(self.ann, "password-ann", "new-password-1")
        self.assertIsNone(self.c.session_user(old_token))  # other devices signed out
        self.assertEqual(self.c.session_user(token)["username"], "ann")
        temp = self.c.reset_password("ANN")
        self.assertIsNone(self.c.session_user(token))
        self.assertTrue(self.c.login("ann", temp, "6.6.6.6")[0])
        with self.assertRaises(gift_community.Problem):
            self.c.reset_password("nobody")

    def test_sessions_expire_and_log_out(self):
        token, user = self.c.login("ann", "password-ann", "5.5.5.5")
        self.assertEqual(self.c.session_user(token)["id"], user["id"])
        self.c.logout(token)
        self.assertIsNone(self.c.session_user(token))
        self.assertIsNone(self.c.session_user("x" * 200))


class APITests(unittest.TestCase):
    """The API over real HTTP, through server.py's handler."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / "lib"
        root.mkdir()
        make_library(root)
        (root / "app/js").mkdir(parents=True)
        (root / "app/index.html").write_text("<!doctype html><title>The Gift</title>", encoding="utf-8")
        (root / "app/js/main.js").write_text("console.log(1)\n", encoding="utf-8")
        cls._orig = (gift.ROOT, gift.DATA_DIR)
        gift.ROOT, gift.DATA_DIR = root, Path(cls.tmp.name) / "data"
        gift.get_app().places = gift_places.Places(fetch=FakeFetch())
        cls.httpd = gift.BoundedThreadingHTTPServer(("127.0.0.1", 0), gift.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.origin = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        gift.ROOT, gift.DATA_DIR = cls._orig
        cls.tmp.cleanup()

    def call(self, method, path, body=None, cookie=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}"}
        if method == "POST":
            h.update({"Origin": self.origin, "Content-Type": "application/json"})
        if cookie:
            h["Cookie"] = f"gift_session={cookie}"
        h.update(headers or {})
        payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        try:
            conn.request(method, path, body=payload, headers=h)
            resp = conn.getresponse()
            data = resp.read()
            try:
                parsed = json.loads(data) if data else None
            except ValueError:
                parsed = data
            return resp, parsed
        finally:
            conn.close()

    def signup(self, username):
        resp, data = self.call("POST", "/api/signup", {"username": username, "name": username.title(),
                                                       "password": "a good password"})
        self.assertEqual(resp.status, 200, data)
        cookie = resp.getheader("Set-Cookie")
        return cookie.split(";")[0].split("=", 1)[1], data["user"]

    # -- the app page

    def test_app_page_has_its_own_csp(self):
        resp, _ = self.call("GET", "/app/")
        self.assertEqual(resp.status, 200)
        csp = resp.getheader("Content-Security-Policy")
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp.split("script-src")[1].split(";")[0])
        self.assertEqual(resp.getheader("Cache-Control"), "no-cache")
        resp, _ = self.call("GET", "/app")
        self.assertEqual(resp.status, 301)
        self.assertTrue(resp.getheader("Location").endswith("/app/"))

    def test_app_assets_always_revalidate(self):
        resp, _ = self.call("GET", "/app/js/main.js")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Cache-Control"), "no-cache")
        self.assertTrue(resp.getheader("Content-Type").startswith("text/javascript"))

    def test_data_dir_is_never_served(self):
        self.signup("datacheck")  # makes sure the database exists
        resp, _ = self.call("GET", "/.data/community.sqlite3")
        self.assertEqual(resp.status, 404)

    # -- library endpoints

    def test_library_endpoints(self):
        resp, data = self.call("GET", "/api/translations")
        self.assertEqual(resp.status, 200)
        self.assertIn("max-age", resp.getheader("Cache-Control"))
        self.assertEqual({t["id"] for t in data["translations"]}, {"TST", "GRK", "EMPTY"})
        resp, data = self.call("GET", "/api/chapter?t=TST&b=John&c=3")
        self.assertEqual(data["verses"][1], [16, "For God so loved the world, that he gave his only begotten Son."])
        resp, data = self.call("GET", "/api/search?t=GRK&q=%CE%B8%CE%B5%CE%BF%CE%BD")
        self.assertEqual(data["total"], 2)
        resp, data = self.call("GET", "/api/devotional?date=01-01")
        self.assertEqual(data["evening"]["title"], "Evening, January 1")

    def test_library_errors(self):
        for path, status in (("/api/books?t=NOPE", 404), ("/api/chapter?t=TST&b=John&c=x", 400),
                             ("/api/chapter?t=TST&b=John&c=9", 404), ("/api/search?t=TST&q=", 400),
                             ("/api/devotional?date=13-01", 400), ("/api/plans/nope", 404),
                             ("/api/nothing", 404), ("/api/books?t=../../etc/passwd", 404)):
            resp, data = self.call("GET", path)
            self.assertEqual(resp.status, status, path)
            self.assertIn("error", data)

    # -- POST guards

    def test_post_needs_same_origin_json(self):
        resp, _ = self.call("POST", "/api/login", {}, headers={"Origin": "https://evil.example"})
        self.assertEqual(resp.status, 403)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", "/api/login", body=b"{}", headers={"Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 403)  # no Origin at all
        conn.close()
        resp, _ = self.call("POST", "/api/login", raw=b"a=b", headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(resp.status, 415)
        resp, _ = self.call("POST", "/api/login", raw=b"{nope")
        self.assertEqual(resp.status, 400)
        resp, _ = self.call("POST", "/api/login", raw=b"x" * (gift.MAX_BODY + 1))
        self.assertEqual(resp.status, 413)

    def test_post_elsewhere_is_404(self):
        resp, _ = self.call("POST", "/README.md", {})
        self.assertEqual(resp.status, 404)

    def test_group_endpoints_need_a_session(self):
        for method, path in (("GET", "/api/groups"), ("POST", "/api/groups"), ("GET", "/api/groups/1/messages")):
            resp, data = self.call(method, path, {} if method == "POST" else None)
            self.assertEqual(resp.status, 401, path)

    # -- accounts and groups end to end

    def test_session_cookie_flags(self):
        resp, _ = self.call("POST", "/api/signup", {"username": "cookies", "password": "a good password"})
        cookie = resp.getheader("Set-Cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertNotIn("Secure", cookie)  # plain http on the LAN
        resp, _ = self.call("POST", "/api/signup", {"username": "cookies2", "password": "a good password"},
                            headers={"X-Forwarded-Proto": "https"})
        self.assertIn("Secure", resp.getheader("Set-Cookie"))  # behind the tunnel (from loopback)

    def test_study_group_flow(self):
        leader, _ = self.signup("leader1")
        member, member_user = self.signup("member1")
        outsider, _ = self.signup("outsider1")

        resp, g = self.call("POST", "/api/groups", {"name": "Thursday group", "area": "Leeds"}, cookie=leader)
        self.assertEqual(resp.status, 200, g)
        gid, code = g["id"], g["invite"]

        resp, preview = self.call("GET", f"/api/invites/{code}")
        self.assertEqual(preview["name"], "Thursday group")
        self.assertNotIn("invite", preview)

        resp, joined = self.call("POST", "/api/groups/join", {"code": code}, cookie=member)
        self.assertEqual(joined["role"], "member")

        resp, m = self.call("POST", f"/api/groups/{gid}/messages",
                            {"body": "Hello", "ref": {"t": "TST", "b": "John", "c": 3, "v": 16}}, cookie=member)
        self.assertEqual(resp.status, 200, m)
        self.assertEqual(m["ref"]["text"], "For God so loved the world, that he gave his only begotten Son.")

        resp, data = self.call("GET", f"/api/groups/{gid}/messages", cookie=leader)
        self.assertEqual([x["body"] for x in data["messages"]], ["Hello"])
        resp, data = self.call("GET", f"/api/groups/{gid}/messages?after={m['id']}", cookie=leader)
        self.assertEqual(data["messages"], [])

        # outsiders can't see it exists; members can't moderate
        resp, _ = self.call("GET", f"/api/groups/{gid}/messages", cookie=outsider)
        self.assertEqual(resp.status, 404)
        resp, _ = self.call("POST", f"/api/groups/{gid}/delete", {}, cookie=member)
        self.assertEqual(resp.status, 403)
        resp, _ = self.call("POST", f"/api/groups/{gid}/messages", {"body": "sneaky"}, cookie=outsider)
        self.assertEqual(resp.status, 404)

        # the leader removes the member, who then loses access
        resp, g = self.call("POST", f"/api/groups/{gid}/remove", {"user_id": member_user["id"]}, cookie=leader)
        self.assertEqual([x["username"] for x in g["members"]], ["leader1"])
        resp, _ = self.call("GET", f"/api/groups/{gid}", cookie=member)
        self.assertEqual(resp.status, 404)

        resp, _ = self.call("POST", f"/api/groups/{gid}/delete", {}, cookie=leader)
        self.assertEqual(resp.status, 200)
        resp, _ = self.call("GET", f"/api/invites/{code}")
        self.assertEqual(resp.status, 404)

    def test_logout_ends_session(self):
        token, _ = self.signup("leaver1")
        resp, data = self.call("GET", "/api/me", cookie=token)
        self.assertEqual(data["user"]["username"], "leaver1")
        resp, _ = self.call("POST", "/api/logout", {}, cookie=token)
        self.assertIn("Max-Age=0", resp.getheader("Set-Cookie"))
        resp, data = self.call("GET", "/api/me", cookie=token)
        self.assertIsNone(data["user"])

    # -- places

    def test_churches_endpoint(self):
        resp, data = self.call("GET", "/api/churches?lat=53.7974&lon=-1.5438&radius=5000")
        self.assertEqual(resp.status, 200, data)
        self.assertEqual(data["places"][0]["name"], "Leeds Minster")
        self.assertIn("OpenStreetMap", data["attribution"])
        for q in ("lat=x&lon=1&radius=5000", "lat=91&lon=1&radius=5000", "lat=1&lon=1&radius=7"):
            resp, _ = self.call("GET", f"/api/churches?{q}")
            self.assertEqual(resp.status, 400, q)


class LandingTests(unittest.TestCase):
    def test_landing_page_links_the_app(self):
        tmp = tempfile.TemporaryDirectory()
        orig = gift.ROOT
        gift.ROOT = Path(tmp.name)
        try:
            self.assertIn(b'href="/app/"', gift.landing_page())
        finally:
            gift.ROOT = orig
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
