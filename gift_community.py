"""
The Gift — accounts, profiles, friends and private online study groups.

Stdlib only: sqlite3 for storage, hashlib.scrypt for passwords. Groups are
private and online: there is no directory and no public room, you join a
group with its invite link. Each member has a role: leaders run the group
(and hand out roles), moderators keep the chat in order (delete messages,
remove members, reset the invite link), members take part; a leader can
also give anyone a short title such as "Prayer lead".

People have a profile (name, picture, a short bio, a favourite verse),
friends, and a record of which Bible chapters they've read. The journal,
highlights and personal plan progress still never come here; they stay on
the reader's device.

The database lives in GIFT_DATA_DIR (see server.py), never inside the
served tree. There is no email, so nobody can reset a password by
themselves; the box admin can (see the command at the bottom):

  sudo -u www-data GIFT_DATA_DIR=/var/lib/the-gift \
      python3 gift_community.py reset-password <username>
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import unicodedata
from collections import deque
from datetime import date, timedelta
from pathlib import Path

import gift_media
import gift_rewards
from gift_study import SLOTS

SESSION_DAYS = 30            # a session lasts at most this long…
SESSION_IDLE_DAYS = 14       # …and ends sooner if unused this long
VERIFY_MINUTES = 30          # admin actions need a password typed this recently
MAX_MEMBERS = 150            # per group
MAX_GROUPS = 30              # groups one person can belong to
MESSAGE_MAX = 2000           # characters
PAGE = 50                    # messages per history page
MAX_FRIENDS = 1000
BIO_MAX = 300
TITLE_MAX = 30               # a member's badge in a group, e.g. "Prayer lead"
ROLES = {"leader": 3, "moderator": 2, "member": 1}
CANON_CHAPTERS = len(SLOTS)  # 1189: progress is tracked over the 66-book Bible

USERNAME_RE = re.compile(r"[a-z0-9_.]{3,24}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

GROUP_MEMBERS = """CREATE TABLE IF NOT EXISTS group_members (
  group_id  INTEGER NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role      TEXT NOT NULL CHECK (role IN ('leader', 'moderator', 'member')),
  title     TEXT NOT NULL DEFAULT '',
  joined    INTEGER NOT NULL,
  last_read INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (group_id, user_id)
)"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  pw_salt       BLOB NOT NULL,
  pw_hash       BLOB NOT NULL,
  created       INTEGER NOT NULL,
  bio           TEXT NOT NULL DEFAULT '',
  verse         TEXT,
  avatar        TEXT,
  show_progress INTEGER NOT NULL DEFAULT 1,
  is_admin      INTEGER NOT NULL DEFAULT 0,
  suspended     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash BLOB PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires    INTEGER NOT NULL,
  created    INTEGER NOT NULL DEFAULT 0,
  last_seen  INTEGER NOT NULL DEFAULT 0,
  verified   INTEGER NOT NULL DEFAULT 0,
  device     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit (
  id      INTEGER PRIMARY KEY,
  at      INTEGER NOT NULL,
  user_id INTEGER,
  ip      TEXT NOT NULL DEFAULT '',
  action  TEXT NOT NULL,
  detail  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS audit_by_time ON audit(at);
CREATE TABLE IF NOT EXISTS study_groups (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  about      TEXT NOT NULL DEFAULT '',
  area       TEXT NOT NULL DEFAULT '',
  invite     TEXT NOT NULL UNIQUE,
  plan       TEXT,
  plan_start TEXT,
  created    INTEGER NOT NULL
);
""" + GROUP_MEMBERS + """;
CREATE INDEX IF NOT EXISTS members_by_user ON group_members(user_id);
CREATE TABLE IF NOT EXISTS messages (
  id       INTEGER PRIMARY KEY,
  group_id INTEGER NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body     TEXT NOT NULL,
  ref      TEXT,
  created  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_group ON messages(group_id, id);
CREATE TABLE IF NOT EXISTS plan_progress (
  group_id INTEGER NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day      INTEGER NOT NULL,
  PRIMARY KEY (group_id, user_id, day)
);
CREATE TABLE IF NOT EXISTS friendships (
  a         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  b         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  requester INTEGER NOT NULL,
  status    TEXT NOT NULL CHECK (status IN ('pending', 'accepted')),
  created   INTEGER NOT NULL,
  PRIMARY KEY (a, b),
  CHECK (a < b)
);
CREATE INDEX IF NOT EXISTS friendships_by_b ON friendships(b);
CREATE TABLE IF NOT EXISTS chapters_read (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book    TEXT NOT NULL,
  chapter INTEGER NOT NULL,
  day     TEXT NOT NULL,
  PRIMARY KEY (user_id, book, chapter)
);
CREATE TABLE IF NOT EXISTS media (
  id       TEXT PRIMARY KEY,
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind     TEXT NOT NULL,
  mime     TEXT NOT NULL,
  ext      TEXT NOT NULL,
  size     INTEGER NOT NULL,
  created  INTEGER NOT NULL,
  used     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS artists (
  id       INTEGER PRIMARY KEY,
  user_id  INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  name     TEXT NOT NULL,
  genre    TEXT NOT NULL DEFAULT '',
  bio      TEXT NOT NULL DEFAULT '',
  links    TEXT NOT NULL DEFAULT '{}',
  photo    TEXT,
  status   TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
  featured INTEGER NOT NULL DEFAULT 0,
  note     TEXT NOT NULL DEFAULT '',
  created  INTEGER NOT NULL,
  reviewed INTEGER
);
CREATE TABLE IF NOT EXISTS songs (
  id        INTEGER PRIMARY KEY,
  artist_id INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
  title     TEXT NOT NULL,
  media     TEXT NOT NULL,
  lyrics    TEXT NOT NULL DEFAULT '',
  status    TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
  note      TEXT NOT NULL DEFAULT '',
  plays     INTEGER NOT NULL DEFAULT 0,
  created   INTEGER NOT NULL,
  reviewed  INTEGER
);
CREATE INDEX IF NOT EXISTS songs_by_artist ON songs(artist_id);
CREATE TABLE IF NOT EXISTS reports (
  id          INTEGER PRIMARY KEY,
  reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('message', 'user', 'song', 'artist')),
  target_id   INTEGER NOT NULL,
  reason      TEXT NOT NULL,
  detail      TEXT NOT NULL DEFAULT '',
  snapshot    TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
  created     INTEGER NOT NULL,
  resolved    INTEGER
);
CREATE TABLE IF NOT EXISTS user_data (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind    TEXT NOT NULL,
  key     TEXT NOT NULL,
  value   TEXT,
  updated INTEGER NOT NULL,
  seq     INTEGER NOT NULL,
  PRIMARY KEY (user_id, kind, key)
);
CREATE INDEX IF NOT EXISTS user_data_by_seq ON user_data(user_id, seq);
CREATE TABLE IF NOT EXISTS blocks (
  blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created    INTEGER NOT NULL,
  PRIMARY KEY (blocker_id, blocked_id)
);
"""

REPORT_REASONS = ("spam", "harassment", "hate", "sexual", "violence", "self-harm", "misinformation",
                  "copyright", "other")


def _migrate(db):
    """Bring a database made by an earlier release up to SCHEMA. Only ever
    adds: columns get defaults, and nothing is dropped."""
    have = {r[1] for r in db.execute("PRAGMA table_info(users)")}
    for col, decl in (("bio", "TEXT NOT NULL DEFAULT ''"), ("verse", "TEXT"), ("avatar", "TEXT"),
                      ("show_progress", "INTEGER NOT NULL DEFAULT 1"),
                      ("is_admin", "INTEGER NOT NULL DEFAULT 0"),
                      ("suspended", "INTEGER NOT NULL DEFAULT 0")):
        if col not in have:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
    have = {r[1] for r in db.execute("PRAGMA table_info(sessions)")}
    for col in ("created", "last_seen", "verified"):
        if col not in have:
            db.execute(f"ALTER TABLE sessions ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
    if "device" not in have:
        db.execute("ALTER TABLE sessions ADD COLUMN device TEXT NOT NULL DEFAULT ''")
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name='group_members'").fetchone()[0]
    if "'moderator'" not in sql:  # the first release had only leaders and members
        db.execute("ALTER TABLE group_members RENAME TO group_members_v1")
        db.execute(GROUP_MEMBERS)
        db.execute("INSERT INTO group_members (group_id, user_id, role, joined, last_read) "
                   "SELECT group_id, user_id, role, joined, last_read FROM group_members_v1")
        db.execute("DROP TABLE group_members_v1")
        db.execute("CREATE INDEX IF NOT EXISTS members_by_user ON group_members(user_id)")


class Problem(Exception):
    """A request the caller got wrong: carries the HTTP status and a
    message that is safe to show the person."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# scrypt with n=2**14, r=8 takes 16 MB of RAM per hash. Under the service's
# 512M ceiling, a burst of logins must not run dozens at once.
_hash_slots = threading.BoundedSemaphore(2)
_DUMMY_SALT = secrets.token_bytes(16)


def _hash_password(password, salt):
    with _hash_slots:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt,
                              n=2 ** 14, r=8, p=1, dklen=32)


def _clean_text(s, limit, multiline=False):
    """Trim, drop control characters, cap the length."""
    if not isinstance(s, str):
        return ""
    keep = "\n" if multiline else ""
    s = "".join(ch for ch in s if ch in keep or unicodedata.category(ch)[0] != "C")
    if multiline:
        s = re.sub(r"\n{3,}", "\n\n", s.replace("\r\n", "\n"))
    else:
        s = " ".join(s.split())
    return s.strip()[:limit]


class RateLimiter:
    """Sliding-window counters kept in memory (they reset on restart, which
    is fine: they only exist to blunt bursts)."""

    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, key, limit, window):
        """Count one event; False (and not counted) if over the limit."""
        return self._check(key, limit, window, record=True)

    def blocked(self, key, limit, window):
        """Already at the limit? Checks without counting."""
        return not self._check(key, limit, window, record=False)

    def hit(self, key):
        self._check(key, float("inf"), 0, record=True)

    def _check(self, key, limit, window, record):
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                if len(self._hits) > 20000:  # forget idle keys before growing
                    self._hits = {k: v for k, v in self._hits.items()
                                  if v and now - v[-1] < 3600}
                q = self._hits[key] = deque()
            while window and q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            if record:
                q.append(now)
            return True


