"""
The Gift — music: public-domain hymns, and artists' own songs.

Hymns ship with the library (Music/Hymns/hymns.json plus their recordings);
every text and recording there is public domain or openly licensed, and
each one carries its credit.

Artists apply from the app; nothing about them is public until an admin
approves the application. An approved artist uploads songs they own the
rights to, and each song is also held until an admin approves it. Artists
can link out to their pages on streaming services (only those services'
own addresses are accepted). Admins are set from the command line
(gift_community.py make-admin).

Storage is the community database (artists and songs tables) plus the
media/ folder for photos and audio; see gift_community and gift_media.
"""

import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from gift_community import Problem, _clean_text, _media_url

HYMNS = Path("Music/Hymns/hymns.json")
MAX_SONGS = 100  # per artist

# where an artist may link to, and the hosts each link must really be on
LINKS = {
    "spotify": ("open.spotify.com",),
    "apple": ("music.apple.com",),
    "youtube": ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"),
    "bandcamp": ("bandcamp.com",),  # and any *.bandcamp.com
    "soundcloud": ("soundcloud.com", "on.soundcloud.com", "m.soundcloud.com"),
    "website": None,  # any https address
}


def clean_links(links):
    if not isinstance(links, dict):
        return {}
    out = {}
    for key, url in links.items():
        if key not in LINKS or not isinstance(url, str) or not url.strip():
            continue
        url = url.strip()[:300]
        if "://" not in url:
            url = "https://" + url
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or not host or " " in url:
            raise Problem(400, f"The {key} link must be an https:// address.")
        hosts = LINKS[key]
        if hosts and host not in hosts and not (key == "bandcamp" and host.endswith(".bandcamp.com")):
            raise Problem(400, f"That doesn't look like a {key.title()} link.")
        out[key] = url
    return out


def _artist(row, songs=None, private=False):
    out = {"id": row["id"], "name": row["name"], "genre": row["genre"], "bio": row["bio"],
           "links": json.loads(row["links"] or "{}"), "photo": _media_url(row["photo"]),
           "featured": bool(row["featured"])}
    if private:
        out.update({"status": row["status"], "note": row["note"], "user_id": row["user_id"],
                    "created": row["created"]})
    if songs is not None:
        out["songs"] = songs
    return out


def _song(row, private=False):
    out = {"id": row["id"], "title": row["title"], "url": _media_url(row["media"]),
           "lyrics": row["lyrics"], "plays": row["plays"], "created": row["created"],
           "artist_id": row["artist_id"]}
    if "artist_name" in row.keys():
        out["artist"] = row["artist_name"]
        out["photo"] = _media_url(row["artist_photo"])
    if private:
        out.update({"status": row["status"], "note": row["note"]})
    return out


