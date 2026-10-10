"""
The Gift — JSON API behind the app (/api/…).

server.py does the HTTP plumbing (parsing, the CSRF check, cookies) and
hands each request here as a plain `Request`; this module only decides what
to answer. Library endpoints are public and cacheable. Account and group
endpoints need the session cookie and are never cached.
"""

import re
import threading

import gift_billing
import gift_community
import gift_music
import gift_places
import gift_study
from gift_community import Problem

LIBRARY_CACHE = "public, max-age=86400"   # the texts are static between releases
SEARCH_SLOTS = threading.BoundedSemaphore(4)  # folding is CPU work: cap it


def device_name(ua):
    """'Chrome on Android' from a User-Agent, for the signed-in devices list."""
    ua = ua or ""
    browser = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                   ("FxiOS", "Firefox"), ("CriOS", "Chrome"), ("Chrome/", "Chrome"),
                                   ("Safari/", "Safari")) if k in ua), "Browser")
    system = next((n for k, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                  ("Windows", "Windows"), ("Mac OS X", "Mac"), ("CrOS", "ChromeOS"),
                                  ("Linux", "Linux")) if k in ua), "")
    return f"{browser} on {system}" if system else browser


# Texts that may not travel inside a paid app: non-commercial, CrossWire-only
# and unknown licences. The Play Store build hides them (they stay free on the web).
RESTRICTED_CLASSES = {"Non-commercial", "CrossWire-only permission", "Unknown"}
RESTRICTED_MODULES = {"rwp"}


class Request:
    def __init__(self, method, path, query=None, body=None, ip="", token=None, upload=None, ua="",
                 channel="web", origin=""):
        self.method = method
        self.path = path
        self.query = query or {}
        self.body = body if isinstance(body, dict) else {}
        self.ip = ip
        self.token = token
        self.upload = upload  # (temporary file path, size) for /api/media
        self.device = device_name(ua)
        self.channel = "play" if channel == "play" else "web"
        self.origin = origin
        self.user = None


class Response:
    def __init__(self, status, body, cache="no-store", session=None):
        self.status = status
        self.body = body
        self.cache = cache
        self.session = session  # new token to set, "" to clear, None to leave alone


class App:
    def __init__(self, library, data_dir, places=None):
        self.library = library
        self.data_dir = data_dir
        self.places = places or gift_places.Places()
        self.study = gift_study.Study(library.root)
        self.dictionaries = gift_study.Dictionaries(library.root)
        self.limits = gift_community.RateLimiter()  # for public endpoints
        self._community = None
        self._music = None
        self._billing = None
        self._lock = threading.Lock()

    @property
    def community(self):
        if self._community is None:
            with self._lock:
                if self._community is None:
                    self.data_dir.mkdir(parents=True, exist_ok=True)
                    community = gift_community.Community(
                        self.data_dir / "community.sqlite3",
                        plans=self.library.plans, verses=self.library.verses)
                    community.billing = gift_billing.Billing(community)  # plan limits from the start
                    self._community = community
        return self._community

    @property
    def billing(self):
        return self.community.billing

    def restricted(self, tid):
        lic = self.library.licences().get(tid, {})
        return lic.get("class") in RESTRICTED_CLASSES

    @property
    def music(self):
        if self._music is None:
            self._music = gift_music.Music(self.community, self.library.root)
        return self._music


ROUTES = []


def route(method, pattern, auth=False, who=False):
    """auth: signed-in only. who: anyone, but look up who's asking if they
    are signed in (an artist sees their own unapproved songs, say)."""
    rx = re.compile(pattern + r"\Z")

    def wrap(fn):
        ROUTES.append((method, rx, "auth" if auth else "who" if who else "", fn))
        return fn
    return wrap


def dispatch(app, req):
    for method, rx, auth, fn in ROUTES:
        m = rx.match(req.path)
        if m and method == req.method:
            try:
                if auth:
                    req.user = app.community.session_user(req.token) if req.token else None
                    if auth == "auth" and req.user is None:
                        return Response(401, {"error": "Please sign in first."})
                return fn(app, req, *m.groups())
            except Problem as p:
                return Response(p.status, {"error": p.message})
            except gift_places.PlacesError as e:
                return Response(503, {"error": str(e)})
    if any(rx.match(req.path) for _, rx, _, _ in ROUTES):
        return Response(405, {"error": "method not allowed"})
    return Response(404, {"error": "not found"})


def _int(value, what):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise Problem(400, f"{what} must be a number.")


