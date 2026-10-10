"""Tests for server.py's request handling: traversal guard, hidden-path
blocking, redirects, conditional requests, and the concurrency cap.

Run with: python3 -m unittest test_server
"""

import os

# Keep the concurrency-cap test cheap — it opens this many real sockets.
os.environ.setdefault("GIFT_MAX_CONCURRENT", "3")

import http.client
import hashlib
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import server as gift


class GiftServerTestCase(unittest.TestCase):
    """Exercises the handler against a tiny fixture tree, not the real
    1.8GB library — keeps the suite fast and independent of repo content."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "README.md").write_text("# The Gift (test fixture)\n")
        (root / "LICENSE").write_text("MIT (test fixture)\n")
        (root / "Bibles").mkdir()
        (root / "Bibles" / "sample.txt").write_text("in the beginning\n")
        (root / "deploy").mkdir()
        (root / "deploy" / "deploy.sh").write_text("#!/bin/sh\necho hi\n")
        (root / ".git").mkdir()
        (root / ".git" / "config").write_text("[core]\n")
        (root / ".claude").mkdir()
        (root / ".claude" / "settings.json").write_text("{}\n")
        (root / "model").mkdir()
        (root / "model" / "weights.txt").write_text("private\n")
        # a symlink inside the library that points at a hidden tree
        (root / "Bibles" / "sneaky").symlink_to(root / "model", target_is_directory=True)
        (root / "Bibles" / "odd #1?%.txt").write_text("odd name\n")
        (root / "app" / "icons").mkdir(parents=True)
        (root / "app" / "icons" / "favicon-32.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")

        cls._orig_root = gift.ROOT
        gift.ROOT = root

        cls.httpd = gift.BoundedThreadingHTTPServer(("127.0.0.1", 0), gift.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        gift.ROOT = cls._orig_root
        cls.tmp.cleanup()

    def request(self, method, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, headers=headers or {})
            resp = conn.getresponse()
            body = resp.read()
            return resp, body
        finally:
            conn.close()

    def test_healthz(self):
        resp, body = self.request("GET", "/healthz")
        self.assertEqual(resp.status, 200)
        self.assertIn(b'"ok": true', body)

    def test_landing_page(self):
        resp, body = self.request("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"<h1>The Gift</h1>", body)

    def test_public_file_served(self):
        resp, body = self.request("GET", "/README.md")
        self.assertEqual(resp.status, 200)
        self.assertTrue(body)

    def test_traversal_dotdot_blocked(self):
        # http.client sends the path as given, unlike curl it does not
        # collapse ../ client-side, so this actually exercises the guard.
        resp, _ = self.request("GET", "/../../../../etc/passwd")
        self.assertEqual(resp.status, 404)

    def test_traversal_encoded_dots_blocked(self):
        resp, _ = self.request("GET", "/%2e%2e/%2e%2e/%2e%2e/etc/passwd")
        self.assertEqual(resp.status, 404)

    def test_hidden_dotgit_file_blocked(self):
        resp, _ = self.request("GET", "/.git/config")
        self.assertEqual(resp.status, 404)

    def test_hidden_deploy_file_blocked(self):
        resp, _ = self.request("GET", "/deploy/deploy.sh")
        self.assertEqual(resp.status, 404)

    def test_hidden_dir_listing_blocked(self):
        resp, _ = self.request("GET", "/deploy/")
        self.assertEqual(resp.status, 404)

    def test_directory_redirects_to_trailing_slash(self):
        resp, _ = self.request("GET", "/Bibles")
        self.assertEqual(resp.status, 301)
        self.assertTrue(resp.getheader("Location", "").endswith("/Bibles/"))

    def test_directory_listing_served(self):
        resp, body = self.request("GET", "/Bibles/")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"<table>", body)

    def test_extensionless_license_served_as_text(self):
        resp, body = self.request("GET", "/LICENSE")
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.getheader("Content-Type", "").startswith("text/plain"))
        self.assertIn(b"MIT", body)

    def test_etag_conditional_304(self):
        resp, _ = self.request("GET", "/README.md")
        etag = resp.getheader("ETag")
        self.assertTrue(etag)
        resp2, body2 = self.request("GET", "/README.md", headers={"If-None-Match": etag})
        self.assertEqual(resp2.status, 304)
        self.assertEqual(body2, b"")

    def test_large_file_streams_byte_for_byte(self):
        """A multi-chunk file survives the chunked path with the exact bytes
        and an exact Content-Length."""
        payload = os.urandom(gift.CHUNK_SIZE * 2 + 12345)  # spans 3 chunk reads
        (gift.ROOT / "Bibles" / "big.bin").write_bytes(payload)
        try:
            resp = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            try:
                resp.request("GET", "/Bibles/big.bin")
                r = resp.getresponse()
                self.assertEqual(r.status, 200)
                self.assertEqual(r.getheader("Content-Length"), str(len(payload)))
                self.assertEqual(hashlib.sha256(r.read()).hexdigest(),
                                 hashlib.sha256(payload).hexdigest())
            finally:
                resp.close()
        finally:
            (gift.ROOT / "Bibles" / "big.bin").unlink()

    def test_head_request_has_no_body(self):
        payload = b"x" * (gift.CHUNK_SIZE + 7)
        (gift.ROOT / "Bibles" / "head.bin").write_bytes(payload)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                conn.request("HEAD", "/Bibles/head.bin")
                r = conn.getresponse()
                self.assertEqual(r.status, 200)
                self.assertEqual(r.getheader("Content-Length"), str(len(payload)))
                self.assertEqual(r.read(), b"")
            finally:
                conn.close()
        finally:
            (gift.ROOT / "Bibles" / "head.bin").unlink()

    def test_client_disconnect_mid_stream_is_survivable(self):
        """A client that hangs up mid-download must not wedge the server:
        the handler thread ends, the slot is released, and later requests
        are served normally."""
        payload = os.urandom(gift.CHUNK_SIZE * 8)
        (gift.ROOT / "Bibles" / "dip.bin").write_bytes(payload)
        try:
            raw = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            raw.sendall(b"GET /Bibles/dip.bin HTTP/1.1\r\n"
                        b"Host: localhost\r\n\r\n")
            time.sleep(0.2)  # headers + first chunks go out
            raw.close()      # hang up mid-stream
            time.sleep(0.3)  # give the handler thread time to notice

            resp, body = self.request("GET", "/healthz")
            self.assertEqual(resp.status, 200)
            self.assertIn(b'"ok": true', body)
        finally:
            (gift.ROOT / "Bibles" / "dip.bin").unlink()

    def test_favicon_served(self):
        resp, body = self.request("GET", "/favicon.ico")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_landing_page_has_favicon_link(self):
        resp, body = self.request("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertIn(b'rel="icon"', body)

    def test_concurrency_cap_returns_503(self):
        """Fill every serving slot with real in-flight requests; a further
        request gets 503, while a connection opened while the server is full
        (no request sent yet) is still served once capacity frees up."""
        blocked = threading.Event()

        def gate(self):
            if self.path != "/healthz":  # healthz bypasses the cap entirely
                blocked.wait(timeout=10)  # request stays in flight until released
            return orig_serve(self)

        # park each request inside the handler's serve step so it holds a slot
        orig_serve = gift.Handler._serve
        gift.Handler._serve = gate
        try:
            conns = []
            idle = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                for _ in range(gift.MAX_CONCURRENT):
                    c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
                    c.request("GET", "/")
                    conns.append(c)
                time.sleep(0.3)  # let them parse and claim every slot
                resp, _ = self.request("GET", "/README.md")
                self.assertEqual(resp.status, 503)

                # liveness is not load: healthz still answers while full
                resp, body = self.request("GET", "/healthz")
                self.assertEqual(resp.status, 200)
                self.assertIn(b'"ok": true', body)

                blocked.set()  # release the parked requests
                for c in conns:
                    r = c.getresponse()
                    self.assertEqual(r.status, 200)
                    r.read()

                # the connection opened while full was never bounced — its
                # request is served normally now that slots are free
                idle.request("GET", "/README.md")
                r2 = idle.getresponse()
                self.assertEqual(r2.status, 200)
                r2.read()
            finally:
                blocked.set()  # never leave requests parked if an assert fails
                idle.close()
                for c in conns:
                    c.close()
        finally:
            gift.Handler._serve = orig_serve

    def test_hidden_model_file_blocked(self):
        resp, _ = self.request("GET", "/model/weights.txt")
        self.assertEqual(resp.status, 404)

    def test_hidden_model_listing_blocked(self):
        resp, _ = self.request("GET", "/model/")
        self.assertEqual(resp.status, 404)

    def test_hidden_dotclaude_blocked(self):
        resp, _ = self.request("GET", "/.claude/settings.json")
        self.assertEqual(resp.status, 404)

    def test_symlink_into_hidden_tree_blocked(self):
        """A symlink inside the library must not expose what it points at."""
        resp, _ = self.request("GET", "/Bibles/sneaky/")
        self.assertEqual(resp.status, 404)
        resp, _ = self.request("GET", "/Bibles/sneaky/weights.txt")
        self.assertEqual(resp.status, 404)

    def test_listing_omits_symlink_into_hidden_tree(self):
        resp, body = self.request("GET", "/Bibles/")
        self.assertEqual(resp.status, 200)
        self.assertNotIn(b"sneaky", body)
        self.assertIn(b"sample.txt", body)

    def test_index_html_is_landing_page(self):
        resp, body = self.request("GET", "/index.html")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"<h1>The Gift</h1>", body)

    def test_listing_links_are_url_encoded(self):
        """#, ? and % in a file name must not break its link."""
        resp, body = self.request("GET", "/Bibles/")
        self.assertIn(b'href="odd%20%231%3F%25.txt"', body)
        self.assertIn(b"odd #1?%.txt", body)  # displayed name unchanged
        resp, body = self.request("GET", "/Bibles/odd%20%231%3F%25.txt")
        self.assertEqual(resp.status, 200)
        self.assertEqual(body, b"odd name\n")

    def test_redirect_keeps_query(self):
        resp, _ = self.request("GET", "/Bibles?x=1")
        self.assertEqual(resp.status, 301)
        self.assertTrue(resp.getheader("Location", "").endswith("/Bibles/?x=1"))

    def test_security_headers(self):
        resp, _ = self.request("GET", "/")
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'none'", resp.getheader("Content-Security-Policy", ""))
        resp, _ = self.request("GET", "/README.md")
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")

    def test_keepalive_requests_all_served(self):
        """Several requests over one connection all get served (no per-
        connection slot held between requests)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            for i in range(3):
                conn.request("GET", "/healthz")
                resp = conn.getresponse()
                body = resp.read()
                self.assertEqual(resp.status, 200)
                self.assertIn(b'"ok": true', body)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
