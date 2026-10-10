"""
The Gift — host server.

One process serves the whole library with a real front door: a landing page
(counts computed from disk), browsable directory listings, and the files
themselves with honest MIME types. Python 3 stdlib only — no packages, no
build step. Binds 127.0.0.1 by default: on atlas the only way in is the
Cloudflare tunnel (zero trust: no network is trusted, the LAN included).
GIFT_HOST=0.0.0.0 deliberately opens it to the local network.

  python3 server.py                 # serve on 127.0.0.1:8770
  GIFT_PORT=8080 python3 server.py  # different port

Dot-directories (.git, .claude, …) and the private model/ folder are never
served. Files stream to the client in chunks, so memory use is flat
regardless of file size — but there is still no HTTP range/resume support
by design; bulk/programmatic access should use git or rsync.

At most GIFT_MAX_CONCURRENT requests are in flight at once; beyond that,
new requests get an immediate 503 instead of piling up work. The slot is
taken per request, not per connection, so a browser's idle keep-alive
connections never consume serving capacity. /healthz is exempt: it answers
"is the process up", and a busy server is up. Refusals are summarised on
stderr (journald) at most once a minute.

Access logging is off by default; GIFT_ACCESS_LOG=1 writes one line per
request to stderr. Errors are always logged.

  GET /                → landing page (library counts, links to browse)
  GET /app/            → the app: reader, devotional, plans, journal, groups
  GET|POST /api/…      → the app's JSON API (gift_api.py)
  GET /media/<id>      → an uploaded picture or song (by random id)
  GET /<path>/         → browsable listing
  GET /<path>/<file>   → the file (text/* UTF-8 for readable formats)

The app's accounts and study groups live in a SQLite file under
GIFT_DATA_DIR (default: .data/ beside this file, which is never served).
"""

import html
import json
import mimetypes
import os
import sys
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import gift_api
import gift_library
import gift_media

PORT = int(os.environ.get("GIFT_PORT", "8770"))
# zero trust: by default only this machine can connect; the public door is
# the Cloudflare tunnel (TLS at the edge). GIFT_HOST=0.0.0.0 opens the LAN.
HOST = os.environ.get("GIFT_HOST", "127.0.0.1")
# Files stream to the client in chunks of this size (never whole into
# memory), so RSS stays flat no matter how big the files are.
CHUNK_SIZE = 256 * 1024

MAX_CONCURRENT = int(os.environ.get("GIFT_MAX_CONCURRENT", "32"))
ACCESS_LOG = os.environ.get("GIFT_ACCESS_LOG") == "1"

REPO_URL = "https://github.com/lisasdungeon/the-gift"

# HTML pages only need their own inline styles and the logo/favicon images
HTML_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

# the app: its own scripts, styles, worker and manifest, and its own API —
# no inline script, nothing from another origin
APP_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; "
           "img-src 'self' data: blob:; media-src 'self'; connect-src 'self'; "
           "manifest-src 'self'; worker-src 'self'; base-uri 'none'; "
           "form-action 'none'; frame-ancestors 'none'")

ROOT = Path(__file__).resolve().parent
APP_DIR = "app"           # the app's static files, served under /app/
DATA_DIR = Path(os.environ.get("GIFT_DATA_DIR") or ROOT / ".data")
SESSION_COOKIE = "gift_session"
MAX_BODY = 32 * 1024      # JSON bodies are small: messages, forms

# never exposed over HTTP, whatever the request
HIDDEN = {".git", ".claude", ".freebuff", "model", "deploy", "__pycache__"}

READABLE_MIME = {
    ".txt": "text/plain; charset=utf-8",
    ".py": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".conf": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
}

# extensionless docs that must display in the browser, not download
DOC_NAMES = {"LICENSE", "README"}