def _float(value, what):
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise Problem(400, f"{what} must be a number.")
    if f != f or f in (float("inf"), float("-inf")):
        raise Problem(400, f"{what} must be a number.")
    return f


# ------------------------------------------------------------------ library

def _translation_allowed(app, req, tid):
    if req.channel == "play" and app.restricted(tid):
        raise Problem(404, "That translation isn't available in this app.")


def _library_cache(req):
    # the Play app sees a different list: caches must keep them apart
    return "private, max-age=86400" if req.channel == "play" else LIBRARY_CACHE


@route("GET", r"/api/translations")
def translations(app, req):
    out = app.library.catalogue()
    if req.channel == "play":
        out = [t for t in out if t.get("class") not in RESTRICTED_CLASSES]
    return Response(200, {"translations": out}, _library_cache(req))


@route("GET", r"/api/books")
def books(app, req):
    _translation_allowed(app, req, req.query.get("t", ""))
    out = app.library.books(req.query.get("t", ""))
    if out is None:
        raise Problem(404, "Unknown translation.")
    return Response(200, out, _library_cache(req))


@route("GET", r"/api/chapter")
def chapter(app, req):
    q = req.query
    _translation_allowed(app, req, q.get("t", ""))
    out = app.library.chapter(q.get("t", ""), q.get("b", ""), _int(q.get("c"), "Chapter"))
    if out is None:
        raise Problem(404, "That chapter isn't in this translation.")
    return Response(200, out, LIBRARY_CACHE)


@route("GET", r"/api/search")
def search(app, req):
    q = req.query
    if not q.get("q", "").strip():
        raise Problem(400, "Type something to search for.")
    if not app.limits.allow(("search", req.ip), 60, 60):
        raise Problem(429, "Lots of searches at once. Wait a moment.")
    _translation_allowed(app, req, q.get("t", ""))
    if not SEARCH_SLOTS.acquire(timeout=10):
        raise Problem(503, "Search is busy. Try again in a moment.")
    try:
        out = app.library.search(q.get("t", ""), q["q"], book=q.get("b") or None)
    finally:
        SEARCH_SLOTS.release()
    if out is None:
        raise Problem(404, "Unknown translation.")
    return Response(200, out, "public, max-age=3600")


@route("GET", r"/api/plans")
def plans(app, req):
    out = [{k: p[k] for k in ("id", "title", "summary", "length", "chapters")}
           for p in app.library.plans().values()]
    return Response(200, {"plans": out}, LIBRARY_CACHE)


@route("GET", r"/api/plans/([a-z0-9-]{1,40})")
def plan(app, req, pid):
    p = app.library.plans().get(pid)
    if p is None:
        raise Problem(404, "Unknown reading plan.")
    return Response(200, p, LIBRARY_CACHE)


@route("GET", r"/api/devotional")
def devotional(app, req):
    month, _, day = req.query.get("date", "").partition("-")
    month, day = _int(month, "Month"), _int(day, "Day")
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise Problem(400, "Dates look like 10-31.")
    out = app.library.devotional_entry(month, day)
    if out is None:
        raise Problem(404, "No devotional for that day.")
    return Response(200, out, LIBRARY_CACHE)


@route("GET", r"/api/commentaries")
def commentaries(app, req):
    out = [dict(m, premium=m["id"] not in gift_billing.FREE_COMMENTARIES) for m in app.study.catalogue()
           if not (req.channel == "play" and m["id"] in RESTRICTED_MODULES)]
    return Response(200, {"commentaries": out}, _library_cache(req))


@route("GET", r"/api/commentary", who=True)
def commentary(app, req):
    q = req.query
    mid = q.get("m", "")
    if req.channel == "play" and mid in RESTRICTED_MODULES:
        raise Problem(404, "No note on this verse.")
    if mid not in gift_billing.FREE_COMMENTARIES:
        app.billing.require(req.user, "study")  # checked here, every time: never by the app
    note = app.study.note(mid, q.get("b", ""), _int(q.get("c"), "Chapter"), _int(q.get("v"), "Verse"))
    if note is None:
        raise Problem(404, "No note on this verse.")
    return Response(200, note, "private, max-age=86400")


# ------------------------------------------------------------------- places

@route("GET", r"/api/churches")
def churches(app, req):
    q = req.query
    lat, lon = _float(q.get("lat"), "Latitude"), _float(q.get("lon"), "Longitude")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise Problem(400, "That location is off the map.")
    radius = _int(q.get("radius", 5000), "Radius")
    if radius not in gift_places.RADII:
        raise Problem(400, "Pick one of the offered distances.")
    if not app.limits.allow(("places", req.ip), 30, 600):
        raise Problem(429, "Lots of searches from here. Try again in a few minutes.")
    return Response(200, {"places": app.places.churches(lat, lon, radius),
                          "attribution": "© OpenStreetMap contributors"})