class Community:
    def __init__(self, db_path, plans=None, verses=None):
        """`plans()` returns {id: plan} so groups can follow one;
        `verses(t, b, c, v1, v2)` returns [[n, text]] so a verse shared into
        chat (or set as a favourite) is quoted from the library, never typed
        in by the person. Uploads live in a media/ folder beside the db."""
        self.db_path = str(db_path)
        self.data_dir = Path(db_path).parent
        self.plans = plans or (lambda: {})
        self.verses = verses or (lambda *a: None)
        self.billing = None  # set by gift_api: plan limits (lead groups, group size)
        self.limits = RateLimiter()
        self._write = threading.Lock()
        with self._write, self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)  # every table, if missing (executescript commits)
            db.execute("BEGIN IMMEDIATE")
            try:
                _migrate(db)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return _Conn(db)

    def _tx(self):
        """A write transaction: one writer at a time, so no SQLITE_BUSY."""
        return _Tx(self)

    def audit_log(self, user, limit=200):
        self.require_verified(user)
        with self._db() as db:
            rows = db.execute("SELECT a.at, a.action, a.ip, a.detail, u.username FROM audit a "
                              "LEFT JOIN users u ON u.id = a.user_id ORDER BY a.id DESC LIMIT ?",
                              (limit,)).fetchall()
        return [dict(r) for r in rows]

    def audit(self, action, user_id=None, ip="", **detail):
        """Security-relevant events, for admins to review (zero trust: verify,
        and keep a record of what was verified). Never passwords or tokens."""
        with self._tx() as db:
            db.execute("INSERT INTO audit (at, user_id, ip, action, detail) VALUES (?,?,?,?,?)",
                       (int(time.time()), user_id, str(ip)[:64], action,
                        json.dumps(detail, ensure_ascii=False)[:500] if detail else ""))
            db.execute("DELETE FROM audit WHERE at < ?", (int(time.time()) - 180 * 86400,))

    # ------------------------------------------------------------ accounts

    def signup(self, username, name, password, ip, device=""):
        username = (username or "").strip().lower() if isinstance(username, str) else ""
        if not USERNAME_RE.fullmatch(username):
            raise Problem(400, "Usernames are 3–24 characters: letters, numbers, _ or .")
        name = _clean_text(name, 40) or username
        if not isinstance(password, str) or not 8 <= len(password) <= 200:
            raise Problem(400, "Passwords need at least 8 characters.")
        # generous: a whole home group may sign up together on one church Wi-Fi
        if not self.limits.allow(("signup", ip), 30, 3600):
            raise Problem(429, "Too many new accounts from here. Try again later.")
        salt = secrets.token_bytes(16)
        pw = _hash_password(password, salt)
        with self._tx() as db:
            if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                raise Problem(409, "That username is taken.")
            cur = db.execute(
                "INSERT INTO users (username, name, pw_salt, pw_hash, created) VALUES (?,?,?,?,?)",
                (username, name, salt, pw, int(time.time())))
            uid = cur.lastrowid
        self.audit("signup", uid, ip)
        return self._new_session(uid, device), self.user(uid)

    def login(self, username, password, ip, device=""):
        username = username.strip().lower() if isinstance(username, str) else ""
        password = password if isinstance(password, str) else ""
        # only failures count, per address and per account: a room full of
        # people signing in at once is fine, guessing one password is not
        if (self.limits.blocked(("login-fail", ip), 30, 900)
                or self.limits.blocked(("login-fail", username), 10, 900)):
            raise Problem(429, "Too many failed sign-ins. Wait a few minutes.")
        with self._db() as db:
            row = db.execute("SELECT id, pw_salt, pw_hash, suspended FROM users WHERE username=?",
                             (username,)).fetchone()
        if row is None:
            _hash_password(password[:200], _DUMMY_SALT)  # same cost either way
        if row is None or not hmac.compare_digest(
                _hash_password(password[:200], row["pw_salt"]), row["pw_hash"]):
            self.limits.hit(("login-fail", ip))
            self.limits.hit(("login-fail", username))
            self.audit("login-failed", row["id"] if row else None, ip, username=username[:24])
            raise Problem(401, "Wrong username or password.")
        if row["suspended"]:
            self.audit("login-suspended", row["id"], ip)
            raise Problem(403, "This account has been suspended. Contact the site admin.")
        self.audit("login", row["id"], ip, device=device)
        return self._new_session(row["id"], device), self.user(row["id"])

    def _new_session(self, uid, device=""):
        """A session is a random token held only by the browser (as an
        HttpOnly cookie); the database keeps its hash. Signing in counts as
        having just typed the password."""
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._tx() as db:
            db.execute("DELETE FROM sessions WHERE expires < ? OR last_seen < ?",
                       (now, now - SESSION_IDLE_DAYS * 86400))
            db.execute("INSERT INTO sessions (token_hash, user_id, expires, created, last_seen, verified, "
                       "device) VALUES (?,?,?,?,?,?,?)",
                       (_token_hash(token), uid, now + SESSION_DAYS * 86400, now, now, now,
                        str(device or "")[:60]))
        return token

    def session_user(self, token):
        """Who holds this token, checked on every request: expired, idle or
        revoked sessions get nothing."""
        if not token or len(token) > 100:
            return None
        now = int(time.time())
        h = _token_hash(token)
        with self._db() as db:
            row = db.execute(
                "SELECT u.id, u.username, u.name, u.avatar, u.is_admin, s.last_seen, s.verified "
                "FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash=? AND s.expires>=? AND s.last_seen>=? AND u.suspended=0",
                (h, now, now - SESSION_IDLE_DAYS * 86400)).fetchone()
        if row is None:
            return None
        if now - row["last_seen"] > 300:  # at most one write per five minutes
            with self._tx() as db:
                db.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, h))
        user = _person(row, admin=True)
        user["verified"] = now - row["verified"] <= VERIFY_MINUTES * 60
        user["session"] = h.hex()[:16]
        return user

    def verify(self, user, password, ip):
        """Step-up: type the password again before admin work."""
        if self.limits.blocked(("login-fail", user["username"]), 10, 900):
            raise Problem(429, "Too many failed attempts. Wait a few minutes.")
        with self._db() as db:
            row = db.execute("SELECT pw_salt, pw_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not hmac.compare_digest(_hash_password(str(password or "")[:200], row["pw_salt"]), row["pw_hash"]):
            self.limits.hit(("login-fail", user["username"]))
            self.audit("verify-failed", user["id"], ip)
            raise Problem(401, "That password isn't right.")
        with self._tx() as db:
            db.execute("UPDATE sessions SET verified=? WHERE user_id=? AND substr(hex(token_hash),1,16)=?",
                       (int(time.time()), user["id"], user["session"].upper()))
        self.audit("verify", user["id"], ip)

    def require_verified(self, user):
        if not user.get("verified"):
            raise Problem(403, "Confirm your password to continue.")

    def sessions(self, user):
        with self._db() as db:
            rows = db.execute("SELECT hex(token_hash) AS h, created, last_seen, device FROM sessions "
                              "WHERE user_id=? ORDER BY last_seen DESC", (user["id"],)).fetchall()
        return [{"id": r["h"][:16].lower(), "created": r["created"], "last_seen": r["last_seen"],
                 "device": r["device"] or "Unknown device", "current": r["h"][:16].lower() == user["session"]}
                for r in rows]

    def revoke_session(self, user, sid, ip):
        """Sign a device out. 'others' signs out every device but this one."""
        with self._tx() as db:
            if sid == "others":
                db.execute("DELETE FROM sessions WHERE user_id=? AND substr(hex(token_hash),1,16)!=?",
                           (user["id"], user["session"].upper()))
            elif isinstance(sid, str) and re.fullmatch(r"[0-9a-f]{16}", sid):
                db.execute("DELETE FROM sessions WHERE user_id=? AND substr(hex(token_hash),1,16)=?",
                           (user["id"], sid.upper()))
            else:
                raise Problem(400, "Pick a device.")
        self.audit("sessions-revoked", user["id"], ip, which=sid)

    def logout(self, token):
        if token:
            with self._tx() as db:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))

    def user(self, uid):
        with self._db() as db:
            row = db.execute("SELECT id, username, name, avatar, is_admin FROM users WHERE id=?",
                             (uid,)).fetchone()
        return _person(row, admin=True) if row else None

    def change_password(self, user, current, new):
        """Returns a fresh session token: every other device is signed out."""
        if self.limits.blocked(("login-fail", user["username"]), 10, 900):
            raise Problem(429, "Too many failed attempts. Wait a few minutes.")
        with self._db() as db:
            row = db.execute("SELECT pw_salt, pw_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if row is None or not hmac.compare_digest(
                _hash_password(str(current or "")[:200], row["pw_salt"]), row["pw_hash"]):
            self.limits.hit(("login-fail", user["username"]))
            raise Problem(401, "Your current password isn't right.")
        self._set_password(user["id"], new)
        self.audit("password-changed", user["id"])
        return self._new_session(user["id"], "")

    def _set_password(self, uid, password):
        if not isinstance(password, str) or not 8 <= len(password) <= 200:
            raise Problem(400, "Passwords need at least 8 characters.")
        salt = secrets.token_bytes(16)
        pw = _hash_password(password, salt)
        with self._tx() as db:
            db.execute("UPDATE users SET pw_salt=?, pw_hash=? WHERE id=?", (salt, pw, uid))
            db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))

    def reset_password(self, username):
        """Admin-only (command line): a temporary password, all sessions ended."""
        with self._db() as db:
            row = db.execute("SELECT id FROM users WHERE username=?",
                             (username.strip().lower(),)).fetchone()
        if row is None:
            raise Problem(404, f"No account called {username!r}.")
        temp = "-".join(secrets.token_hex(3) for _ in range(3))
        self._set_password(row["id"], temp)
        self.audit("password-reset-by-admin", row["id"], "command line")
        return temp

    def rename(self, user, name):
        name = _clean_text(name, 40)
        if not name:
            raise Problem(400, "Your name can't be empty.")
        with self._tx() as db:
            db.execute("UPDATE users SET name=? WHERE id=?", (name, user["id"]))
        return self.user(user["id"])

    def delete_account(self, user, password):
        with self._db() as db:
            row = db.execute("SELECT pw_salt, pw_hash FROM users WHERE id=?",
                             (user["id"],)).fetchone()
        if row is None or not hmac.compare_digest(
                _hash_password(str(password or "")[:200], row["pw_salt"]), row["pw_hash"]):
            raise Problem(401, "That password isn't right.")
        with self._tx() as db:
            for (gid,) in db.execute("SELECT group_id FROM group_members WHERE user_id=?",
                                     (user["id"],)).fetchall():
                self._leave(db, gid, user["id"])
            files = db.execute("SELECT id, ext FROM media WHERE owner_id=?", (user["id"],)).fetchall()
            # messages, sessions, friends, reading progress, uploads, artist
            # profile and songs all go with the account (ON DELETE CASCADE)
            db.execute("DELETE FROM users WHERE id=?", (user["id"],))
        for f in files:
            gift_media.remove(self.data_dir, f["id"], f["ext"])
        self.audit("account-deleted", None, "", username=user["username"])

    def set_admin(self, username, on=True):
        """Command line only: who can approve artists and songs."""
        with self._tx() as db:
            cur = db.execute("UPDATE users SET is_admin=? WHERE username=?",
                             (1 if on else 0, username.strip().lower()))
            if not cur.rowcount:
                raise Problem(404, f"No account called {username!r}.")
        self.audit("admin-granted" if on else "admin-removed", None, "command line",
                   username=username.strip().lower())

    # -------------------------------------------------------------- groups

    def _membership(self, db, gid, uid):
        row = db.execute("SELECT role FROM group_members WHERE group_id=? AND user_id=?",
                         (gid, uid)).fetchone()
        if row is None:
            raise Problem(404, "Group not found.")
        return row["role"]

    def _require(self, db, gid, uid, at_least, message):
        role = self._membership(db, gid, uid)
        if ROLES[role] < ROLES[at_least]:
            raise Problem(403, message)
        return role

    def _check_plan(self, plan, start):
        if not plan:
            return None, None
        if plan not in self.plans():
            raise Problem(400, "Unknown reading plan.")
        if not isinstance(start, str) or not DATE_RE.fullmatch(start):
            raise Problem(400, "Pick a start date for the plan.")
        return plan, start

    def create_group(self, user, fields):
        if not self.limits.allow(("create", user["id"]), 10, 86400):
            raise Problem(429, "You've started a lot of groups today. Try again tomorrow.")
        name = _clean_text(fields.get("name"), 60)
        if not name:
            raise Problem(400, "Give the group a name.")
        plan, start = self._check_plan(fields.get("plan"), fields.get("plan_start"))
        now = int(time.time())
        if self.billing is not None:
            cap = self.billing.limits(user["id"])["lead_groups"]
            with self._db() as db:
                leading = db.execute("SELECT COUNT(*) FROM group_members WHERE user_id=? AND role='leader'",
                                     (user["id"],)).fetchone()[0]
            if leading >= cap:
                raise Problem(402, f"You can lead {cap} groups on your plan. Premium lets you lead up to 20.")
        with self._tx() as db:
            self._check_group_cap(db, user["id"])
            cur = db.execute(
                "INSERT INTO study_groups (name, about, area, invite, plan, plan_start, created) "
                "VALUES (?,?,?,?,?,?,?)",
                (name, _clean_text(fields.get("about"), 500, multiline=True),
                 _clean_text(fields.get("area"), 80), _invite_code(), plan, start, now))
            gid = cur.lastrowid
            db.execute("INSERT INTO group_members (group_id, user_id, role, joined) VALUES (?,?,?,?)",
                       (gid, user["id"], "leader", now))
        return self.group(user, gid)

    def _check_group_cap(self, db, uid):
        n = db.execute("SELECT COUNT(*) FROM group_members WHERE user_id=?", (uid,)).fetchone()[0]
        if n >= MAX_GROUPS:
            raise Problem(400, f"You can be in at most {MAX_GROUPS} groups.")

    def update_group(self, user, gid, fields):
        with self._tx() as db:
            self._require(db, gid, user["id"], "leader", "Only a group leader can change the group.")
            row = db.execute("SELECT * FROM study_groups WHERE id=?", (gid,)).fetchone()
            name = _clean_text(fields.get("name", row["name"]), 60)
            if not name:
                raise Problem(400, "Give the group a name.")
            plan, start = row["plan"], row["plan_start"]
            if "plan" in fields:
                plan, start = self._check_plan(fields.get("plan"), fields.get("plan_start"))
                if (plan, start) != (row["plan"], row["plan_start"]):
                    db.execute("DELETE FROM plan_progress WHERE group_id=?", (gid,))
            db.execute(
                "UPDATE study_groups SET name=?, about=?, area=?, plan=?, plan_start=? WHERE id=?",
                (name, _clean_text(fields.get("about", row["about"]), 500, multiline=True),
                 _clean_text(fields.get("area", row["area"]), 80), plan, start, gid))
        return self.group(user, gid)

    def reset_invite(self, user, gid):
        with self._tx() as db:
            self._require(db, gid, user["id"], "moderator",
                          "Only leaders and moderators can reset the invite link.")
            db.execute("UPDATE study_groups SET invite=? WHERE id=?", (_invite_code(), gid))
        return self.group(user, gid)

    def preview_invite(self, code):
        """What someone sees before joining: name, area, size. Nothing else."""
        if not isinstance(code, str) or not 6 <= len(code) <= 40:
            raise Problem(404, "That invite link doesn't work any more.")
        with self._db() as db:
            row = db.execute(
                "SELECT g.id, g.name, g.area, g.about, COUNT(m.user_id) AS members "
                "FROM study_groups g LEFT JOIN group_members m ON m.group_id = g.id "
                "WHERE g.invite=? GROUP BY g.id", (code,)).fetchone()
        if row is None:
            raise Problem(404, "That invite link doesn't work any more.")
        return dict(row)

    def join(self, user, code, ip):
        if not self.limits.allow(("join", ip), 30, 3600):
            raise Problem(429, "Too many attempts. Try again later.")
        preview = self.preview_invite(code)
        gid = preview["id"]
        with self._tx() as db:
            if db.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=?",
                          (gid, user["id"])).fetchone():
                pass  # already a member: joining twice is harmless
            else:
                self._check_group_cap(db, user["id"])
                n = db.execute("SELECT COUNT(*) FROM group_members WHERE group_id=?",
                               (gid,)).fetchone()[0]
                size = MAX_MEMBERS
                if self.billing is not None:  # a group is as big as its best-planned leader allows
                    leaders = [r[0] for r in db.execute(
                        "SELECT user_id FROM group_members WHERE group_id=? AND role='leader'", (gid,))]
                    size = max((self.billing.limits(u)["group_size"] for u in leaders), default=MAX_MEMBERS)
                if n >= size:
                    raise Problem(400, "This group is full.")
                last = db.execute("SELECT COALESCE(MAX(id), 0) FROM messages WHERE group_id=?",
                                  (gid,)).fetchone()[0]
                db.execute(
                    "INSERT INTO group_members (group_id, user_id, role, joined, last_read) "
                    "VALUES (?,?,?,?,?)", (gid, user["id"], "member", int(time.time()), last))
        return self.group(user, gid)

    def _leave(self, db, gid, uid):
        role = self._membership(db, gid, uid)
        db.execute("DELETE FROM group_members WHERE group_id=? AND user_id=?", (gid, uid))
        db.execute("DELETE FROM plan_progress WHERE group_id=? AND user_id=?", (gid, uid))
        if role == "leader":
            heir = db.execute(  # another leader, else the longest-serving moderator, else member
                "SELECT user_id FROM group_members WHERE group_id=? ORDER BY "
                "CASE role WHEN 'leader' THEN 0 WHEN 'moderator' THEN 1 ELSE 2 END, joined, user_id "
                "LIMIT 1", (gid,)).fetchone()
            if heir is None:
                db.execute("DELETE FROM study_groups WHERE id=?", (gid,))  # last one out
            else:
                db.execute("UPDATE group_members SET role='leader' WHERE group_id=? AND user_id=?",
                           (gid, heir[0]))

    def leave(self, user, gid):
        with self._tx() as db:
            self._leave(db, gid, user["id"])

    def remove_member(self, user, gid, target):
        if not isinstance(target, int) or target == user["id"]:
            raise Problem(400, "Pick someone else to remove.")
        with self._tx() as db:
            mine = self._require(db, gid, user["id"], "moderator",
                                 "Only leaders and moderators can remove people.")
            theirs = self._membership(db, gid, target)
            if ROLES[theirs] >= ROLES[mine]:
                raise Problem(403, "You can only remove people below you in the group."
                              if mine == "moderator" else "Make them a member first.")
            db.execute("DELETE FROM group_members WHERE group_id=? AND user_id=?", (gid, target))
            db.execute("DELETE FROM plan_progress WHERE group_id=? AND user_id=?", (gid, target))
        self.audit("member-removed", user["id"], group=gid, member=target)
        return self.group(user, gid)

    def set_role(self, user, gid, target, role, title=None):
        """Leaders only: make someone a leader, moderator or member, and/or
        give them a title. A group always keeps at least one leader."""
        if role not in ROLES or not isinstance(target, int):
            raise Problem(400, "Pick a member and a role.")
        with self._tx() as db:
            self._require(db, gid, user["id"], "leader", "Only a group leader can change roles.")
            current = self._membership(db, gid, target)
            if current == "leader" and role != "leader":
                n = db.execute("SELECT COUNT(*) FROM group_members WHERE group_id=? AND role='leader'",
                               (gid,)).fetchone()[0]
                if n <= 1:
                    raise Problem(400, "Make someone else a leader first.")
            title = _clean_text(title, TITLE_MAX) if title is not None else None
            if title is None:
                db.execute("UPDATE group_members SET role=? WHERE group_id=? AND user_id=?",
                           (role, gid, target))
            else:
                db.execute("UPDATE group_members SET role=?, title=? WHERE group_id=? AND user_id=?",
                           (role, title, gid, target))
        self.audit("role-changed", user["id"], group=gid, member=target, role=role)
        return self.group(user, gid)

    def make_leader(self, user, gid, target):
        return self.set_role(user, gid, target, "leader")

    def delete_group(self, user, gid):
        with self._tx() as db:
            self._require(db, gid, user["id"], "leader", "Only a group leader can delete the group.")
            db.execute("DELETE FROM study_groups WHERE id=?", (gid,))
        self.audit("group-deleted", user["id"], group=gid)

    def groups(self, user):
        with self._db() as db:
            rows = db.execute(
                "SELECT g.id, g.name, g.area, g.plan, g.plan_start, m.role, "
                "  (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) AS members, "
                "  (SELECT COUNT(*) FROM messages WHERE group_id = g.id AND id > m.last_read "
                "     AND user_id != m.user_id) AS unread, "
                "  (SELECT body FROM messages WHERE group_id = g.id ORDER BY id DESC LIMIT 1) AS last_body, "
                "  (SELECT u.name FROM messages x JOIN users u ON u.id = x.user_id "
                "     WHERE x.group_id = g.id ORDER BY x.id DESC LIMIT 1) AS last_name, "
                "  (SELECT created FROM messages WHERE group_id = g.id ORDER BY id DESC LIMIT 1) AS last_at "
                "FROM group_members m JOIN study_groups g ON g.id = m.group_id "
                "WHERE m.user_id=? ORDER BY COALESCE(last_at, g.created) DESC",
                (user["id"],)).fetchall()
        return [dict(r) for r in rows]

    def group(self, user, gid):
        with self._db() as db:
            role = self._membership(db, gid, user["id"])
            g = dict(db.execute("SELECT id, name, about, area, invite, plan, plan_start, created "
                                "FROM study_groups WHERE id=?", (gid,)).fetchone())
            members = db.execute(
                "SELECT u.id, u.name, u.username, u.avatar, m.role, m.title, m.joined, "
                "  (SELECT COUNT(*) FROM plan_progress p WHERE p.group_id = m.group_id "
                "     AND p.user_id = u.id) AS days_done "
                "FROM group_members m JOIN users u ON u.id = m.user_id WHERE m.group_id=? "
                "ORDER BY CASE m.role WHEN 'leader' THEN 0 WHEN 'moderator' THEN 1 ELSE 2 END, "
                "u.name COLLATE NOCASE", (gid,)).fetchall()
            days = [r[0] for r in db.execute(
                "SELECT day FROM plan_progress WHERE group_id=? AND user_id=? ORDER BY day",
                (gid, user["id"]))]
            counts = dict(db.execute(
                "SELECT day, COUNT(*) FROM plan_progress WHERE group_id=? GROUP BY day", (gid,)
            ).fetchall())
        g["role"] = role
        g["can"] = {"edit": role == "leader", "roles": role == "leader",
                    "moderate": ROLES[role] >= ROLES["moderator"]}
        g["members"] = [_member(m) for m in members]
        g["my_days"] = days
        g["day_counts"] = {str(k): v for k, v in counts.items()}
        return g

    def set_progress(self, user, gid, day, done):
        with self._tx() as db:
            self._membership(db, gid, user["id"])
            g = db.execute("SELECT plan FROM study_groups WHERE id=?", (gid,)).fetchone()
            plan = self.plans().get(g["plan"]) if g["plan"] else None
            if plan is None:
                raise Problem(400, "This group isn't following a reading plan.")
            if not isinstance(day, int) or not 1 <= day <= plan["length"]:
                raise Problem(400, "That day isn't in the plan.")
            if done:
                db.execute("INSERT OR IGNORE INTO plan_progress (group_id, user_id, day) VALUES (?,?,?)",
                           (gid, user["id"], day))
            else:
                db.execute("DELETE FROM plan_progress WHERE group_id=? AND user_id=? AND day=?",
                           (gid, user["id"], day))
        return self.group(user, gid)

    # ------------------------------------------------------------ messages

    def messages(self, user, gid, after=None, before=None):
        with self._db() as db:
            self._membership(db, gid, user["id"])
            cols = ("SELECT x.id, x.body, x.ref, x.created, u.id AS user_id, u.name, u.username, "
                    "u.avatar, (SELECT role FROM group_members gm WHERE gm.group_id = x.group_id "
                    "AND gm.user_id = u.id) AS role, (SELECT title FROM group_members gm "
                    "WHERE gm.group_id = x.group_id AND gm.user_id = u.id) AS title "
                    "FROM messages x JOIN users u ON u.id = x.user_id WHERE x.group_id=? ")
            cols += ("AND x.user_id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id=%d) "
                     % int(user["id"]))
            if after is not None:
                rows = db.execute(cols + "AND x.id > ? ORDER BY x.id LIMIT 200",
                                  (gid, after)).fetchall()
            elif before is not None:
                rows = db.execute(cols + "AND x.id < ? ORDER BY x.id DESC LIMIT ?",
                                  (gid, before, PAGE)).fetchall()[::-1]
            else:
                rows = db.execute(cols + "ORDER BY x.id DESC LIMIT ?", (gid, PAGE)).fetchall()[::-1]
        out = []
        for r in rows:
            m = dict(r)
            m["ref"] = json.loads(m["ref"]) if m["ref"] else None
            m["avatar"] = _media_url(m["avatar"])
            out.append(m)
        if out and before is None:
            with self._tx() as db:
                db.execute("UPDATE group_members SET last_read=MAX(last_read, ?) "
                           "WHERE group_id=? AND user_id=?", (out[-1]["id"], gid, user["id"]))
        return out

    def post(self, user, gid, body, ref=None):
        if not self.limits.allow(("post", user["id"]), 15, 60):
            raise Problem(429, "You're sending messages very quickly. Wait a moment.")
        body = _clean_text(body, MESSAGE_MAX, multiline=True)
        quoted = self._quote(ref) if ref else None
        if not body and not quoted:
            raise Problem(400, "Write a message first.")
        with self._tx() as db:
            self._membership(db, gid, user["id"])
            cur = db.execute(
                "INSERT INTO messages (group_id, user_id, body, ref, created) VALUES (?,?,?,?,?)",
                (gid, user["id"], body, json.dumps(quoted, ensure_ascii=False) if quoted else None,
                 int(time.time())))
            db.execute("UPDATE group_members SET last_read=? WHERE group_id=? AND user_id=?",
                       (cur.lastrowid, gid, user["id"]))
            mid = cur.lastrowid
        return {"id": mid, "body": body, "ref": quoted, "created": int(time.time()),
                "user_id": user["id"], "name": user["name"], "username": user["username"],
                "avatar": user.get("avatar")}

    def _quote(self, ref):
        """A verse shared into chat is looked up here, so what the group
        sees is the library's text, not whatever the sender typed."""
        if not isinstance(ref, dict):
            raise Problem(400, "That verse reference isn't valid.")
        t, b, c, v = ref.get("t"), ref.get("b"), ref.get("c"), ref.get("v")
        v2 = ref.get("v2", v)
        if not (isinstance(t, str) and isinstance(b, str) and all(isinstance(x, int) for x in (c, v, v2))):
            raise Problem(400, "That verse reference isn't valid.")
        if v2 < v or v2 - v > 9:
            raise Problem(400, "Share up to 10 verses at a time.")
        verses = self.verses(t, b, c, v, v2)
        if not verses:
            raise Problem(400, "That verse isn't in this translation.")
        return {"t": t, "b": b, "c": c, "v": verses[0][0], "v2": verses[-1][0],
                "text": " ".join(x[1] for x in verses)}

    def delete_message(self, user, gid, mid):
        with self._tx() as db:
            role = self._membership(db, gid, user["id"])
            row = db.execute("SELECT user_id FROM messages WHERE id=? AND group_id=?",
                             (mid, gid)).fetchone()
            if row is None:
                raise Problem(404, "Message not found.")
            if row["user_id"] != user["id"] and ROLES[role] < ROLES["moderator"]:
                raise Problem(403, "You can only delete your own messages.")
            db.execute("DELETE FROM messages WHERE id=?", (mid,))

    # ------------------------------------------------------------- friends

    def _user_by_name(self, db, username):
        row = db.execute("SELECT id, username, name, avatar FROM users WHERE username=?",
                         (str(username or "").strip().lower().lstrip("@"),)).fetchone()
        if row is None:
            raise Problem(404, "There's no one with that username.")
        return row

    @staticmethod
    def _relationship(db, me, other):
        if me == other:
            return "self"
        a, b = sorted((me, other))
        row = db.execute("SELECT requester, status FROM friendships WHERE a=? AND b=?", (a, b)).fetchone()
        if row is None:
            return "none"
        if row["status"] == "accepted":
            return "friends"
        return "outgoing" if row["requester"] == me else "incoming"

    def friend_request(self, user, username):
        if not self.limits.allow(("friend", user["id"]), 50, 86400):
            raise Problem(429, "That's a lot of friend requests for one day.")
        with self._tx() as db:
            other = self._user_by_name(db, username)
            rel = self._relationship(db, user["id"], other["id"])
            if rel == "self":
                raise Problem(400, "That's you!")
            if db.execute("SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) "
                          "OR (blocker_id=? AND blocked_id=?)",
                          (user["id"], other["id"], other["id"], user["id"])).fetchone():
                raise Problem(403, "You can't send a friend request to this person.")
            if rel in ("friends", "outgoing"):
                return rel
            a, b = sorted((user["id"], other["id"]))
            if rel == "incoming":  # they already asked: asking back is accepting
                db.execute("UPDATE friendships SET status='accepted' WHERE a=? AND b=?", (a, b))
                return "friends"
            n = db.execute("SELECT COUNT(*) FROM friendships WHERE (a=? OR b=?)",
                           (user["id"], user["id"])).fetchone()[0]
            if n >= MAX_FRIENDS:
                raise Problem(400, f"You can have at most {MAX_FRIENDS} friends and requests.")
            db.execute("INSERT INTO friendships (a, b, requester, status, created) VALUES (?,?,?,?,?)",
                       (a, b, user["id"], "pending", int(time.time())))
        return "outgoing"

    def friend_accept(self, user, other_id):
        if not isinstance(other_id, int):
            raise Problem(400, "Pick a request to accept.")
        a, b = sorted((user["id"], other_id))
        with self._tx() as db:
            cur = db.execute("UPDATE friendships SET status='accepted' WHERE a=? AND b=? "
                             "AND status='pending' AND requester=?", (a, b, other_id))
            if not cur.rowcount:
                raise Problem(404, "That request isn't there any more.")
        return "friends"

    def friend_remove(self, user, other_id):
        """Unfriend, decline a request, or cancel one you sent."""
        if not isinstance(other_id, int):
            raise Problem(400, "Pick someone.")
        a, b = sorted((user["id"], other_id))
        with self._tx() as db:
            db.execute("DELETE FROM friendships WHERE a=? AND b=?", (a, b))
        return "none"

    def friends(self, user):
        uid = user["id"]
        with self._db() as db:
            rows = db.execute(
                "SELECT u.id, u.username, u.name, u.avatar, f.status, f.requester, f.created "
                "FROM friendships f JOIN users u ON u.id = CASE WHEN f.a=? THEN f.b ELSE f.a END "
                "WHERE f.a=? OR f.b=? ORDER BY u.name COLLATE NOCASE", (uid, uid, uid)).fetchall()
        out = {"friends": [], "incoming": [], "outgoing": []}
        for r in rows:
            key = "friends" if r["status"] == "accepted" else (
                "outgoing" if r["requester"] == uid else "incoming")
            out[key].append(_person(r))
        return out

    # ----------------------------------------------------------------- sync

    SYNC_KINDS = {"journal", "hl", "bm", "plan"}
    SYNC_VALUE_MAX = 64 * 1024
    SYNC_TOTAL_MAX = 25 * 1024 * 1024

    def sync(self, user, since, changes):
        """Two-way sync of personal data, newest edit wins per item. Journal
        entries arrive already encrypted on the device (AES-GCM, key from the
        password), so this stores only ciphertext for them. Returns the
        changes after `since` and a new cursor."""
        if not isinstance(changes, list) or len(changes) > 500:
            raise Problem(400, "Send up to 500 changes at a time.")
        since = since if isinstance(since, int) and since >= 0 else 0
        with self._tx() as db:
            seq = db.execute("SELECT COALESCE(MAX(seq), 0) FROM user_data WHERE user_id=?",
                             (user["id"],)).fetchone()[0]
            used = db.execute("SELECT COALESCE(SUM(LENGTH(value)), 0) FROM user_data WHERE user_id=?",
                              (user["id"],)).fetchone()[0]
            for ch in changes:
                if not isinstance(ch, dict) or ch.get("kind") not in self.SYNC_KINDS:
                    raise Problem(400, "That change isn't something we sync.")
                key, value, updated = ch.get("key"), ch.get("value"), ch.get("updated")
                if not isinstance(key, str) or not 0 < len(key) <= 120 or not isinstance(updated, int):
                    raise Problem(400, "That change is missing its key or time.")
                value = None if value is None else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                if value is not None and len(value) > self.SYNC_VALUE_MAX:
                    raise Problem(413, "One item is too large to sync.")
                used += len(value or "")
                if used > self.SYNC_TOTAL_MAX:
                    raise Problem(413, "Your backup is full (25 MB).")
                row = db.execute("SELECT updated FROM user_data WHERE user_id=? AND kind=? AND key=?",
                                 (user["id"], ch["kind"], key)).fetchone()
                if row is not None and row["updated"] >= updated:
                    continue  # we already have something newer
                seq += 1
                db.execute("INSERT INTO user_data (user_id, kind, key, value, updated, seq) VALUES (?,?,?,?,?,?) "
                           "ON CONFLICT(user_id, kind, key) DO UPDATE SET value=excluded.value, "
                           "updated=excluded.updated, seq=excluded.seq",
                           (user["id"], ch["kind"], key, value, updated, seq))
            rows = db.execute("SELECT kind, key, value, updated, seq FROM user_data WHERE user_id=? AND seq>? "
                              "ORDER BY seq LIMIT 2000", (user["id"], since)).fetchall()
        out = [{"kind": r["kind"], "key": r["key"], "updated": r["updated"],
                "value": json.loads(r["value"]) if r["value"] is not None else None} for r in rows]
        return {"cursor": rows[-1]["seq"] if rows else max(since, 0), "changes": out,
                "more": len(rows) == 2000}

    def sync_reset(self, user, kind):
        """Forget synced items of one kind (e.g. journal ciphertext that can no
        longer be read after an admin password reset)."""
        if kind not in self.SYNC_KINDS:
            raise Problem(400, "Unknown kind.")
        with self._tx() as db:
            db.execute("DELETE FROM user_data WHERE user_id=? AND kind=?", (user["id"], kind))

    # --------------------------------------------------------------- safety

    def report(self, user, kind, target, reason, detail=""):
        """Anyone signed in can report a message, person, song or artist.
        A copy of what was reported is kept, so deleting it doesn't erase
        the evidence an admin needs."""
        if kind not in ("message", "user", "song", "artist") or not isinstance(target, int):
            raise Problem(400, "Pick what you're reporting.")
        if reason not in REPORT_REASONS:
            raise Problem(400, "Pick a reason.")
        if not self.limits.allow(("report", user["id"]), 30, 86400):
            raise Problem(429, "That's a lot of reports today. Thank you; try again tomorrow.")
        with self._db() as db:
            q = {"message": "SELECT x.body, x.ref, u.username FROM messages x JOIN users u ON u.id = x.user_id "
                            "WHERE x.id=? AND x.group_id IN (SELECT group_id FROM group_members WHERE user_id=%d)"
                            % int(user["id"]),
                 "user": "SELECT username, name, bio FROM users WHERE id=?",
                 "song": "SELECT s.title, a.name FROM songs s JOIN artists a ON a.id = s.artist_id WHERE s.id=?",
                 "artist": "SELECT name, bio FROM artists WHERE id=?"}[kind]
            row = db.execute(q, (target,)).fetchone()
        if row is None:
            raise Problem(404, "That isn't there any more.")
        snapshot = json.dumps(dict(row), ensure_ascii=False)[:2000]
        with self._tx() as db:
            db.execute("INSERT INTO reports (reporter_id, kind, target_id, reason, detail, snapshot, created) "
                       "VALUES (?,?,?,?,?,?,?)", (user["id"], kind, target, reason,
                                                  _clean_text(detail, 1000, multiline=True), snapshot,
                                                  int(time.time())))
        self.audit("report", user["id"], kind=kind, target=target, reason=reason)

    def block(self, user, other_id, on=True):
        if not isinstance(other_id, int) or other_id == user["id"]:
            raise Problem(400, "Pick someone else.")
        with self._tx() as db:
            if on:
                db.execute("INSERT OR IGNORE INTO blocks (blocker_id, blocked_id, created) VALUES (?,?,?)",
                           (user["id"], other_id, int(time.time())))
                a, b = sorted((user["id"], other_id))
                db.execute("DELETE FROM friendships WHERE a=? AND b=?", (a, b))
            else:
                db.execute("DELETE FROM blocks WHERE blocker_id=? AND blocked_id=?", (user["id"], other_id))
        self.audit("block" if on else "unblock", user["id"], other=other_id)

    def blocked(self, user):
        with self._db() as db:
            rows = db.execute("SELECT u.id, u.username, u.name, u.avatar FROM blocks b "
                              "JOIN users u ON u.id = b.blocked_id WHERE b.blocker_id=? ORDER BY u.name",
                              (user["id"],)).fetchall()
        return [_person(r) for r in rows]

    def reports_open(self, admin):
        self._require_admin(admin)
        with self._db() as db:
            rows = db.execute("SELECT r.*, u.username AS reporter FROM reports r "
                              "LEFT JOIN users u ON u.id = r.reporter_id WHERE r.status='open' "
                              "ORDER BY r.created").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["snapshot"] = json.loads(d["snapshot"] or "{}")
            out.append(d)
        return out

    def resolve_report(self, admin, rid, action):
        """dismiss, or act: delete the message / suspend the person (songs and
        artists are removed through the music admin)."""
        self._require_admin(admin)
        with self._tx() as db:
            r = db.execute("SELECT kind, target_id FROM reports WHERE id=?", (rid,)).fetchone()
            if r is None:
                raise Problem(404, "Report not found.")
            if action == "delete-message" and r["kind"] == "message":
                db.execute("DELETE FROM messages WHERE id=?", (r["target_id"],))
            elif action == "suspend-user":
                uid = r["target_id"] if r["kind"] == "user" else (db.execute(
                    "SELECT user_id FROM messages WHERE id=?", (r["target_id"],)).fetchone() or [None])[0]
                if uid is None:
                    raise Problem(400, "Nobody to suspend.")
                db.execute("UPDATE users SET suspended=1 WHERE id=? AND is_admin=0", (uid,))
                db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            elif action not in ("dismiss", "actioned"):
                raise Problem(400, "Unknown action.")
            db.execute("UPDATE reports SET status=?, resolved=? WHERE id=?",
                       ("dismissed" if action == "dismiss" else "actioned", int(time.time()), rid))
        self.audit(f"report-{action}", admin["id"], report=rid)

    def _require_admin(self, user):
        if not user.get("is_admin"):
            raise Problem(403, "Admins only.")
        self.require_verified(user)

    # ------------------------------------------------------------- profiles

    def profile(self, viewer, username):
        with self._db() as db:
            row = db.execute("SELECT id, username, name, avatar, bio, verse, show_progress, created "
                             "FROM users WHERE username=?",
                             (str(username or "").strip().lower().lstrip("@"),)).fetchone()
            if row is None:
                raise Problem(404, "There's no one with that username.")
            uid = row["id"]
            rel = self._relationship(db, viewer["id"], uid)
            friends = db.execute("SELECT COUNT(*) FROM friendships WHERE (a=? OR b=?) "
                                 "AND status='accepted'", (uid, uid)).fetchone()[0]
            groups = db.execute("SELECT COUNT(*) FROM group_members WHERE user_id=?",
                                (uid,)).fetchone()[0]
            shared = [r[0] for r in db.execute(
                "SELECT g.name FROM study_groups g JOIN group_members a ON a.group_id = g.id "
                "JOIN group_members b ON b.group_id = g.id WHERE a.user_id=? AND b.user_id=? "
                "ORDER BY g.name", (viewer["id"], uid))] if rel != "self" else []
        out = _person(row)
        out.update({"bio": row["bio"], "joined": row["created"], "relationship": rel,
                    "friends": friends, "groups": groups, "shared_groups": shared,
                    "show_progress": bool(row["show_progress"]), "verse": None, "progress": None})
        if row["verse"]:
            ref = json.loads(row["verse"])
            try:
                quoted = self._quote(ref)
            except Problem:
                quoted = None  # the translation went away: just skip it
            out["verse"] = quoted
        if row["show_progress"] or rel == "self":
            out["progress"] = self.progress_summary(uid)
            r = self.rewards(uid)
            out["rewards"] = {k: r[k] for k in ("points", "level", "title", "earned")}
            out["rewards"]["badges"] = [b for b in r["badges"] if b["earned"]]
        return out

    def rewards(self, uid):
        with self._db() as db:
            return gift_rewards.rewards(db, uid)

    def update_profile(self, user, fields):
        sets, args, old_avatar = [], [], None
        if "name" in fields:
            name = _clean_text(fields.get("name"), 40)
            if not name:
                raise Problem(400, "Your name can't be empty.")
            sets.append("name=?"), args.append(name)
        if "bio" in fields:
            sets.append("bio=?"), args.append(_clean_text(fields.get("bio"), BIO_MAX, multiline=True))
        if "verse" in fields:
            v = fields.get("verse")
            if v:
                q = self._quote({**v, "v2": v.get("v")} if isinstance(v, dict) else v)
                v = json.dumps({"t": q["t"], "b": q["b"], "c": q["c"], "v": q["v"]})
            sets.append("verse=?"), args.append(v or None)
        if "show_progress" in fields:
            sets.append("show_progress=?"), args.append(1 if fields.get("show_progress") else 0)
        with self._tx() as db:
            if "avatar" in fields:
                new = fields.get("avatar")
                old_avatar = db.execute("SELECT avatar FROM users WHERE id=?",
                                        (user["id"],)).fetchone()[0]
                if new:
                    self._claim_media(db, user["id"], new, "image")
                sets.append("avatar=?"), args.append(new or None)
            if sets:
                db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*args, user["id"]))
            if old_avatar and old_avatar != fields.get("avatar"):
                self._drop_media(db, old_avatar)
        return self.user(user["id"])

    def rename(self, user, name):
        return self.update_profile(user, {"name": name})

    # ------------------------------------------------------- bible progress

    def mark_chapters(self, user, items, done=True, day=None):
        """Mark Bible chapters read (or unread). `items` is [[book, chapter]];
        `day` is the reader's own date, so streaks follow their midnight."""
        if not isinstance(items, list) or not 1 <= len(items) <= CANON_CHAPTERS:
            raise Problem(400, "Send a list of chapters.")
        rows = []
        for it in items:
            if (not isinstance(it, list) or len(it) != 2 or not isinstance(it[1], int)
                    or (it[0], it[1]) not in SLOTS):
                raise Problem(400, "That isn't a chapter of the Bible.")
            rows.append((it[0], it[1]))
        if not (isinstance(day, str) and DATE_RE.fullmatch(day)):
            day = date.today().isoformat()
        with self._tx() as db:
            if done:
                db.executemany("INSERT OR IGNORE INTO chapters_read (user_id, book, chapter, day) "
                               "VALUES (?,?,?,?)", [(user["id"], b, c, day) for b, c in rows])
            else:
                db.executemany("DELETE FROM chapters_read WHERE user_id=? AND book=? AND chapter=?",
                               [(user["id"], b, c) for b, c in rows])
        return self.progress_summary(user["id"], full=True)

    def progress_summary(self, uid, full=False):
        with self._db() as db:
            rows = db.execute("SELECT book, chapter, day FROM chapters_read WHERE user_id=?",
                              (uid,)).fetchall()
        by_book = {}
        for r in rows:
            by_book.setdefault(r["book"], []).append(r["chapter"])
        nt_books = set(b for (b, _), slot in SLOTS.items() if slot[0] == "nt")
        nt_total = sum(1 for slot in SLOTS.values() if slot[0] == "nt")
        nt = sum(len(v) for b, v in by_book.items() if b in nt_books)
        out = {"read": len(rows), "total": CANON_CHAPTERS, "ot": len(rows) - nt,
               "ot_total": CANON_CHAPTERS - nt_total, "nt": nt, "nt_total": nt_total,
               "books_done": sum(1 for b, v in by_book.items()
                                 if len(v) == sum(1 for (bb, _) in SLOTS if bb == b)),
               "streak": _streak({r["day"] for r in rows})}
        if full:
            out["chapters"] = {b: sorted(v) for b, v in by_book.items()}
        return out

    # ---------------------------------------------------------------- media

    def add_media(self, user, tmp_path, size):
        """Keep an uploaded file (already on disk at tmp_path) if it is a
        format we serve. It stays unclaimed until a profile, artist or song
        uses it; unclaimed uploads are swept after a day."""
        try:
            with open(tmp_path, "rb") as f:
                kind = gift_media.sniff(f.read(64))
            if kind is None:
                raise Problem(415, "That file type isn't supported. Use JPEG, PNG or WebP for "
                                   "pictures and MP3, M4A, Ogg, WAV or FLAC for music.")
            if size > gift_media.LIMITS[kind[0]]:
                raise Problem(413, "That file is too big." if kind[0] == "audio"
                              else "That picture is too big.")
            if not self.limits.allow(("upload", user["id"]), 60, 3600):
                raise Problem(429, "That's a lot of uploads. Try again in a while.")
            mid = gift_media.new_id()
            os.replace(tmp_path, gift_media.media_dir(self.data_dir) / f"{mid}{kind[2]}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        now = int(time.time())
        with self._tx() as db:
            db.execute("INSERT INTO media (id, owner_id, kind, mime, ext, size, created) "
                       "VALUES (?,?,?,?,?,?,?)", (mid, user["id"], kind[0], kind[1], kind[2], size, now))
            stale = db.execute("SELECT id FROM media WHERE owner_id=? AND used=0 AND created<?",
                               (user["id"], now - 86400)).fetchall()
            for r in stale:
                self._drop_media(db, r["id"])
        return {"id": mid, "kind": kind[0], "url": _media_url(mid)}

    def media_file(self, mid):
        if not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{10,40}", mid):
            return None
        with self._db() as db:
            row = db.execute("SELECT id, mime, ext, size FROM media WHERE id=?", (mid,)).fetchone()
        if row is None:
            return None
        return gift_media.media_dir(self.data_dir) / f"{row['id']}{row['ext']}", row["mime"]

    def _claim_media(self, db, uid, mid, kind):
        row = db.execute("SELECT owner_id, kind FROM media WHERE id=?", (str(mid),)).fetchone()
        if row is None or row["owner_id"] != uid or row["kind"] != kind:
            raise Problem(400, "Upload the file again, then save.")
        db.execute("UPDATE media SET used=1 WHERE id=?", (mid,))

    def _drop_media(self, db, mid):
        row = db.execute("SELECT ext FROM media WHERE id=?", (mid,)).fetchone()
        if row is not None:
            db.execute("DELETE FROM media WHERE id=?", (mid,))
            gift_media.remove(self.data_dir, mid, row["ext"])


def _media_url(mid):
    return f"/media/{mid}" if mid else None


def _person(row, admin=False):
    """The public face of an account: what other people may see."""
    out = {"id": row["id"], "username": row["username"], "name": row["name"],
           "avatar": _media_url(row["avatar"])}
    if admin:
        out["is_admin"] = bool(row["is_admin"])
    return out


def _member(row):
    out = _person(row)
    out.update({"role": row["role"], "title": row["title"], "joined": row["joined"],
                "days_done": row["days_done"]})
    return out


def _streak(days, today=None):
    """Consecutive days with reading, ending today or yesterday."""
    today = today or date.today()
    d = today if today.isoformat() in days else today - timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= timedelta(days=1)
    return n


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).digest()