class Music:
    def __init__(self, community, root):
        self.c = community
        self.root = Path(root)
        self._hymns = (None, [])

    # ---------------------------------------------------------------- hymns

    def hymns(self):
        p = self.root / HYMNS
        try:
            st = p.stat()
        except OSError:
            return []
        stamp = (st.st_mtime_ns, st.st_size)
        if self._hymns[0] != stamp:
            self._hymns = (stamp, json.loads(p.read_text("utf-8")).get("hymns", []))
        return self._hymns[1]

    def hymn_list(self):
        return [{k: h.get(k) for k in ("id", "title", "author", "year", "theme")}
                | {"audio": bool(h.get("audio"))} for h in self.hymns()]

    def hymn(self, hid):
        for h in self.hymns():
            if h.get("id") == hid:
                out = dict(h)
                if h.get("audio"):
                    out["audio"] = dict(h["audio"], url="/" + (HYMNS.parent / h["audio"]["file"]).as_posix())
                return out
        raise Problem(404, "Hymn not found.")

    # --------------------------------------------------------------- public

    def overview(self):
        with self.c._db() as db:
            artists = db.execute("SELECT * FROM artists WHERE status='approved' "
                                 "ORDER BY name COLLATE NOCASE").fetchall()
            songs = db.execute(
                "SELECT s.*, a.name AS artist_name, a.photo AS artist_photo FROM songs s "
                "JOIN artists a ON a.id = s.artist_id WHERE s.status='approved' AND a.status='approved' "
                "ORDER BY s.reviewed DESC, s.id DESC LIMIT 20").fetchall()
        all_artists = [_artist(a) for a in artists]
        return {"featured": [a for a in all_artists if a["featured"]],
                "artists": all_artists,
                "songs": [_song(s) for s in songs],
                "hymns": self.hymn_list()}

    def artist(self, viewer, aid):
        with self.c._db() as db:
            row = db.execute("SELECT * FROM artists WHERE id=?", (aid,)).fetchone()
            if row is None:
                raise Problem(404, "Artist not found.")
            mine = viewer is not None and (viewer["id"] == row["user_id"] or viewer.get("is_admin"))
            if row["status"] != "approved" and not mine:
                raise Problem(404, "Artist not found.")
            songs = db.execute(
                "SELECT s.*, a.name AS artist_name, a.photo AS artist_photo FROM songs s "
                "JOIN artists a ON a.id = s.artist_id WHERE s.artist_id=? "
                + ("" if mine else "AND s.status='approved' ") + "ORDER BY s.id DESC", (aid,)).fetchall()
        return _artist(row, [_song(s, private=mine) for s in songs], private=mine)

    def artist_of(self, uid):
        """The approved artist profile behind an account, for its profile page."""
        with self.c._db() as db:
            row = db.execute("SELECT id, name FROM artists WHERE user_id=? AND status='approved'",
                             (uid,)).fetchone()
        return dict(row) if row else None

    def played(self, sid, ip):
        if not self.c.limits.allow(("play", ip, sid), 1, 1800):
            return  # one play per listener per half hour counts
        with self.c._tx() as db:
            db.execute("UPDATE songs SET plays = plays + 1 WHERE id=? AND status='approved'", (sid,))

    # --------------------------------------------------------------- artist

    def studio(self, user):
        with self.c._db() as db:
            row = db.execute("SELECT id FROM artists WHERE user_id=?", (user["id"],)).fetchone()
        return {"artist": self.artist(user, row["id"]) if row else None}

    def apply(self, user, fields):
        """Apply to be an artist, or edit an application or approved profile.
        A rejected application goes back to pending when resubmitted."""
        name = _clean_text(fields.get("name"), 60)
        if not name:
            raise Problem(400, "What name do you release music under?")
        genre = _clean_text(fields.get("genre"), 40)
        bio = _clean_text(fields.get("bio"), 1500, multiline=True)
        links = json.dumps(clean_links(fields.get("links")))
        photo = fields.get("photo") or None
        now = int(time.time())
        with self.c._tx() as db:
            row = db.execute("SELECT * FROM artists WHERE user_id=?", (user["id"],)).fetchone()
            if photo and (row is None or photo != row["photo"]):
                self.c._claim_media(db, user["id"], photo, "image")
            if row is None:
                if not self.c.limits.allow(("apply", user["id"]), 5, 86400):
                    raise Problem(429, "Try again tomorrow.")
                db.execute("INSERT INTO artists (user_id, name, genre, bio, links, photo, status, created) "
                           "VALUES (?,?,?,?,?,?,?,?)",
                           (user["id"], name, genre, bio, links, photo, "pending", now))
            else:
                status = "pending" if row["status"] == "rejected" else row["status"]
                db.execute("UPDATE artists SET name=?, genre=?, bio=?, links=?, photo=?, status=? "
                           "WHERE id=?", (name, genre, bio, links, photo, status, row["id"]))
                if row["photo"] and row["photo"] != photo:
                    self.c._drop_media(db, row["photo"])
        return self.studio(user)

    def add_song(self, user, fields):
        title = _clean_text(fields.get("title"), 100)
        if not title:
            raise Problem(400, "Give the song a title.")
        if fields.get("rights") is not True:
            raise Problem(400, "Confirm you own or have permission to share this recording.")
        media = fields.get("media")
        with self.c._tx() as db:
            artist = db.execute("SELECT id, status FROM artists WHERE user_id=?", (user["id"],)).fetchone()
            if artist is None or artist["status"] != "approved":
                raise Problem(403, "Songs can be added once your artist profile is approved.")
            n = db.execute("SELECT COUNT(*) FROM songs WHERE artist_id=?", (artist["id"],)).fetchone()[0]
            cap = self.c.billing.limits(user["id"])["songs"] if self.c.billing else MAX_SONGS
            if n >= cap:
                raise Problem(402, f"Your plan holds {cap} songs." + (" Premium holds 100." if cap < MAX_SONGS else ""))
            self.c._claim_media(db, user["id"], media, "audio")
            db.execute("INSERT INTO songs (artist_id, title, media, lyrics, status, created) "
                       "VALUES (?,?,?,?,?,?)",
                       (artist["id"], title, media, _clean_text(fields.get("lyrics"), 5000, multiline=True),
                        "pending", int(time.time())))
        return self.studio(user)

    def delete_song(self, user, sid):
        with self.c._tx() as db:
            row = db.execute("SELECT s.media, a.user_id FROM songs s JOIN artists a ON a.id = s.artist_id "
                             "WHERE s.id=?", (sid,)).fetchone()
            if row is None:
                raise Problem(404, "Song not found.")
            if row["user_id"] != user["id"] and not user.get("is_admin"):
                raise Problem(403, "That isn't your song.")
            db.execute("DELETE FROM songs WHERE id=?", (sid,))
            self.c._drop_media(db, row["media"])

    # ---------------------------------------------------------------- admin

    def _admin(self, user):
        """Admins only, and only with a recently typed password (step-up)."""
        if not user.get("is_admin"):
            raise Problem(403, "Admins only.")
        self.c.require_verified(user)

    def queue(self, user):
        self._admin(user)
        with self.c._db() as db:
            pending = db.execute("SELECT a.*, u.username FROM artists a JOIN users u ON u.id = a.user_id "
                                 "WHERE a.status='pending' ORDER BY a.created").fetchall()
            songs = db.execute(
                "SELECT s.*, a.name AS artist_name, a.photo AS artist_photo FROM songs s "
                "JOIN artists a ON a.id = s.artist_id WHERE s.status='pending' ORDER BY s.created").fetchall()
            approved = db.execute("SELECT * FROM artists WHERE status='approved' "
                                  "ORDER BY featured DESC, name COLLATE NOCASE").fetchall()
            counts = db.execute("SELECT (SELECT COUNT(*) FROM users), (SELECT COUNT(*) FROM study_groups), "
                                "(SELECT COUNT(*) FROM songs WHERE status='approved')").fetchone()

        def with_user(r):
            a = _artist(r, private=True)
            a["username"] = r["username"]
            return a
        return {"artists": [with_user(r) for r in pending],
                "songs": [_song(s, private=True) for s in songs],
                "approved": [_artist(r, private=True) for r in approved],
                "stats": {"users": counts[0], "groups": counts[1], "songs": counts[2]}}

    def review_artist(self, user, aid, action, note=""):
        self._admin(user)
        note = _clean_text(note, 300)
        with self.c._tx() as db:
            row = db.execute("SELECT id, photo FROM artists WHERE id=?", (aid,)).fetchone()
            if row is None:
                raise Problem(404, "Artist not found.")
            now = int(time.time())
            if action == "approve":
                db.execute("UPDATE artists SET status='approved', note=?, reviewed=? WHERE id=?", (note, now, aid))
            elif action == "reject":
                db.execute("UPDATE artists SET status='rejected', featured=0, note=?, reviewed=? WHERE id=?",
                           (note, now, aid))
            elif action in ("feature", "unfeature"):  # noqa: same transaction
                db.execute("UPDATE artists SET featured=? WHERE id=? AND status='approved'",
                           (1 if action == "feature" else 0, aid))
            elif action == "remove":
                for s in db.execute("SELECT media FROM songs WHERE artist_id=?", (aid,)).fetchall():
                    self.c._drop_media(db, s["media"])
                db.execute("DELETE FROM artists WHERE id=?", (aid,))
                if row["photo"]:
                    self.c._drop_media(db, row["photo"])
            else:
                raise Problem(400, "Unknown action.")
        self.c.audit(f"artist-{action}", user["id"], artist=aid)
        return self.queue(user)

    def review_song(self, user, sid, action, note=""):
        self._admin(user)
        if action == "remove":
            self.delete_song(user, sid)
            return self.queue(user)
        if action not in ("approve", "reject"):
            raise Problem(400, "Unknown action.")
        with self.c._tx() as db:
            cur = db.execute("UPDATE songs SET status=?, note=?, reviewed=? WHERE id=?",
                             ("approved" if action == "approve" else "rejected",
                              _clean_text(note, 300), int(time.time()), sid))
            if not cur.rowcount:
                raise Problem(404, "Song not found.")
        self.c.audit(f"song-{action}", user["id"], song=sid)
        return self.queue(user)