@route("GET", r"/api/geocode")
def geocode(app, req):
    q = req.query.get("q", "").strip()
    if len(q) < 2:
        raise Problem(400, "Type a town or postcode.")
    if not app.limits.allow(("places", req.ip), 30, 600):
        raise Problem(429, "Lots of searches from here. Try again in a few minutes.")
    return Response(200, {"results": app.places.geocode(q),
                          "attribution": "© OpenStreetMap contributors"})


# ----------------------------------------------------------------- accounts

@route("GET", r"/api/me", who=True)
def me(app, req):
    return Response(200, {"user": req.user})


@route("POST", r"/api/signup")
def signup(app, req):
    b = req.body
    token, user = app.community.signup(b.get("username"), b.get("name"), b.get("password"), req.ip,
                                       req.device)
    return Response(200, {"user": user}, session=token)


@route("POST", r"/api/login")
def login(app, req):
    b = req.body
    token, user = app.community.login(b.get("username"), b.get("password"), req.ip, req.device)
    return Response(200, {"user": user}, session=token)


@route("POST", r"/api/logout")
def logout(app, req):
    app.community.logout(req.token)
    return Response(200, {"ok": True}, session="")


@route("POST", r"/api/me", auth=True)
def rename(app, req):
    return Response(200, {"user": app.community.rename(req.user, req.body.get("name"))})


@route("POST", r"/api/me/profile", auth=True)
def update_profile(app, req):
    return Response(200, {"user": app.community.update_profile(req.user, req.body)})


@route("GET", r"/api/profiles/@?([A-Za-z0-9_.]{3,24})", auth=True)
def profile(app, req, username):
    out = app.community.profile(req.user, username)
    out["artist"] = app.music.artist_of(out["id"])
    return Response(200, out)


@route("GET", r"/api/me/progress", auth=True)
def my_progress(app, req):
    return Response(200, app.community.progress_summary(req.user["id"], full=True))


@route("POST", r"/api/me/progress", auth=True)
def mark_progress(app, req):
    b = req.body
    return Response(200, app.community.mark_chapters(req.user, b.get("items"), b.get("done", True) is not False,
                                                     b.get("day")))


@route("GET", r"/api/me/rewards", auth=True)
def my_rewards(app, req):
    return Response(200, app.community.rewards(req.user["id"]))


@route("POST", r"/api/me/verify", auth=True)
def verify(app, req):
    app.community.verify(req.user, req.body.get("password"), req.ip)
    return Response(200, {"ok": True})


@route("GET", r"/api/me/sessions", auth=True)
def sessions(app, req):
    return Response(200, {"sessions": app.community.sessions(req.user)})


@route("POST", r"/api/me/sessions/revoke", auth=True)
def revoke(app, req):
    app.community.revoke_session(req.user, req.body.get("id"), req.ip)
    return Response(200, {"sessions": app.community.sessions(req.user)})


@route("GET", r"/api/admin/audit", auth=True)
def audit(app, req):
    if not req.user.get("is_admin"):
        raise Problem(403, "Admins only.")
    return Response(200, {"events": app.community.audit_log(req.user)})


@route("POST", r"/api/media", auth=True)
def upload(app, req):
    if not req.upload:
        raise Problem(400, "Send the file itself.")
    return Response(200, app.community.add_media(req.user, *req.upload))


# ------------------------------------------------------------------ friends

@route("GET", r"/api/friends", auth=True)
def friends(app, req):
    return Response(200, app.community.friends(req.user))


@route("POST", r"/api/friends/request", auth=True)
def friend_request(app, req):
    return Response(200, {"relationship": app.community.friend_request(req.user, req.body.get("username"))})


@route("POST", r"/api/friends/accept", auth=True)
def friend_accept(app, req):
    return Response(200, {"relationship": app.community.friend_accept(req.user, req.body.get("user_id"))})


@route("POST", r"/api/friends/remove", auth=True)
def friend_remove(app, req):
    return Response(200, {"relationship": app.community.friend_remove(req.user, req.body.get("user_id"))})


@route("POST", r"/api/me/password", auth=True)
def change_password(app, req):
    b = req.body
    token = app.community.change_password(req.user, b.get("current"), b.get("new"))
    return Response(200, {"ok": True}, session=token)