# one-line "book" glyph that inherits the page's text color
# the logo's book and cross (design/make_brand.py makes it from the logo)
FAVICON = "/app/icons/favicon-64.png"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Gift — Read it. Study it. Grow together.</title>
<meta name="description" content="Free Bibles in 56 languages, a daily devotional, reading plans, study groups and music.">
<meta property="og:title" content="The Gift — Read it. Study it. Grow together.">
<meta property="og:image" content="https://gift.rnkstudios.uk/app/img/og-image.jpg">
<link rel="icon" href="{favicon}">
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; color: #eef2fb; font: 17px/1.6 system-ui, sans-serif;
         background: radial-gradient(1000px 560px at 50% -10%, #0b2a6e, transparent 65%), #030a1d; }}
  main {{ max-width: 880px; margin: 0 auto; padding: clamp(24px, 5vw, 56px) 20px; }}
  .hero {{ display: flex; align-items: center; gap: clamp(16px, 4vw, 36px); flex-wrap: wrap; margin-bottom: 36px; }}
  .hero img {{ width: clamp(150px, 30vw, 230px); height: auto; border-radius: 28px; }}
  .tag {{ font: 700 clamp(30px, 5.4vw, 46px)/1.12 Georgia, "Noto Serif", serif; color: #f3cf7a; margin: 0 0 12px; }}
  .lede {{ color: #c7d1e8; max-width: 52ch; margin: 0; }}
  .sr {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }}
  .doors {{ display: grid; gap: 14px; }}
  a.door {{ display: block; padding: 20px 22px; background: #0a1636; border-radius: 16px;
            border: 1px solid rgba(201,214,255,.12); color: inherit; text-decoration: none; }}
  a.door:hover {{ border-color: rgba(232,181,82,.55); }}
  a.door.app {{ border-color: rgba(232,181,82,.45);
                background: linear-gradient(135deg, #1a2a5e, #0a1636 65%); }}
  a.door.app h2 {{ color: #f3cf7a; }}
  a.door h2 {{ margin: 0 0 6px; font-size: 22px; color: #eef2fb; }}
  a.door p {{ margin: 0; color: #a7b3d1; font-size: 15px; }}
  .foot {{ margin-top: 44px; color: #8d9bbd; font-size: 14px; }}
  .foot a {{ color: #e8b552; }}
</style>
</head>
<body>
<main>
  <div class="hero">
    <img src="/app/img/logo.jpg" alt="The Gift" width="230" height="230">
    <div>
      <div class="sr"><h1>The Gift</h1></div>
      <p class="tag">Read it. Study it. Grow together.</p>
      <p class="lede">
        A free library of Bible translations and study resources, most of
        them public domain, gathered from established open-data projects.
        The library is never paywalled, DRM'd or account-gated; the app
        adds plans, groups and music on top.
      </p>
    </div>
  </div>

  <div class="doors">
    <a class="door app" href="/app/">
      <h2>Open the app →</h2>
      <p>Read and compare {text_count} translations, search them, follow a
         Bible-in-a-year plan, keep a private journal, read Spurgeon's
         Morning &amp; Evening, start a study group and find a church
         nearby. Installs on your phone.</p>
    </a>
    <a class="door" href="/Bibles/formats/text/">
      <h2>Bibles — plain text · {text_count} translations</h2>
      <p>One UTF-8 .txt per translation, across ~50 languages. Start with
         AKJV, ASV, Webster — the full list is the listing itself.</p>
    </a>
    <a class="door" href="/Bibles/formats/python/">
      <h2>Bibles — by book &amp; language · {python_dirs} folders</h2>
      <p>The same texts organised per book and per language — {python_files}
         files, useful for scripting and programmatic reading.</p>
    </a>
    <a class="door" href="/Bibles/formats/correlate/">
      <h2>Bibles — correlate scripts</h2>
      <p>Small Node.js word-concordance scripts, one per book and
         translation. They read the Python files above, so download both.</p>
    </a>
    <a class="door" href="/Study%20Guides/">
      <h2>Study Guides · {sword_count} SWORD modules</h2>
      <p>Classic public-domain commentaries and reference works (Matthew
         Henry, JFB, Strong's, Nave's …) and Spurgeon's Morning &amp;
         Evening, in the CrossWire SWORD format.</p>
    </a>
  </div>

  <p class="foot">
    Free to read — mostly public domain, but not all: each translation's
    licence is listed in <a href="/Bibles/README.md">Bibles/README.md</a>.
    See also the <a href="/README.md">README</a> and
    <a href="/LICENSE">LICENSE</a>. For bulk access, clone the
    <a href="{repo_url}">git repository</a> instead of crawling this site.
  </p>
</main>
</body>
</html>
"""


def _human_size(n):
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"


def count_visible(d, predicate=lambda p: True):
    try:
        return sum(1 for e in os.scandir(d) if e.name not in HIDDEN and not e.name.startswith(".") and predicate(e))
    except OSError:
        return 0


def is_exposed(path):
    """True if `path` really lives inside ROOT and nowhere hidden — resolving
    symlinks, so a link can't smuggle a hidden or outside tree into view."""
    try:
        real = Path(path).resolve()
    except (OSError, ValueError):
        return False
    if real == ROOT:
        return True
    if not str(real).startswith(str(ROOT) + os.sep):
        return False
    return not any(part in HIDDEN or part.startswith(".")
                   for part in real.relative_to(ROOT).parts)


def landing_page():
    text_count = count_visible(ROOT / "Bibles/formats/text", lambda e: e.name.endswith(".txt"))
    py_dir = ROOT / "Bibles/formats/python"
    python_dirs = count_visible(py_dir)
    python_files = _cached_py_files(py_dir)
    sword_count = count_visible(ROOT / "Study Guides/Commentaries and Reference/mods.d", lambda e: e.name.endswith(".conf"))
    return PAGE.format(text_count=text_count, python_dirs=python_dirs,
                       python_files=f"{python_files:,}", sword_count=sword_count,
                       favicon=FAVICON, repo_url=REPO_URL).encode("utf-8")


_py_files_cache = {}

_app_state = {"key": None, "app": None}
_app_lock = threading.Lock()


def get_app():
    """The API's state for the current ROOT/DATA_DIR (tests swap both)."""
    key = (ROOT, DATA_DIR)
    if _app_state["key"] != key:
        with _app_lock:
            if _app_state["key"] != key:
                _app_state["app"] = gift_api.App(gift_library.Library(ROOT), DATA_DIR)
                _app_state["key"] = key
    return _app_state["app"]


def _cached_py_files(d):
    """Recursive .py count — the library is static while serving, so compute once per tree."""
    key = str(d)
    if key not in _py_files_cache:
        n = 0
        for base, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in HIDDEN and not x.startswith(".")]
            n += sum(1 for f in files if f.endswith(".py"))
        _py_files_cache[key] = n
    return _py_files_cache[key]


class Handler(BaseHTTPRequestHandler):
    server_version = "TheGift/1.1"  # sys_version (Python version) is not advertised

    timeout = 60  # drop stuck connections instead of pinning a thread forever

    def version_string(self):
        return self.server_version

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if self._is_https():  # only ever tell browsers "https only" over https
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        super().end_headers()

    def _send(self, code, body, content_type, cache_control=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", HTML_CSP)
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _not_found(self):
        self._send(404, b'{"error": "not found"}', "application/json; charset=utf-8")

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def _handle(self):
        # liveness must not depend on load: a saturated server is still up
        if self.path.partition("?")[0] == "/healthz":
            return self._serve()
        # one serving slot per request, not per connection — taken only once
        # the request is parsed, released when the response is written
        if not self.server._slots.acquire(blocking=False):
            self.server.note_busy()
            return self._send(503, b'{"error": "server busy"}',
                              "application/json; charset=utf-8",
                              cache_control="no-store")
        try:
            self._serve()
        finally:
            self.server._slots.release()

    def _serve(self):
        # keep the encoded form for redirects, decode for the filesystem
        raw_path, _, query = self.path.partition("?")
        raw_path = raw_path.split("#", 1)[0]
        path = unquote(raw_path)
        if path.startswith("/api/"):
            return self._api(path, query)
        if path == "/.well-known/assetlinks.json" and self.command in ("GET", "HEAD"):
            return self._assetlinks()
        if path.startswith("/media/") and self.command in ("GET", "HEAD"):
            found = get_app().community.media_file(path[7:])
            if found is None:
                return self._not_found()
            return self._send_ranged(found[0], found[1], "public, max-age=31536000, immutable",
                                     sandbox=True)
        if self.command not in ("GET", "HEAD"):
            self.close_connection = True  # an unread body would poison keep-alive
            return self._not_found()
        if path == "/app":
            return self._redirect("/app/" + ("?" + query if query else ""))
        if path in ("/app/", "/app/index.html"):
            return self._send_app_page()
        if path == "/" or path == "/index.html":
            return self._send(200, landing_page(), "text/html; charset=utf-8",
                              cache_control="no-cache")
        if path == "/favicon.ico":
            try:
                icon = (ROOT / APP_DIR / "icons" / "favicon-32.png").read_bytes()
            except OSError:
                return self._not_found()
            return self._send(200, icon, "image/png", cache_control="public, max-age=604800")
        if path == "/healthz":
            return self._send(200, b'{"ok": true}\n', "application/json; charset=utf-8",
                              cache_control="no-store")

        try:
            candidate = (ROOT / os.path.normpath(path.lstrip("/"))).resolve()
        except (ValueError, OSError):
            return self._not_found()
        if not str(candidate).startswith(str(ROOT) + os.sep) and candidate != ROOT:
            return self._not_found()  # traversal guard
        if candidate.is_file():
            return self._send_file(candidate)
        if candidate.is_dir():
            parts = [p for p in path.split("/") if p]
            rel = Path(*parts) if parts else Path()
            # check both what was asked for and where a symlink really points
            if any(part in HIDDEN or part.startswith(".")
                   for part in (*parts, *candidate.relative_to(ROOT).parts)):
                return self._not_found()
            if not raw_path.endswith("/"):
                # canonicalise directories to a trailing slash so relative links work
                return self._redirect(raw_path + "/" + ("?" + query if query else ""))
            return self._send_listing(candidate, rel)
        return self._not_found()

    def _assetlinks(self):
        """Digital Asset Links: tells Android that the Play Store app (a
        Trusted Web Activity) and this site belong together, so the app
        opens full-screen with no browser bar. Set GIFT_ANDROID_PACKAGE and
        GIFT_ANDROID_CERT_SHA256 (comma-separated fingerprints) to enable."""
        package = os.environ.get("GIFT_ANDROID_PACKAGE", "")
        prints = [p.strip() for p in os.environ.get("GIFT_ANDROID_CERT_SHA256", "").split(",") if p.strip()]
        if not package or not prints:
            return self._not_found()
        body = json.dumps([{"relation": ["delegate_permission/common.handle_all_urls"],
                            "target": {"namespace": "android_app", "package_name": package,
                                       "sha256_cert_fingerprints": prints}}], indent=2).encode()
        self._send(200, body, "application/json", cache_control="public, max-age=3600")

    def _redirect(self, location):
        self.send_response(301)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_app_page(self):
        try:
            body = (ROOT / APP_DIR / "index.html").read_bytes()
        except OSError:
            return self._not_found()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", APP_CSP)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # -- the app's API

    def _from_proxy(self):
        """The Cloudflare tunnel connects from this box; only then are its
        forwarding headers believed."""
        return self.client_address[0] in ("127.0.0.1", "::1")

    def _client_ip(self):
        if self._from_proxy():
            fwd = self.headers.get("CF-Connecting-IP") or \
                (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if fwd:
                return fwd[:64]
        return self.client_address[0]

    def _is_https(self):
        if not self._from_proxy():
            return False
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https"
                or '"https"' in self.headers.get("CF-Visitor", ""))

    def _api(self, path, query):
        body = None
        upload = None
        if self.command == "POST" and path == "/api/media":
            return self._upload(path)
        if self.command == "POST" and path == "/api/billing/stripe/webhook":
            return self._stripe_webhook()
        if self.command == "POST":
            # any refusal below leaves the body unread: don't reuse the connection
            keep_open = not self.close_connection
            self.close_connection = True
            # same-origin JSON only: a page elsewhere can neither send JSON
            # cross-origin without asking first nor forge our Origin
            origin = self.headers.get("Origin", "")
            if not origin or urlsplit(origin).netloc != self.headers.get("Host", ""):
                return self._json(403, {"error": "cross-origin request refused"})
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(415, {"error": "send JSON"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                return self._json(413, {"error": "request too large"})
            raw = self.rfile.read(length)
            self.close_connection = not keep_open  # body fully read: back to normal
            try:
                body = json.loads(raw or b"{}")
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"error": "that isn't valid JSON"})
        elif self.command not in ("GET", "HEAD"):
            return self._json(405, {"error": "method not allowed"})
        q = {k: v[0] for k, v in parse_qs(query, max_num_fields=20).items()}
        req = gift_api.Request("POST" if self.command == "POST" else "GET",
                               path, q, body, self._client_ip(), self._session_token(), upload,
                               self.headers.get("User-Agent", ""), self.headers.get("X-Gift-Channel", ""),
                               self._origin())
        resp = gift_api.dispatch(get_app(), req)
        self._json(resp.status, resp.body, resp.cache, resp.session)

    def _origin(self):
        """Our own public address, for links we hand to Stripe."""
        scheme = "https" if self._is_https() else "http"
        return f"{scheme}://{self.headers.get('Host', 'localhost')}"

    def _stripe_webhook(self):
        """Stripe calls this server-to-server, so there's no Origin or cookie:
        the Stripe-Signature HMAC over the exact body is the only trust."""
        self.close_connection = True
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"error": "length required"})
        if not 0 < length <= 256 * 1024:
            return self._json(413, {"error": "too large"})
        raw = self.rfile.read(length)
        self.close_connection = False
        try:
            out = get_app().billing.stripe_webhook(raw, self.headers.get("Stripe-Signature", ""))
        except gift_api.Problem as p:
            return self._json(p.status, {"error": p.message})
        except Exception as e:  # Stripe retries failed deliveries
            self.log_error("stripe webhook failed: %r", e)
            return self._json(500, {"error": "try again"})
        self._json(200, out)

    def _session_token(self):
        try:
            jar = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        return jar[SESSION_COOKIE].value if SESSION_COOKIE in jar else None

    def _upload(self, path):
        """POST /api/media: the raw file as the body. Who's asking is checked
        before a byte is read, and the body streams to disk in chunks."""
        self.close_connection = True  # any refusal leaves the body unread
        origin = self.headers.get("Origin", "")
        if not origin or urlsplit(origin).netloc != self.headers.get("Host", ""):
            return self._json(403, {"error": "cross-origin request refused"})
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith(("image/", "audio/", "application/octet-stream")):
            return self._json(415, {"error": "send a picture or an audio file"})
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"error": "send the file's length"})
        if not 0 < length <= gift_media.UPLOAD_MAX:
            return self._json(413, {"error": "That file is too big (40 MB at most)."})
        token = self._session_token()
        if not (token and get_app().community.session_user(token)):
            return self._json(401, {"error": "Please sign in first."})
        try:
            tmp = gift_media.receive(self.rfile, length, DATA_DIR)
        except (ValueError, OSError):
            return self._json(400, {"error": "The upload didn't finish. Try again."})
        self.close_connection = False
        req = gift_api.Request("POST", path, {}, None, self._client_ip(), token, (tmp, length))
        try:
            resp = gift_api.dispatch(get_app(), req)
        finally:
            tmp.unlink(missing_ok=True)
        self._json(resp.status, resp.body, resp.cache, resp.session)

    def _json(self, code, obj, cache_control="no-store", session=None):
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if session is not None:
            secure = "; Secure" if self._is_https() else ""
            if session:
                self.send_header("Set-Cookie", f"{SESSION_COOKIE}={session}; Path=/; HttpOnly; "
                                 f"SameSite=Lax; Max-Age={90 * 86400}{secure}")
            else:
                self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; "
                                 f"SameSite=Lax; Max-Age=0{secure}")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    @staticmethod
    def _etag(st):
        # mtime+size, not a content hash — avoids reading the whole file just to
        # answer a conditional request
        return f'"{st.st_mtime_ns:x}-{st.st_size:x}"'

    def _send_file(self, candidate):
        if any(part in HIDDEN or part.startswith(".") for part in candidate.relative_to(ROOT).parts):
            return self._not_found()
        try:
            st = candidate.stat()
        except OSError:
            return self._not_found()
        if candidate.name in DOC_NAMES and not candidate.suffix:
            ctype = "text/plain; charset=utf-8"
        else:
            ctype = READABLE_MIME.get(candidate.suffix.lower()) \
                or mimetypes.guess_type(str(candidate))[0] \
                or "application/octet-stream"
        etag = self._etag(st)
        cache_control = "public, max-age=604800"  # library files are static; a week bounds staleness
        if candidate.relative_to(ROOT).parts[:1] == (APP_DIR,):
            cache_control = "no-cache"  # the app changes with releases: always revalidate
        if ctype.startswith("audio/"):
            return self._send_ranged(candidate, ctype, cache_control)
        if etag in {t.strip() for t in self.headers.get("If-None-Match", "").split(",")}:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control)
            self.end_headers()
            return
        try:
            f = candidate.open("rb")
        except OSError:
            return self._not_found()  # still time to send an honest 404
        with f:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(st.st_size))
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control)
            self.end_headers()
            if self.command == "HEAD":
                return
            try:
                while chunk := f.read(CHUNK_SIZE):
                    self.wfile.write(chunk)
            except (ConnectionError, TimeoutError):
                # client hung up mid-transfer: normal on the public internet.
                # Content-Length is already sent, so the response is truncated —
                # the client treats the connection dying as the error it is.
                raise

    def _send_ranged(self, path, ctype, cache_control, sandbox=False):
        """A file that honours a single Range request. The library doesn't do
        ranges (bulk access should use git), but audio does: browsers seek
        with them, and Safari won't play audio at all without them."""
        try:
            st = path.stat()
            f = path.open("rb")
        except OSError:
            return self._not_found()
        with f:
            size = st.st_size
            etag = self._etag(st)
            if etag in {t.strip() for t in self.headers.get("If-None-Match", "").split(",")}:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            wanted = self.headers.get("Range")
            span = gift_media.parse_range(wanted, size) if wanted else None
            if wanted and span is None:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            first, last = span or (0, size - 1)
            self.send_response(206 if span else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(last - first + 1))
            self.send_header("Accept-Ranges", "bytes")
            if span:
                self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control)
            if sandbox:  # uploaded by a person: never let it run as a page
                self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
                self.send_header("Content-Disposition", "inline")
            self.end_headers()
            if self.command == "HEAD":
                return
            f.seek(first)
            left = last - first + 1
            while left > 0:
                chunk = f.read(min(CHUNK_SIZE, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def _send_listing(self, d, rel):
        try:
            entries = [e for e in os.scandir(d)
                       if e.name not in HIDDEN and not e.name.startswith(".")
                       and (not e.is_symlink() or is_exposed(e.path))]
        except OSError:
            return self._not_found()
        dirs = sorted((e for e in entries if e.is_dir()), key=lambda e: e.name.lower())
        files = sorted((e for e in entries if not e.is_dir()), key=lambda e: e.name.lower())

        def href_for(e):
            # URL-encode first (so #, ? and % in names stay part of the path),
            # then HTML-escape for the attribute
            name = html.escape(quote(e.name, safe=""), quote=True)
            return f"{name}/" if e.is_dir() else name

        crumbs = '<a href="/">The Gift</a>'
        acc = ""
        for part in rel.parts:
            acc += "/" + quote(part, safe="")
            crumbs += f' / <a href="{html.escape(acc, quote=True)}/">{html.escape(part)}</a>'

        rows = ""
        for e in dirs:
            size = "—"
            rows += f'<tr><td><a href="{href_for(e)}">{html.escape(e.name)}/</a></td><td class="s">{size}</td></tr>'
        for e in files:
            try:
                size = _human_size(e.stat().st_size)
            except OSError:
                size = "—"
            rows += f'<tr><td><a href="{href_for(e)}">{html.escape(e.name)}</a></td><td class="s">{size}</td></tr>'

        body = LISTING.format(title=html.escape(str(rel) if str(rel) != "." else "browse"),
                              crumbs=crumbs, rows=rows,
                              favicon=FAVICON).encode("utf-8")
        self._send(200, body, "text/html; charset=utf-8")

    def log_message(self, fmt, *args):
        # a quiet public server by default; GIFT_ACCESS_LOG=1 for per-request lines
        if ACCESS_LOG:
            super().log_message(fmt, *args)

    def log_error(self, fmt, *args):
        super().log_message(fmt, *args)  # errors are always worth a line


LISTING = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — The Gift</title>
<link rel="icon" href="{favicon}">
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; background: #030a1d; color: #eef2fb;
          font: 16px/1.5 ui-monospace, monospace; }}
  main {{ max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }}
  .crumbs a {{ color: #e8b552; text-decoration: none; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid rgba(231,244,248,.08); }}
  td.s {{ text-align: right; color: #8aa3b3; white-space: nowrap; }}
  a {{ color: #e7f4f8; text-decoration: none; }}
  a:hover {{ color: #e8b552; }}
</style>
</head>
<body>
<main>
  <p class="crumbs">{crumbs}</p>
  <table>{rows}</table>
</main>
</body>
</html>
"""


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a cap on concurrently-served requests.

    Plain ThreadingMixIn spawns one thread per connection with no limit. The
    cap here bounds requests actually being processed (filesystem reads,
    response writes) rather than whole connections, so a browser's idle
    keep-alive connections — it holds several at once — never eat serving
    capacity. Past the cap a request gets an immediate 503 (keep-alive
    preserved); idle connections still each cost only a cheap parked thread
    that dies on its 60s socket timeout.
    """

    daemon_threads = True

    BUSY_REPORT_INTERVAL = 60  # seconds between "refused N requests" lines

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slots = threading.Semaphore(MAX_CONCURRENT)
        self._busy_lock = threading.Lock()
        self._busy_count = 0
        self._busy_reported = float("-inf")

    def note_busy(self):
        """Count a 503 refusal; summarise on stderr at most once a minute."""
        with self._busy_lock:
            self._busy_count += 1
            now = time.monotonic()
            if now - self._busy_reported < self.BUSY_REPORT_INTERVAL:
                return
            n, self._busy_count, self._busy_reported = self._busy_count, 0, now
        sys.stderr.write(f"The Gift: refused {n} request(s) with 503 "
                         f"(all {MAX_CONCURRENT} slots busy)\n")

    def handle_error(self, request, client_address):
        # a client hanging up mid-transfer is the normal case on the public
        # internet, not a server fault — one silent drop instead of a traceback
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


if __name__ == "__main__":
    print(f"The Gift: serving {ROOT} on http://{HOST}:{PORT} "
          f"(max {MAX_CONCURRENT} requests in flight)")
    # index every translation in the background (~2 s) so the app's first
    # visitor after a restart doesn't wait for it
    threading.Thread(target=lambda: get_app().library.catalogue(), daemon=True).start()
    BoundedThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
