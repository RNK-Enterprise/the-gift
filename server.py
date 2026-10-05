"""
The Gift — host server.

One process serves the whole library with a real front door: a landing page
(counts computed from disk), browsable directory listings, and the files
themselves with honest MIME types. Python 3 stdlib only — no packages, no
build step. Binds 0.0.0.0 by default (override with GIFT_HOST) so LAN
visitors can reach it — e.g. the RNK box at 192.168.1.202.

  python3 server.py                 # serve on 0.0.0.0:8770
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
  GET /<path>/         → browsable listing
  GET /<path>/<file>   → the file (text/* UTF-8 for readable formats)
"""

import html
import mimetypes
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

PORT = int(os.environ.get("GIFT_PORT", "8770"))
HOST = os.environ.get("GIFT_HOST", "0.0.0.0")
# Files stream to the client in chunks of this size (never whole into
# memory), so RSS stays flat no matter how big the files are.
CHUNK_SIZE = 256 * 1024

MAX_CONCURRENT = int(os.environ.get("GIFT_MAX_CONCURRENT", "32"))
ACCESS_LOG = os.environ.get("GIFT_ACCESS_LOG") == "1"

REPO_URL = "https://github.com/lisasdungeon/the-gift"

# HTML pages only need their own inline styles and the data: favicon
HTML_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

ROOT = Path(__file__).resolve().parent

# never exposed over HTTP, whatever the request
HIDDEN = {".git", ".claude", ".freebuff", "model", "deploy", "__pycache__"}

READABLE_MIME = {
    ".txt": "text/plain; charset=utf-8",
    ".py": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".conf": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

# extensionless docs that must display in the browser, not download
DOC_NAMES = {"LICENSE", "README"}

# one-line "book" glyph that inherits the page's text color
FAVICON = ("data:image/svg+xml," 
           "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
           "<rect width='32' height='32' rx='6' fill='%23070b14'/>"
           "<path d='M8 6h11a5 5 0 0 1 5 5v15H13a5 5 0 0 1-5-5z' "
           "fill='none' stroke='%232ee6c8' stroke-width='2'/></svg>")

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Gift — a free library</title>
<link rel="icon" href="{favicon}">
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #070b14; color: #e7f4f8;
         font: 17px/1.6 system-ui, sans-serif; }}
  main {{ max-width: 880px; margin: 0 auto; padding: clamp(28px, 6vw, 72px) 20px; }}
  .eyebrow {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
              color: #2ee6c8; margin: 0 0 10px; }}
  h1 {{ font-size: clamp(38px, 7vw, 64px); line-height: 1.05; margin: 0 0 14px; }}
  .lede {{ color: #8aa3b3; max-width: 56ch; margin: 0 0 40px; }}
  .doors {{ display: grid; gap: 14px; }}
  a.door {{ display: block; padding: 20px 22px; background: #0d1520;
            border: 1px solid rgba(231,244,248,.1); color: inherit;
            text-decoration: none; }}
  a.door:hover {{ border-color: rgba(46,230,200,.45); }}
  a.door h2 {{ margin: 0 0 6px; font-size: 22px; color: #e7f4f8; }}
  a.door p {{ margin: 0; color: #8aa3b3; font-size: 15px; }}
  .foot {{ margin-top: 44px; color: #8aa3b3; font-size: 14px; }}
  .foot a {{ color: #2ee6c8; }}
</style>
</head>
<body>
<main>
  <p class="eyebrow">RNK Studios · Open</p>
  <h1>The Gift</h1>
  <p class="lede">
    A personal library of free-to-read Bible translations and study
    resources, most of them public domain, pulled together from established
    open-data projects. Nothing paywalled, DRM'd, or account-gated.
  </p>

  <div class="doors">
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
         Henry, JFB, Strong's, Nave's …) in the CrossWire SWORD format.</p>
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
        if self.command not in ("GET", "HEAD"):
            return self._not_found()
        # keep the encoded form for redirects, decode for the filesystem
        raw_path, _, query = self.path.partition("?")
        raw_path = raw_path.split("#", 1)[0]
        path = unquote(raw_path)
        if path == "/" or path == "/index.html":
            return self._send(200, landing_page(), "text/html; charset=utf-8",
                              cache_control="no-cache")
        if path == "/favicon.ico":
            return self._send(200, FAVICON.encode("ascii"), "image/svg+xml",
                              cache_control="public, max-age=604800")
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
                self.send_response(301)
                self.send_header("Location", raw_path + "/" + ("?" + query if query else ""))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._send_listing(candidate, rel)
        return self._not_found()

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
  body {{ margin: 0; background: #070b14; color: #e7f4f8;
          font: 16px/1.5 ui-monospace, monospace; }}
  main {{ max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }}
  .crumbs a {{ color: #2ee6c8; text-decoration: none; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid rgba(231,244,248,.08); }}
  td.s {{ text-align: right; color: #8aa3b3; white-space: nowrap; }}
  a {{ color: #e7f4f8; text-decoration: none; }}
  a:hover {{ color: #2ee6c8; }}
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
    BoundedThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