@route("POST", r"/api/me/delete", auth=True)
def delete_me(app, req):
    app.community.delete_account(req.user, req.body.get("password"))
    return Response(200, {"ok": True}, session="")


# ------------------------------------------------------------------- groups

@route("GET", r"/api/groups", auth=True)
def groups(app, req):
    return Response(200, {"groups": app.community.groups(req.user)})


@route("POST", r"/api/groups", auth=True)
def create_group(app, req):
    return Response(200, app.community.create_group(req.user, req.body))


@route("GET", r"/api/invites/([A-Za-z0-9_-]{6,40})")
def invite(app, req, code):
    return Response(200, app.community.preview_invite(code))


@route("POST", r"/api/groups/join", auth=True)
def join(app, req):
    return Response(200, app.community.join(req.user, req.body.get("code"), req.ip))


@route("GET", r"/api/groups/(\d{1,12})", auth=True)
def group(app, req, gid):
    return Response(200, app.community.group(req.user, int(gid)))


@route("POST", r"/api/groups/(\d{1,12})", auth=True)
def update_group(app, req, gid):
    return Response(200, app.community.update_group(req.user, int(gid), req.body))


@route("POST", r"/api/groups/(\d{1,12})/leave", auth=True)
def leave(app, req, gid):
    app.community.leave(req.user, int(gid))
    return Response(200, {"ok": True})


@route("POST", r"/api/groups/(\d{1,12})/delete", auth=True)
def delete_group(app, req, gid):
    app.community.delete_group(req.user, int(gid))
    return Response(200, {"ok": True})


@route("POST", r"/api/groups/(\d{1,12})/invite", auth=True)
def reset_invite(app, req, gid):
    return Response(200, app.community.reset_invite(req.user, int(gid)))


@route("POST", r"/api/groups/(\d{1,12})/remove", auth=True)
def remove_member(app, req, gid):
    return Response(200, app.community.remove_member(req.user, int(gid), req.body.get("user_id")))


@route("POST", r"/api/groups/(\d{1,12})/role", auth=True)
def set_role(app, req, gid):
    b = req.body
    return Response(200, app.community.set_role(req.user, int(gid), b.get("user_id"), b.get("role"),
                                                b.get("title")))


@route("POST", r"/api/groups/(\d{1,12})/leader", auth=True)
def make_leader(app, req, gid):
    target = req.body.get("user_id")
    if not isinstance(target, int):
        raise Problem(400, "Pick a member.")
    return Response(200, app.community.make_leader(req.user, int(gid), target))


@route("POST", r"/api/groups/(\d{1,12})/progress", auth=True)
def progress(app, req, gid):
    b = req.body
    return Response(200, app.community.set_progress(req.user, int(gid), b.get("day"),
                                                    bool(b.get("done"))))


@route("GET", r"/api/groups/(\d{1,12})/messages", auth=True)
def messages(app, req, gid):
    q = req.query
    after = _int(q["after"], "after") if "after" in q else None
    before = _int(q["before"], "before") if "before" in q else None
    return Response(200, {"messages": app.community.messages(req.user, int(gid), after, before)})


@route("POST", r"/api/groups/(\d{1,12})/messages", auth=True)
def post(app, req, gid):
    b = req.body
    return Response(200, app.community.post(req.user, int(gid), b.get("body"), b.get("ref")))


@route("POST", r"/api/groups/(\d{1,12})/messages/(\d{1,12})/delete", auth=True)
def delete_message(app, req, gid, mid):
    app.community.delete_message(req.user, int(gid), int(mid))
    return Response(200, {"ok": True})


# -------------------------------------------------------------------- music

@route("GET", r"/api/music")
def music(app, req):
    return Response(200, app.music.overview(), "no-cache")


@route("GET", r"/api/hymns/([a-z0-9-]{1,60})")
def hymn(app, req, hid):
    return Response(200, app.music.hymn(hid), LIBRARY_CACHE)


@route("GET", r"/api/artists/(\d{1,12})", who=True)
def artist(app, req, aid):
    return Response(200, app.music.artist(req.user, int(aid)))


@route("POST", r"/api/songs/(\d{1,12})/play")
def played(app, req, sid):
    app.music.played(int(sid), req.ip)
    return Response(200, {"ok": True})


@route("GET", r"/api/studio", auth=True)
def studio(app, req):
    return Response(200, app.music.studio(req.user))


@route("POST", r"/api/studio", auth=True)
def apply(app, req):
    return Response(200, app.music.apply(req.user, req.body))


