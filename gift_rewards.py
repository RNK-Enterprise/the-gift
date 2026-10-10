"""
The Gift — rewards: badges, points and levels.

Nothing here is stored or claimed by the browser. Every badge is worked out
on the server, each time, from what the database already records: chapters
read, the days they were read on, group membership and roles, friendships,
messages and verses shared, group plan days, and approved artist profiles.
So a reward can't be granted by editing a request (zero trust); the most a
reader can do is mark chapters as read, which is what the badges celebrate.
"""

from datetime import date, timedelta

from gift_study import SLOTS

GOSPELS = ("Matthew", "Mark", "Luke", "John")
_CHAPTERS = {}
for (_book, _c), (_t, _, _) in SLOTS.items():
    _CHAPTERS.setdefault(_book, (_t, 0))
    _CHAPTERS[_book] = (_t, _CHAPTERS[_book][1] + 1)

# (id, title, what earns it, points, icon, test(stats))
BADGES = (
    ("first-chapter", "First steps", "Read your first chapter", 10, "book", lambda s: s["chapters"] >= 1),
    ("chapters-10", "Getting started", "Read 10 chapters", 25, "book", lambda s: s["chapters"] >= 10),
    ("chapters-50", "Hungry for the Word", "Read 50 chapters", 50, "book", lambda s: s["chapters"] >= 50),
    ("chapters-100", "Hundredfold", "Read 100 chapters", 100, "book", lambda s: s["chapters"] >= 100),
    ("chapters-250", "Deep roots", "Read 250 chapters", 150, "book", lambda s: s["chapters"] >= 250),
    ("chapters-500", "Halfway home", "Read 500 chapters", 250, "book", lambda s: s["chapters"] >= 500),
    ("chapters-1000", "Thousand", "Read 1,000 chapters", 400, "book", lambda s: s["chapters"] >= 1000),
    ("bible", "Cover to cover", "Read all 1,189 chapters of the Bible", 1000, "crown",
     lambda s: s["chapters"] >= len(SLOTS)),
    ("book-1", "Book finisher", "Read every chapter of a book", 50, "check", lambda s: s["books"] >= 1),
    ("books-10", "Ten books", "Finish 10 books", 150, "check", lambda s: s["books"] >= 10),
    ("gospels", "Good news", "Read all four Gospels", 150, "sparkle", lambda s: all(b in s["done"] for b in GOSPELS)),
    ("psalms", "Songbook", "Read all 150 Psalms", 150, "music", lambda s: "Psalms" in s["done"]),
    ("proverbs", "Wise heart", "Read all of Proverbs", 60, "sparkle", lambda s: "Proverbs" in s["done"]),
    ("nt", "New Testament", "Read the whole New Testament", 400, "crown", lambda s: s["nt_done"]),
    ("ot", "Old Testament", "Read the whole Old Testament", 700, "crown", lambda s: s["ot_done"]),
    ("streak-3", "Three in a row", "Read on 3 days in a row", 15, "flame", lambda s: s["best_streak"] >= 3),
    ("streak-7", "Week in the Word", "Read every day for a week", 40, "flame", lambda s: s["best_streak"] >= 7),
    ("streak-30", "Faithful month", "Read every day for 30 days", 150, "flame", lambda s: s["best_streak"] >= 30),
    ("streak-100", "Hundred days", "Read every day for 100 days", 400, "flame", lambda s: s["best_streak"] >= 100),
    ("streak-365", "A year in the Word", "Read every day for a year", 1000, "crown",
     lambda s: s["best_streak"] >= 365),
    ("joined-group", "Together", "Join a study group", 20, "users", lambda s: s["groups"] >= 1),
    ("leader", "Shepherd", "Lead a study group", 40, "users", lambda s: s["leads"] >= 1),
    ("first-friend", "Friend", "Make a friend", 20, "heart", lambda s: s["friends"] >= 1),
    ("friends-10", "Circle of ten", "Have 10 friends", 50, "heart", lambda s: s["friends"] >= 10),
    ("shared-verse", "Sharer", "Share a verse with a group", 20, "share", lambda s: s["verses_shared"] >= 1),
    ("encourager", "Encourager", "Send 25 messages to your groups", 40, "chat", lambda s: s["messages"] >= 25),
    ("in-step", "In step", "Tick off 7 days of a group reading plan", 40, "calendar",
     lambda s: s["plan_days"] >= 7),
    ("artist", "Psalmist", "Become an approved artist", 100, "music", lambda s: s["artist"]),
)
POINTS_PER_CHAPTER = 2
LEVEL_TITLES = ("Seeker", "Learner", "Reader", "Student", "Disciple", "Steward",
                "Teacher", "Elder", "Sage", "Pillar")


def level_for(points):
    """Level n starts at 50·n·(n−1) points: 0, 100, 300, 600, 1000, …"""
    n = 1
    while 50 * (n + 1) * n <= points:
        n += 1
    start, nxt = 50 * n * (n - 1), 50 * (n + 1) * n
    return {"level": n, "title": LEVEL_TITLES[min(n, len(LEVEL_TITLES)) - 1],
            "start": start, "next": nxt, "fraction": (points - start) / (nxt - start)}


def best_streak(days):
    best = run = 0
    prev = None
    for d in sorted(date.fromisoformat(x) for x in days):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


def stats(db, uid):
    rows = db.execute("SELECT book, day FROM chapters_read WHERE user_id=?", (uid,)).fetchall()
    per_book = {}
    for r in rows:
        per_book[r["book"]] = per_book.get(r["book"], 0) + 1
    done = {b for b, n in per_book.items() if b in _CHAPTERS and n >= _CHAPTERS[b][1]}
    one = lambda sql: db.execute(sql, (uid,)).fetchone()[0]
    return {
        "chapters": len(rows), "done": done, "books": len(done),
        "nt_done": all(b in done for b, (t, _) in _CHAPTERS.items() if t == "nt"),
        "ot_done": all(b in done for b, (t, _) in _CHAPTERS.items() if t == "ot"),
        "best_streak": best_streak({r["day"] for r in rows}),
        "groups": one("SELECT COUNT(*) FROM group_members WHERE user_id=?"),
        "leads": one("SELECT COUNT(*) FROM group_members WHERE user_id=? AND role='leader'"),
        "friends": db.execute("SELECT COUNT(*) FROM friendships WHERE (a=? OR b=?) AND status='accepted'",
                              (uid, uid)).fetchone()[0],
        "verses_shared": one("SELECT COUNT(*) FROM messages WHERE user_id=? AND ref IS NOT NULL"),
        "messages": one("SELECT COUNT(*) FROM messages WHERE user_id=?"),
        "plan_days": one("SELECT COALESCE(MAX(n), 0) FROM (SELECT COUNT(*) AS n FROM plan_progress "
                         "WHERE user_id=? GROUP BY group_id)"),
        "artist": bool(one("SELECT COUNT(*) FROM artists WHERE user_id=? AND status='approved'")),
    }


def rewards(db, uid):
    s = stats(db, uid)
    badges = [{"id": bid, "title": title, "description": what, "points": pts, "icon": icon,
               "earned": bool(test(s))} for bid, title, what, pts, icon, test in BADGES]
    points = s["chapters"] * POINTS_PER_CHAPTER + sum(b["points"] for b in badges if b["earned"])
    return {"points": points, **level_for(points), "badges": badges,
            "earned": sum(1 for b in badges if b["earned"]), "best_streak": s["best_streak"],
            "books_done": s["books"]}