def _invite_code():
    return secrets.token_urlsafe(9)


class _Conn:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        self.db.close()


class _Tx:
    def __init__(self, community):
        self.c = community

    def __enter__(self):
        self.c._write.acquire()
        self.conn = self.c._db()
        self.db = self.conn.db
        self.db.execute("BEGIN IMMEDIATE")
        return self.db

    def __exit__(self, exc_type, *exc):
        try:
            self.db.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self.db.close()
            self.c._write.release()


if __name__ == "__main__":
    # python3 gift_community.py reset-password|make-admin|remove-admin <username>
    #                          grant <username> plus|premium|church <days>
    usage = ("usage: python3 gift_community.py reset-password|make-admin|remove-admin <username>\n"
             "       python3 gift_community.py grant <username> plus|premium|church <days>")
    if len(sys.argv) == 5 and sys.argv[1] == "grant":
        import gift_billing
        data = Path(os.environ.get("GIFT_DATA_DIR") or Path(__file__).resolve().parent / ".data")
        try:
            gift_billing.Billing(Community(data / "community.sqlite3")).grant(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        except (Problem, ValueError) as e:
            sys.exit(getattr(e, "message", str(e)))
        print(f"{sys.argv[2]} has {sys.argv[3]} for {sys.argv[4]} days.")
        sys.exit(0)
    if len(sys.argv) != 3 or sys.argv[1] not in ("reset-password", "make-admin", "remove-admin"):
        sys.exit(usage)
    data = Path(os.environ.get("GIFT_DATA_DIR") or Path(__file__).resolve().parent / ".data")
    db_file = data / "community.sqlite3"
    if not db_file.exists():
        sys.exit(f"no database at {db_file} (set GIFT_DATA_DIR)")
    command, username = sys.argv[1], sys.argv[2]
    try:
        c = Community(db_file)
        if command == "reset-password":
            temp = c.reset_password(username)
            print(f"Temporary password for {username}: {temp}")
            print("They should sign in with it, then change it under Settings → Account.")
        else:
            c.set_admin(username, command == "make-admin")
            print(f"{username} is {'now' if command == 'make-admin' else 'no longer'} an admin "
                  "(approves artists and songs in the app's Admin page).")
    except Problem as p:
        sys.exit(p.message)