@route("POST", r"/api/studio/songs", auth=True)
def add_song(app, req):
    return Response(200, app.music.add_song(req.user, req.body))


@route("POST", r"/api/songs/(\d{1,12})/delete", auth=True)
def delete_song(app, req, sid):
    app.music.delete_song(req.user, int(sid))
    return Response(200, {"ok": True})


@route("GET", r"/api/admin", auth=True)
def admin(app, req):
    return Response(200, app.music.queue(req.user))


@route("POST", r"/api/admin/artists/(\d{1,12})", auth=True)
def review_artist(app, req, aid):
    b = req.body
    return Response(200, app.music.review_artist(req.user, int(aid), b.get("action"), b.get("note", "")))


@route("POST", r"/api/admin/songs/(\d{1,12})", auth=True)
def review_song(app, req, sid):
    b = req.body
    return Response(200, app.music.review_song(req.user, int(sid), b.get("action"), b.get("note", "")))


# ------------------------------------------------------------------- safety

@route("POST", r"/api/report", auth=True)
def report(app, req):
    b = req.body
    app.community.report(req.user, b.get("kind"), b.get("id"), b.get("reason"), b.get("detail", ""))
    return Response(200, {"ok": True})


@route("POST", r"/api/block", auth=True)
def block(app, req):
    app.community.block(req.user, req.body.get("user_id"), req.body.get("block", True) is not False)
    return Response(200, {"blocked": app.community.blocked(req.user)})


@route("GET", r"/api/me/blocks", auth=True)
def blocks(app, req):
    return Response(200, {"blocked": app.community.blocked(req.user)})


@route("GET", r"/api/admin/reports", auth=True)
def reports(app, req):
    return Response(200, {"reports": app.community.reports_open(req.user)})


@route("POST", r"/api/admin/reports/(\d{1,12})", auth=True)
def resolve_report(app, req, rid):
    app.community.resolve_report(req.user, int(rid), req.body.get("action"))
    return Response(200, {"reports": app.community.reports_open(req.user)})


# ------------------------------------------------------------------ billing

@route("GET", r"/api/billing", auth=True)
def billing_status(app, req):
    app.billing.refresh_play(req.user)
    return Response(200, app.billing.status(req.user))


@route("POST", r"/api/billing/stripe/checkout", auth=True)
def stripe_checkout(app, req):
    b = req.body
    return Response(200, app.billing.stripe_checkout(req.user, b.get("plan"), b.get("period"), req.origin))


@route("POST", r"/api/billing/stripe/portal", auth=True)
def stripe_portal(app, req):
    return Response(200, app.billing.stripe_portal(req.user, req.origin))


@route("POST", r"/api/billing/play/verify", auth=True)
def play_verify(app, req):
    b = req.body
    return Response(200, app.billing.play_verify(req.user, b.get("product"), b.get("token")))


@route("POST", r"/api/contact/church")
def church(app, req):
    return Response(200, app.billing.church_inquiry(req.body, req.ip))


@route("GET", r"/api/admin/inquiries", auth=True)
def inquiries(app, req):
    return Response(200, {"inquiries": app.billing.inquiries(req.user)})


# ------------------------------------------------------- plus & premium

@route("GET", r"/api/dictionary", who=True)
def dictionary(app, req):
    app.billing.require(req.user, "study")
    return Response(200, app.dictionaries.lookup(req.query.get("q", "")), "private, max-age=86400")


@route("GET", r"/api/download", auth=True)
def download(app, req):
    """A whole translation for offline reading (Plus). Texts that may not be
    part of a paid feature (non-commercial and the like) are never offered."""
    app.billing.require(req.user, "offline")
    tid = req.query.get("t", "")
    if app.restricted(tid):
        raise Problem(403, "This translation's licence doesn't allow offline copies in a paid feature.")
    if not app.limits.allow(("download", req.user["id"]), 20, 3600):
        raise Problem(429, "That's a lot of downloads. Try again in a while.")
    out = app.library.download(tid)
    if out is None:
        raise Problem(404, "Unknown translation.")
    return Response(200, out, "private, max-age=86400")


@route("POST", r"/api/sync", auth=True)
def sync(app, req):
    app.billing.require(req.user, "sync")
    b = req.body
    return Response(200, app.community.sync(req.user, b.get("since", 0), b.get("changes", [])))


@route("POST", r"/api/sync/reset", auth=True)
def sync_reset(app, req):
    app.billing.require(req.user, "sync")
    app.community.sync_reset(req.user, req.body.get("kind"))
    return Response(200, {"ok": True})
