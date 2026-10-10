"""Tests for the app's second wave: roles, friends, profiles, Bible
progress and rewards, uploads, music review, safety tools, plans and
payments, sync, offline downloads, and the zero-trust guards around them.

Run with: python3 -m unittest test_features
"""

import os

os.environ.setdefault("GIFT_MAX_CONCURRENT", "8")

import hashlib
import hmac
import http.client
import json
import sqlite3
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

import gift_billing
import gift_community
import gift_media
import gift_music
import gift_places
import gift_rewards
import server as gift
from test_app import FakeFetch, make_library

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 200


class CommunityFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        plans = {"tiny": {"id": "tiny", "length": 3}}
        verses = lambda t, b, c, v1, v2: [[n, f"verse {n}"] for n in range(v1, v2 + 1)] if b == "John" else None
        self.c = gift_community.Community(Path(self.tmp.name) / "c.sqlite3", plans=lambda: plans, verses=verses)
        self.users = {n: self.c.signup(n, n.title(), f"password-{n}", "1.1.1.1")[1] for n in ("ann", "ben", "cat", "dan")}

    def tearDown(self):
        self.tmp.cleanup()

    def group(self):
        g = self.c.create_group(self.users["ann"], {"name": "G"})
        for n in ("ben", "cat", "dan"):
            self.c.join(self.users[n], g["invite"], "1.1.1.1")
        return g["id"]

    # roles
    def test_roles_and_permissions(self):
        gid = self.group()
        ann, ben, cat, dan = (self.users[n] for n in ("ann", "ben", "cat", "dan"))
        with self.assertRaises(gift_community.Problem):
            self.c.set_role(ben, gid, cat["id"], "moderator")  # members can't hand out roles
        g = self.c.set_role(ann, gid, ben["id"], "moderator", "Prayer lead")
        b = next(m for m in g["members"] if m["id"] == ben["id"])
        self.assertEqual((b["role"], b["title"]), ("moderator", "Prayer lead"))
        # a moderator can delete others' messages and remove members, not leaders
        mid = self.c.post(cat, gid, "hello", None)["id"]
        self.c.delete_message(ben, gid, mid)
        self.c.remove_member(ben, gid, dan["id"])
        with self.assertRaises(gift_community.Problem):
            self.c.remove_member(ben, gid, ann["id"])
        self.assertTrue(self.c.group(ben, gid)["can"]["moderate"])
        self.assertFalse(self.c.group(ben, gid)["can"]["edit"])
        # the last leader can't step down
        with self.assertRaises(gift_community.Problem):
            self.c.set_role(ann, gid, ann["id"], "member")

    def test_leader_leaving_promotes_moderator_first(self):
        gid = self.group()
        self.c.set_role(self.users["ann"], gid, self.users["cat"]["id"], "moderator")
        self.c.leave(self.users["ann"], gid)
        self.assertEqual(self.c.group(self.users["cat"], gid)["role"], "leader")

    # friends and blocks
    def test_friend_requests(self):
        ann, ben = self.users["ann"], self.users["ben"]
        self.assertEqual(self.c.friend_request(ann, "ben"), "outgoing")
        self.assertEqual(self.c.profile(ben, "ann")["relationship"], "incoming")
        self.assertEqual(self.c.friend_accept(ben, ann["id"]), "friends")
        self.assertEqual(self.c.profile(ann, "ben")["friends"], 1)
        self.c.friend_remove(ann, ben["id"])
        self.assertEqual(self.c.friends(ann)["friends"], [])
        # asking someone who already asked you is accepting
        self.c.friend_request(ben, "ann")
        self.assertEqual(self.c.friend_request(ann, "ben"), "friends")

    def test_block_hides_messages_and_stops_requests(self):
        gid = self.group()
        ann, ben = self.users["ann"], self.users["ben"]
        self.c.post(ben, gid, "from ben", None)
        self.c.block(ann, ben["id"])
        self.assertEqual([m["body"] for m in self.c.messages(ann, gid)], [])
        self.assertEqual([m["body"] for m in self.c.messages(self.users["cat"], gid)], ["from ben"])
        with self.assertRaises(gift_community.Problem):
            self.c.friend_request(ben, "ann")

    def test_reports_snapshot_and_suspension(self):
        gid = self.group()
        ann, ben = self.users["ann"], self.users["ben"]
        mid = self.c.post(ben, gid, "something nasty", None)["id"]
        self.c.report(ann, "message", mid, "harassment", "please look")
        with self.assertRaises(gift_community.Problem):
            self.c.report(ann, "message", mid, "made-up-reason")
        admin = dict(ann, is_admin=True, verified=True)
        reports = self.c.reports_open(admin)
        self.assertEqual(reports[0]["snapshot"]["body"], "something nasty")
        token, _ = self.c.login("ben", "password-ben", "2.2.2.2")
        self.c.resolve_report(admin, reports[0]["id"], "suspend-user")
        self.assertIsNone(self.c.session_user(token))  # signed out everywhere
        with self.assertRaises(gift_community.Problem) as e:
            self.c.login("ben", "password-ben", "2.2.2.2")
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(gift_community.Problem):
            self.c.reports_open(dict(ann, is_admin=True, verified=False))  # step-up required

    # profiles, progress, rewards
    def test_profile_progress_and_rewards(self):
        ann = self.users["ann"]
        self.c.update_profile(ann, {"bio": "Hello", "verse": {"t": "KJV", "b": "John", "c": 3, "v": 16},
                                    "show_progress": True})
        self.c.mark_chapters(ann, [["Jude", 1], ["Philemon", 1], ["John", 1]], day="2026-10-01")
        self.c.mark_chapters(ann, [["John", 2]], day="2026-10-02")
        p = self.c.profile(self.users["ben"], "ann")
        self.assertEqual(p["verse"]["text"], "verse 16")
        self.assertEqual(p["progress"]["read"], 4)
        r = self.c.rewards(ann["id"])
        earned = {b["id"] for b in r["badges"] if b["earned"]}
        self.assertTrue({"first-chapter", "book-1"} <= earned)  # Jude and Philemon are whole books
        self.assertEqual(r["best_streak"], 2)
        self.assertEqual(r["points"], 4 * gift_rewards.POINTS_PER_CHAPTER + sum(b["points"] for b in r["badges"] if b["earned"]))
        with self.assertRaises(gift_community.Problem):
            self.c.mark_chapters(ann, [["Hezekiah", 1]])  # not a book
        self.c.update_profile(ann, {"show_progress": False})
        self.assertIsNone(self.c.profile(self.users["ben"], "ann")["progress"])
        self.assertIsNotNone(self.c.profile(ann, "ann")["progress"])  # you always see your own

    def test_levels(self):
        self.assertEqual(gift_rewards.level_for(0)["level"], 1)
        self.assertEqual(gift_rewards.level_for(100)["level"], 2)
        self.assertEqual(gift_rewards.level_for(299)["level"], 2)
        self.assertEqual(gift_rewards.level_for(300)["level"], 3)
        self.assertEqual(gift_rewards.best_streak({"2026-01-01", "2026-01-02", "2026-01-04"}), 2)

    # sessions
    def test_device_list_and_revoke(self):
        t1, _ = self.c.login("ann", "password-ann", "3.3.3.3", "Chrome on Android")
        t2, _ = self.c.login("ann", "password-ann", "3.3.3.3", "Safari on iPhone")
        me = self.c.session_user(t1)
        devices = self.c.sessions(me)
        self.assertEqual(sum(d["current"] for d in devices), 1)
        self.c.revoke_session(me, "others", "3.3.3.3")
        self.assertIsNone(self.c.session_user(t2))
        self.assertIsNotNone(self.c.session_user(t1))

    def test_sync_last_write_wins(self):
        ann = self.users["ann"]
        out = self.c.sync(ann, 0, [{"kind": "hl", "key": "John|3|16", "value": "y", "updated": 100}])
        self.assertEqual(out["changes"][0]["value"], "y")
        self.c.sync(ann, 0, [{"kind": "hl", "key": "John|3|16", "value": "g", "updated": 50}])  # older: ignored
        out = self.c.sync(ann, 0, [])
        self.assertEqual(out["changes"][0]["value"], "y")
        later = self.c.sync(ann, out["cursor"], [{"kind": "hl", "key": "John|3|16", "value": None, "updated": 200}])
        self.assertIsNone(later["changes"][0]["value"])
        with self.assertRaises(gift_community.Problem):
            self.c.sync(ann, 0, [{"kind": "passwords", "key": "x", "value": 1, "updated": 1}])

    def test_migrates_first_release_database(self):
        path = Path(self.tmp.name) / "old.sqlite3"
        db = sqlite3.connect(path)
        db.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
              pw_salt BLOB NOT NULL, pw_hash BLOB NOT NULL, created INTEGER NOT NULL);
            CREATE TABLE sessions (token_hash BLOB PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE study_groups (id INTEGER PRIMARY KEY, name TEXT NOT NULL, about TEXT NOT NULL DEFAULT '',
              area TEXT NOT NULL DEFAULT '', invite TEXT NOT NULL UNIQUE, plan TEXT, plan_start TEXT, created INTEGER NOT NULL);
            CREATE TABLE group_members (group_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
              role TEXT NOT NULL CHECK (role IN ('leader', 'member')), joined INTEGER NOT NULL,
              last_read INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (group_id, user_id));
            INSERT INTO users VALUES (1, 'old', 'Old', x'00', x'00', 1);
            INSERT INTO study_groups VALUES (1, 'Old group', '', '', 'invitecode1', NULL, NULL, 1);
            INSERT INTO group_members VALUES (1, 1, 'leader', 1, 0);
        """)
        db.commit()
        db.close()
        c = gift_community.Community(path)
        user = c.user(1)
        g = c.group(user, 1)
        self.assertEqual(g["members"][0]["role"], "leader")
        c.set_role(user, 1, 1, "leader", "Founder")  # new columns work
        self.assertEqual(c.group(user, 1)["members"][0]["title"], "Founder")


class MediaTests(unittest.TestCase):
    def test_sniffing(self):
        self.assertEqual(gift_media.sniff(PNG)[0:2], ("image", "image/png"))
        self.assertEqual(gift_media.sniff(MP3)[1], "audio/mpeg")
        self.assertEqual(gift_media.sniff(b"\xff\xd8\xff\xe0")[1], "image/jpeg")
        self.assertIsNone(gift_media.sniff(b"<svg xmlns=..."))
        self.assertIsNone(gift_media.sniff(b"<!doctype html>"))

    def test_ranges(self):
        self.assertEqual(gift_media.parse_range("bytes=0-99", 1000), (0, 99))
        self.assertEqual(gift_media.parse_range("bytes=900-", 1000), (900, 999))
        self.assertEqual(gift_media.parse_range("bytes=-100", 1000), (900, 999))
        self.assertIsNone(gift_media.parse_range("bytes=2000-", 1000))
        self.assertIsNone(gift_media.parse_range("bytes=0-1,5-6", 1000))


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = gift_community.Community(Path(self.tmp.name) / "c.sqlite3")
        self.user = self.c.signup("payer", "Payer", "password-payer", "1.1.1.1")[1]
        self.calls = []
        self.env = {"GIFT_STRIPE_SECRET_KEY": "sk_test", "GIFT_STRIPE_WEBHOOK_SECRET": "whsec_test",
                    "GIFT_STRIPE_PRICES": json.dumps({"plus_month": "price_plus_m", "premium_year": "price_prem_y"})}
        self.b = gift_billing.Billing(self.c, env=self.env, http=self.http, sign=lambda key, msg: b"sig")
        self.c.billing = self.b
        self.stripe_sub = {"id": "sub_1", "status": "active", "customer": "cus_1",
                           "current_period_end": int(time.time()) + 30 * 86400, "cancel_at_period_end": False,
                           "metadata": {"user_id": str(self.user["id"])},
                           "items": {"data": [{"price": {"id": "price_prem_y"}}]}}

    def tearDown(self):
        self.tmp.cleanup()

    def http(self, method, url, data=None, headers=None, timeout=20):
        self.calls.append((method, url, data))
        if "checkout/sessions" in url:
            return {"url": "https://checkout.stripe.test/s"}
        if "/subscriptions/" in url and "api.stripe.com" in url:
            return self.stripe_sub
        if "oauth2.googleapis.com" in url:
            return {"access_token": "ya29.test", "expires_in": 3600}
        if "subscriptionsv2" in url:
            return {"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE", "acknowledgementState": "ACKNOWLEDGEMENT_STATE_PENDING",
                    "lineItems": [{"productId": "plus_monthly", "expiryTime": "2099-01-01T00:00:00Z"}]}
        return {}

    def signed(self, payload, secret="whsec_test", t=None):
        t = t or int(time.time())
        sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
        return f"t={t},v1={sig}"

    def test_free_by_default(self):
        self.assertEqual(self.b.tier(self.user["id"]), "free")
        with self.assertRaises(gift_community.Problem) as e:
            self.b.require(self.user, "study")
        self.assertEqual(e.exception.status, 402)

    def test_stripe_checkout_and_signed_webhook(self):
        out = self.b.stripe_checkout(self.user, "premium", "year", "https://gift.example")
        self.assertTrue(out["url"].startswith("https://checkout.stripe.test"))
        sent = self.calls[0][2]
        self.assertEqual(sent["client_reference_id"], str(self.user["id"]))
        payload = json.dumps({"type": "customer.subscription.updated", "data": {"object": {"id": "sub_1"}}}).encode()
        with self.assertRaises(gift_community.Problem):
            self.b.stripe_webhook(payload, "t=1,v1=forged")
        with self.assertRaises(gift_community.Problem):
            self.b.stripe_webhook(payload, self.signed(payload, t=int(time.time()) - 3600))  # too old: replay
        self.b.stripe_webhook(payload, self.signed(payload))
        self.assertEqual(self.b.tier(self.user["id"]), "premium")
        # cancelled and expired → back to free
        self.stripe_sub.update(status="canceled", current_period_end=int(time.time()) - 10)
        self.b.stripe_webhook(payload, self.signed(payload))
        self.assertEqual(self.b.tier(self.user["id"]), "free")

    def test_play_purchase_is_verified_and_bound_to_one_account(self):
        self.env.update(GIFT_PLAY_PACKAGE="uk.test", GIFT_PLAY_SERVICE_ACCOUNT=str(Path(self.tmp.name) / "sa.json"))
        Path(self.env["GIFT_PLAY_SERVICE_ACCOUNT"]).write_text(json.dumps({"client_email": "x@y", "private_key": "k"}))
        status = self.b.play_verify(self.user, "plus_monthly", "purchase-token-123")
        self.assertEqual(status["tier"], "plus")
        self.assertTrue(any(":acknowledge" in u for _, u, _ in self.calls))
        other = self.c.signup("other", "Other", "password-other", "1.1.1.1")[1]
        with self.assertRaises(gift_community.Problem) as e:
            self.b.play_verify(other, "plus_monthly", "purchase-token-123")
        self.assertEqual(e.exception.status, 409)
        with self.assertRaises(gift_community.Problem):
            self.b.play_verify(self.user, "free_lunch", "purchase-token-123")

    def test_plan_limits_on_groups(self):
        for i in range(2):
            self.c.create_group(self.user, {"name": f"G{i}"})
        with self.assertRaises(gift_community.Problem) as e:
            self.c.create_group(self.user, {"name": "G3"})
        self.assertEqual(e.exception.status, 402)
        self.b.grant("payer", "premium", 30)
        self.c.create_group(self.user, {"name": "G3"})  # premium leads more

    def test_rs256_with_real_openssl(self):
        key = subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
                             capture_output=True, check=True).stdout.decode()
        sig = gift_billing.rs256(key, b"header.claims")
        self.assertEqual(len(sig), 256)
        pub = subprocess.run(["openssl", "pkey", "-pubout"], input=key.encode(), capture_output=True, check=True).stdout
        with tempfile.NamedTemporaryFile() as p, tempfile.NamedTemporaryFile() as s:
            p.write(pub), p.flush(), s.write(sig), s.flush()
            ok = subprocess.run(["openssl", "dgst", "-sha256", "-verify", p.name, "-signature", s.name],
                                input=b"header.claims", capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_church_inquiry(self):
        with self.assertRaises(gift_community.Problem):
            self.b.church_inquiry({"name": "Pastor"}, "4.4.4.4")
        self.b.church_inquiry({"name": "Pastor Jo", "church": "St Mark's", "email": "jo@example.org", "size": "200"}, "4.4.4.4")
        admin = dict(self.user, is_admin=True, verified=True)
        self.assertEqual(self.b.inquiries(admin)[0]["church"], "St Mark's")


class FeatureAPITests(unittest.TestCase):
    """Over real HTTP: uploads, media, music review, gates, channel, links."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / "lib"
        root.mkdir()
        make_library(root)
        (root / "app").mkdir()
        (root / "app/index.html").write_text("<!doctype html><title>The Gift</title>", encoding="utf-8")
        (root / "Music/Hymns/audio").mkdir(parents=True)
        (root / "Music/Hymns/audio/test.mp3").write_bytes(MP3)
        (root / "Music/Hymns/hymns.json").write_text(json.dumps({"hymns": [{"id": "test-hymn", "title": "Test Hymn",
            "author": "A. Writer", "year": 1800, "verses": [["Line one", "Line two"]],
            "audio": {"file": "audio/test.mp3", "performer": "Choir", "licence": "Public domain"}}]}))
        # the licence table marks GRK non-commercial: the Play app hides it
        cls._orig = (gift.ROOT, gift.DATA_DIR)
        gift.ROOT, gift.DATA_DIR = root, Path(cls.tmp.name) / "data"
        gift.get_app().places = gift_places.Places(fetch=FakeFetch())
        cls.httpd = gift.BoundedThreadingHTTPServer(("127.0.0.1", 0), gift.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.origin = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.c = gift.get_app().community

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
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
            r = conn.getresponse()
            data = r.read()
            try:
                return r, json.loads(data)
            except ValueError:
                return r, data
        finally:
            conn.close()

    def signup(self, name):
        r, d = self.call("POST", "/api/signup", {"username": name, "password": "a good password"})
        self.assertEqual(r.status, 200, d)
        return r.getheader("Set-Cookie").split(";")[0].split("=", 1)[1], d["user"]

    def test_upload_and_serve_media(self):
        token, _ = self.signup("uploader1")
        r, d = self.call("POST", "/api/media", raw=PNG, cookie=token, headers={"Content-Type": "image/png"})
        self.assertEqual(r.status, 200, d)
        r, body = self.call("GET", d["url"])
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader("Content-Type"), "image/png")
        self.assertIn("sandbox", r.getheader("Content-Security-Policy"))
        r, part = self.call("GET", d["url"], headers={"Range": "bytes=0-7"})
        self.assertEqual(r.status, 206)
        self.assertEqual(part, PNG[:8])
        # disguised HTML is refused, whatever it claims to be
        r, d = self.call("POST", "/api/media", raw=b"<html><script>alert(1)</script>", cookie=token,
                         headers={"Content-Type": "image/png"})
        self.assertEqual(r.status, 415)
        # nobody signed in: refused before the body is read
        r, d = self.call("POST", "/api/media", raw=PNG, headers={"Content-Type": "image/png"})
        self.assertEqual(r.status, 401)

    def test_hymn_audio_supports_ranges(self):
        r, d = self.call("GET", "/api/hymns/test-hymn")
        self.assertEqual(d["audio"]["url"], "/Music/Hymns/audio/test.mp3")
        r, part = self.call("GET", d["audio"]["url"], headers={"Range": "bytes=0-2"})
        self.assertEqual((r.status, part), (206, b"ID3"))

    def test_music_review_flow(self):
        artist_tok, artist = self.signup("artist1")
        admin_tok, admin = self.signup("admin1")
        self.c.set_admin("admin1")
        r, d = self.call("POST", "/api/studio", {"name": "The Psalmists", "links": {"spotify": "https://evil.example/x"}},
                         cookie=artist_tok)
        self.assertEqual(r.status, 400)  # only Spotify's own address counts as a Spotify link
        r, d = self.call("POST", "/api/studio", {"name": "The Psalmists", "links": {"youtube": "youtube.com/@psalmists"}},
                         cookie=artist_tok)
        aid = d["artist"]["id"]
        r, _ = self.call("GET", f"/api/artists/{aid}")
        self.assertEqual(r.status, 404)  # not public until approved
        r, d = self.call("POST", "/api/media", raw=MP3, cookie=artist_tok, headers={"Content-Type": "audio/mpeg"})
        media = d["id"]
        r, d = self.call("POST", "/api/studio/songs", {"title": "Song", "media": media, "rights": True}, cookie=artist_tok)
        self.assertEqual(r.status, 403)  # songs wait for an approved artist
        # admin needs a fresh password (step-up) — sign-in counts as fresh
        r, q = self.call("GET", "/api/admin", cookie=admin_tok)
        self.assertEqual(r.status, 200, q)
        r, _ = self.call("POST", f"/api/admin/artists/{aid}", {"action": "approve"}, cookie=admin_tok)
        self.assertEqual(r.status, 200)
        r, d = self.call("POST", "/api/studio/songs", {"title": "Song", "media": media, "rights": True}, cookie=artist_tok)
        self.assertEqual(r.status, 200, d)
        r, m = self.call("GET", "/api/music")
        self.assertEqual(m["songs"], [])  # held for review
        sid = d["artist"]["songs"][0]["id"]
        self.call("POST", f"/api/admin/songs/{sid}", {"action": "approve"}, cookie=admin_tok)
        r, m = self.call("GET", "/api/music")
        self.assertEqual([s["title"] for s in m["songs"]], ["Song"])
        # a non-admin can't review
        r, _ = self.call("GET", "/api/admin", cookie=artist_tok)
        self.assertEqual(r.status, 403)

    def test_premium_gates_are_server_side(self):
        token, user = self.signup("gated1")
        for path in ("/api/commentary?m=jfb&b=John&c=3&v=16", "/api/dictionary?q=grace"):
            r, d = self.call("GET", path, cookie=token)
            self.assertEqual(r.status, 402, path)
        r, d = self.call("GET", "/api/download?t=TST", cookie=token)
        self.assertEqual(r.status, 402)
        r, d = self.call("POST", "/api/sync", {"changes": []}, cookie=token)
        self.assertEqual(r.status, 402)
        gift.get_app().billing.grant("gated1", "premium", 1)
        r, d = self.call("GET", "/api/commentary?m=jfb&b=John&c=3&v=16", cookie=token)
        self.assertEqual(r.status, 404)  # past the gate (the fixture has no commentaries)
        r, d = self.call("GET", "/api/download?t=TST", cookie=token)
        self.assertEqual((r.status, len(d["chapters"])), (200, 5))
        r, d = self.call("GET", "/api/download?t=GRK", cookie=token)
        self.assertEqual(r.status, 403)  # non-commercial licence: never part of a paid feature

    def test_play_channel_hides_restricted_texts(self):
        r, d = self.call("GET", "/api/translations")
        self.assertIn("GRK", {t["id"] for t in d["translations"]})
        r, d = self.call("GET", "/api/translations", headers={"X-Gift-Channel": "play"})
        self.assertNotIn("GRK", {t["id"] for t in d["translations"]})
        r, _ = self.call("GET", "/api/chapter?t=GRK&b=John&c=1", headers={"X-Gift-Channel": "play"})
        self.assertEqual(r.status, 404)

    def test_stripe_webhook_needs_signature_not_origin(self):
        r, _ = self.call("POST", "/api/billing/stripe/webhook", raw=b"{}", headers={"Origin": "", "Stripe-Signature": "t=1,v1=x"})
        self.assertEqual(r.status, 400)

    def test_assetlinks(self):
        r, _ = self.call("GET", "/.well-known/assetlinks.json")
        self.assertEqual(r.status, 404)
        os.environ.update(GIFT_ANDROID_PACKAGE="uk.test.app", GIFT_ANDROID_CERT_SHA256="AA:BB")
        try:
            r, d = self.call("GET", "/.well-known/assetlinks.json")
            self.assertEqual(d[0]["target"]["package_name"], "uk.test.app")
        finally:
            del os.environ["GIFT_ANDROID_PACKAGE"], os.environ["GIFT_ANDROID_CERT_SHA256"]

    def test_security_headers_everywhere(self):
        r, _ = self.call("GET", "/api/translations")
        for h in ("X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options", "Cross-Origin-Resource-Policy"):
            self.assertTrue(r.getheader(h), h)
        self.assertIsNone(r.getheader("Strict-Transport-Security"))  # only over https
        r, _ = self.call("GET", "/api/translations", headers={"X-Forwarded-Proto": "https"})
        self.assertTrue(r.getheader("Strict-Transport-Security"))

    def test_audit_log_needs_admin(self):
        token, _ = self.signup("plain1")
        r, _ = self.call("GET", "/api/admin/audit", cookie=token)
        self.assertEqual(r.status, 403)


if __name__ == "__main__":
    unittest.main()
